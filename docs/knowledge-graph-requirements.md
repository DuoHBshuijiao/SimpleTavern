# SimpleTavern 知识图谱功能需求

> 2026-05-20 整理自 5/19 晚与 5/20 的讨论

## 一、定位

MVU agent 在维护状态栏变量的同一轮 call 中，同步维护知识图谱。图谱数据在角色扮演 LLM 上下文内注入，与状态栏并列。

核心约束：**agent 不能自由生成图谱 JSON**。图谱结构由后端 Pydantic 模型严格定义、前端按确定性规则可视化渲染。agent 仅通过工具（tools）进行增删查改——结构由代码保证，内容由 agent 填充。

## 二、数据模型

### 2.1 KgEntity（实体）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识，工具自动生成 |
| `name` | `str` | 显示名 |
| `type` | `Literal["人物", "地点", "物品", "势力", "事件"]` | 实体类型，影响前端渲染颜色 |
| `properties` | `dict[str, str]` | 自由属性，如 `{"年龄": "32", "职业": "侦探"}` |
| `firstMentionedAt` | `str | None` | 首次提及的消息 ID，可溯源 |

### 2.2 KgRelation（关系）

| 字段 | 类型 | 说明 |
|------|------|------|
| `subject` | `str` | 主体实体 ID |
| `predicate` | `str` | 关系谓语，如"信任"、"仇视"、"位于"、"拥有" |
| `object` | `str` | 客体实体 ID（或字面量字符串） |
| `establishedAt` | `str | None` | 确立该关系的消息 ID |
| `confidence` | `float` | 0.0 ~ 1.0，推测（0.3）还是确知（1.0） |

### 2.3 KnowledgeGraph（顶层容器）

| 字段 | 类型 | 说明 |
|------|------|------|
| `entities` | `list[KgEntity]` | 实体列表 |
| `relations` | `list[KgRelation]` | 关系列表 |
| `version` | `int` | 乐观锁版本号 |
| `updatedAt` | `str` | ISO 时间戳 |
| `source` | `str` | 固定为 `"mvu_agent"` |

## 三、MVU agent 新增工具

与现有四件工具（`mvu_get_session_state`、`mvu_define_table`、`mvu_set_cell`、`mvu_get_chat_context`）平行注册。

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `kg_upsert_entity` | `name`, `type`, `properties?` | 新建或按 `name+type` 去重合并。返回实体 ID |
| `kg_delete_entity` | `entity_id` | 逻辑删除（标记而非物理删除，保留溯源） |
| `kg_upsert_relation` | `subject_id`, `predicate`, `object_id`, `confidence?` | 新建或更新三元组。后端校验两端实体存在性 |
| `kg_get_context` | （无） | 返回图谱摘要文本——用于注入 RP prompt |
| `kg_query` | `entity_name?`, `relation_type?`, `type?` | 按条件查询实体/关系 |

### 不做约束的项

- 不限制每轮 agent 调用工具的次数
- 不限定关系谓语词表（agent 自由拟定 predicate）
- 不限制每次新增/修改的实体和关系数量

## 四、RP 上下文注入

在 prompt 构建阶段（`routes/generate.py`），与 `_inject_mvu_state_tables_for_directive` 并列，新增 `_inject_knowledge_graph` 函数。

注入格式（XML 标签，与现有 `CharacterCard`、`StateVariables` 体系一致）：

```xml
<KnowledgeGraph>
[人物]
- 张三：32岁，私家侦探（首次提及于 msg_0003）
- 李四：28岁，古董商（首次提及于 msg_0015）

[地点]
- 德月楼：城东茶楼

[关系]
- 张三 调查 李四（置信度: 0.8）
- 李四 藏有 神秘铜镜
- 德月楼 位于 城东
</KnowledgeGraph>
```

仅在 MVU 运行时启用（`is_chat_mvu_runtime_enabled`）且至少有一个实体时才注入，零实体零开销。

## 五、存储

- 路径：`data/chats/{chat_id}/knowledge_graph.json`
- 文件级操作符：`load_knowledge_graph(chat_id)` / `save_knowledge_graph(chat_id, kg)`
- 在 `storage.py` 中实现，与现有 `load_chat` / `save_chat` 的 JSON + `portalocker` 模式一致
- 懒初始化：首次 MVU agent 调用时若文件不存在，自动建空 `KnowledgeGraph`
- 未启用 MVU 的会话：不创建该文件，零开销

## 六、前端可视化

### 6.1 渲染方案
- 实体 → 力导向图节点，颜色按 `type` 区分（人物=蓝、地点=绿、物品=橙、势力=红、事件=灰）
- 关系 → 节点间带标签的有向边，标签为 `predicate`
- 单击节点 → 侧边栏显示实体详情 + 关联关系列表
- 图库：`vis-network` 或 `D3.js force simulation`（二者均直接吃 JSON，无需额外转换层）

### 6.2 前端状态
- 从 `GET /api/mvu/{chat_id}/state` 或新增 `GET /api/mvu/{chat_id}/knowledge-graph` 拉取图谱 JSON
- 图谱更新时前端实时刷新（可复用 SSE 事件或定时拉取）
- 图谱数据只读展示在前端——编辑操作由 MVU agent 通过工具执行

## 七、与现有系统的对接

- **MVU agent prompt**：在 system prompt 中追加知识图谱工具的使用指南，与状态栏工具说明并列
- **MVU work log**：图谱操作记录纳入 `MvuWorkLogEntry`（与状态栏变更同一条目，或新增 `kgOperations` 字段）
- **`/forget` / session 重置**：删除对应的 `knowledge_graph.json`
- **聊天导出**：图谱可作为独立文件导出，或嵌入导出包
- **角色卡导入**：若酒馆角色卡内含世界书/关系数据，可尝试自动填充初始图谱实体

## 八、实现顺序建议

1. **数据模型 + 存储**（`schemas.py` 中定义 `KgEntity`/`KgRelation`/`KnowledgeGraph`，`storage.py` 增加读写函数）
2. **MVU agent 工具**（5 件工具 handler，注册到 `registry.py`）
3. **MVU agent prompt 追加**（更新 `prompt.py` 中 agent 的系统提示）
4. **RP prompt 注入**（`routes/generate.py` 增加 `_inject_knowledge_graph`）
5. **前端可视化**（节点-边图组件 + API 端点）
6. **测试**（单元：实体去重、关系校验、JSON 序列化；集成：MVU agent 同一轮同时操作状态栏和图谱）
