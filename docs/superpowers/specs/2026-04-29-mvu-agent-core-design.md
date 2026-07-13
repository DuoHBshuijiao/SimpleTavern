# MVU 助手核心管线设计

## 概述

在已有「会话级正则正文处理」基础上，搭建 MVU 助手（第三 Agent）核心管线。MVU 助手定位为纯自动 worker，不可交互、不可询问；与已有的聊天助手（内置 Claude Code 定位，可交互、可读日志、可修补变量）职责隔离。

## 当前基础设施

- `content_regex.py`：正则规则引擎，支持 remove/replace/extract/extract_and_replace 四种 action
- `content_regex_queue.py`：per-chat 内存 FIFO 队列（上限 500），extract action 产出物入队
- `content_regex_scanner.py`：后台守护（每 0.5s），扫描消息 → 应用规则 → extract 结果入队 → 设置 contentDisplay
- `schemas.py`：`ChatContentRegexRule` 已包含 extractSource/extractGroupIndex 字段；`CharacterCard.mvuEnabled` 已存在
- `chats.py`：`_merge_group_regex_rules_via_mvu()` 当前为确定性降级实现

关键缺口：**队列没有消费者**。提取项不断入队但无人读取，MVU Agent 不存在。

## 范围

- **包含**：MVU Agent 核心循环、领域分区工具注册框架、stateVariables 存储模型、胶囊条前端渲染、MVU 只读工作日志面板、聊天助手日志读取 + 变量修补工具
- **首域落地**：state_variables domain（4 个工具）
- **占位预留**：knowledge_graph、vector_memory domain
- **不包含**：群聊正则合并（_merge_group_regex_rules_via_mvu 保持当前确定性降级，待单聊跑通后再启动 Agent 合并）

## 架构分层

```
前端
├─ 胶囊条 (StateVariablesBar)          ← chatInput 上方常驻
├─ MVU 面板 (MvuPanel)                 ← 只读工作日志 SSE 流
└─ 聊天助手面板 (已有)                  ← 增强: read_mvu_logs + patch_state_variable

API 层
├─ /api/mvu/{chat_id}/stream           ← MVU 工作日志 SSE 推送
├─ /api/mvu/{chat_id}/state            ← GET/PUT stateVariables
├─ /api/generate/stream                ← 主生成 (已有)
└─ /api/assistant/...                  ← 聊天助手 (已有)

Agent 层
├─ MVUAgentService
│   ├─ ToolRegistry (领域分区)
│   │   ├─ state_variables  ← 首域落地
│   │   ├─ knowledge_graph  ← 注册占位
│   │   └─ vector_memory    ← 注册占位
│   └─ AgentLoop (复用 AssistantAgentService 循环骨架)
└─ AssistantAgentService (已有，增强 read_mvu_logs + patch_state_variable)

数据层
├─ chat.stateVariables    ← 版本化变量快照
├─ data/chats/{id}/mvu_logs.json  ← MVU 工作日志 (最近 200 条轮转)
└─ content_regex_queue    ← 提取队列 (已有)
```

## MVU 助手 vs 聊天助手 隔离

| | MVU 助手 | 聊天助手 |
|---|---|---|
| 消息来源 | 系统事件（生成完成 / 队列堆积） | 用户输入 |
| 交互性 | 只读 SSE 推送，无输入 | 完全可交互 |
| 工具范围 | 领域分区（state_variables + 未来 KG/向量） | 全量（含 read_mvu_logs + patch_state_variable） |
| system prompt | 纯 worker，不可交互 | 内置 Claude Code 定位 |
| SSE route | /api/mvu/{chat_id}/stream | /api/assistant/stream |
| 持久化 | mvu_logs.json | assistant 对话线程 |

## 领域分区工具注册框架

```python
# 每个 domain 声明
class MvuToolDomain:
    name: str
    description: str  # 注入 Agent system prompt
    tools: list[Callable]
```

### 首域：state_variables

| 工具 | 参数 | 说明 |
|------|------|------|
| `mvu_get_session_state` | chat_id | 读取 stateVariables + 提取队列快照 (最近 50 条) |
| `mvu_define_table` | chat_id, table_def | 申请/修改 N×M 表格 schema |
| `mvu_set_cell` | chat_id, table_name, field, column, value | 写入/修改单元格值 |
| `mvu_get_chat_context` | chat_id, count (默认 10) | 获取最近聊天消息片段 |

数据返回格式：`mvu_get_session_state` 和 `mvu_get_chat_context` 以 markdown table 形式向 Agent 返回原始数据，由 Agent 自行理解字段语义（第二行还是第二列）。

### 占位域

```python
# knowledge_graph
"kg_merge_entities"   # stub

# vector_memory
"vector_recall_chat_slice"  # stub
```

Agent system prompt 中只注入已激活 domain 的简短描述。未来激活新 domain 只需注册工具 + 更新 prompt，不改 Agent 循环代码。

## MVU Agent 生命周期

```
事件触发
    │
    ▼
MVUAgentLoop.run(job)
    │
    ├─ 1) mvu_get_session_state → 确认是否已有状态栏
    ├─ 2) mvu_get_chat_context  → 最近 N 条上下文
    ├─ 3) 推断 → mvu_define_table（首次）或 mvu_set_cell（更新）
    ├─ 4) 原子批量 commit stateVariables
    ├─ 5) SSE 推送工作日志 → 前端 MVU 面板 + 胶囊条刷新
    └─ 6) 消费完毕的提取项从队列移除
```

### 事件触发策略

| 触发器 | 条件 | 说明 |
|--------|------|------|
| 主生成完成 | generate/stream 返回 `[DONE]` | SSE done 事件驱动 |
| 队列堆积阈值 | extract 队列 ≥ 3 条未消费 | 即使没有新生成也触发 |

两触发器共用同一互斥锁，防止并发。

### 原子写入

Agent 输出一批单元格操作 → 服务端内存态完整校验 → 一次性覆盖 chat.json 中 stateVariables → 任一失败则全批回滚。

### 冷却

每次 Agent 执行完毕后 5s 冷却窗口，避免高频重复触发。

## 数据模型

### StateVariables（chat.json 内嵌）

```python
class StatusTableDef(BaseModel):
    name: str                          # 表名
    columns: list[str]                 # 列名（Agent 动态定义，不做约束）
    rows: list[StatusTableRow]

class StatusTableRow(BaseModel):
    field: str                         # 行字段名
    cells: dict[str, str]              # {列名: 值}

class StateVariables(BaseModel):
    version: int = 1                   # 单调递增，并发控制
    updatedAt: str = ""                # ISO 时间戳
    source: Literal["mvu_agent", "chat_assistant"] = "mvu_agent"
    tables: list[StatusTableDef] = []  # 支持多表
```

### MVU 工作日志条目

```python
class MvuWorkLogEntry(BaseModel):
    id: str
    chatId: str
    timestamp: str
    eventType: Literal["triggered", "planning", "tool_call", "commit", "error"]
    summary: str                       # "更新了好感度 68→72"
    detail: dict | None                # 工具调用参数/响应
```

存储：`data/chats/{chat_id}/mvu_logs.json`，与 chat.json 分离。保留最近 200 条，超出自动轮转。

### 提取队列增强

现有 `content_regex_queue.py` 新增：
- `dequeue_batch(chat_id, max_items: int) -> list[dict]` — Agent 批量消费
- 消费后即移除，无标记

## 前端交互

### 胶囊条 (StateVariablesBar)

- **位置**：ChatInput 正上方，常驻显示
- **内容**：`stateVariables.tables[0].rows` — 每颗胶囊 = field + 第一列 cell 值
- **动画**：值变化时 300ms 背景色闪烁（淡化过渡）
- **溢出**：水平滚动，首屏优先显示前 5 个
- **指示器**：MVU 运行时右侧显示小型旋转指示器
- **窄屏**：减少同时显示胶囊数，自动缩小字号

### MVU 面板 (MvuPanel)

- **入口**：胶囊条右侧齿轮图标，与聊天助手 FAB 独立并列
- **内容**：SSE 实时推送的 MVU 工作日志流
- **交互**：只读 — 无可输入框、无可操作按钮（仅关闭/最小化）
- **折叠**：默认折叠为侧边窄条，点击展开
- **宽高**：复用聊天助手面板的尺寸体系

### 聊天助手增强

新增两个工具：

| 工具 | 说明 |
|------|------|
| `read_mvu_logs` | 读取指定会话 MVU 工作日志（最近 N 条） |
| `patch_state_variable` | 修改 stateVariables 中指定单元格 |

## MVU Worker 消费守护

```python
def _ensure_mvu_worker(chat_id: str):
    # 检查 chat.character.mvuEnabled
    # 若开启且 daemon 未运行，启动 _mvu_loop(chat_id)

async def _mvu_loop(chat_id: str):
    while True:
        await wait_trigger()  # generate done OR queue >= 3
        batch = dequeue_batch(chat_id, 50)
        job = assemble_job(batch, chat_context, current_state)
        await agent_loop.run(job)  # SSE 推送 mvu_log_entry
        await commit_state_variables(chat_id)
        await asyncio.sleep(5)  # cooldown
```

## 技术决策清单

- Agent schema 完全自主定义，不预设变量类型
- 向 Agent 返回 markdown table，由 Agent 自行理解列/行语义
- 队列消费后直接移除，不保留已消费标记
- 两触发器（生成完成 + 队列阈值）共用互斥锁
- 原子批量写入 stateVariables，失败全回滚
- MVU 面板和聊天助手面板独立共存，各自折叠
- 首域落地 state_variables，KG/向量仅占位
- 群聊暂搁置，单聊跑通后再扩展

## 关联计划

- 上游依赖：`会话级正则正文处理_14453d10.plan.md`（已完成）
- 参考架构：`xml变量第三agent方案_c623ea46.plan.md`（未启动，本设计取其三层架构思路但缩小首域范围）
