# T-803 v0.800 性能基线与基础设施

- status: in-progress（3A/3B/3C 已完成；下一棒 3D）
- area: backend HTTP / I/O / 索引
- priority: P0
- theme: 先测量再优化；共享连接池、索引与锁；每项有基线与回归门槛
- depends_on: T-801（完成）、T-802（完成）

## 目标

建立可复用的性能基础设施，并形成可回归的基线数字。本任务**不**迁移 LLM 协议内核（T-804），也**不**做 usage ledger（T-807）。

## read_first

- `docs/tasks/T-800-v0800-backend-performance.md`
- `docs/state/LAST_HANDOFF.md`
- `backend/app/llm/openai_compat.py`
- `backend/app/services/web_search.py`
- `backend/app/services/tts_platform.py`
- `backend/app/fork_index.py`
- `backend/app/storage.py`
- `backend/app/main.py`

## 批次计划

| 批次 | 主题 | 落点 | 完成定义 |
|------|------|------|----------|
| **3A** | 共享 HTTP client / 超时 / 连接池 | `http_client` 模块；先迁 `openai_compat` + `web_search` | 进程级复用；lifespan 关闭；单测覆盖复用与超时透传 |
| 3B | chatId / fork / usage 索引与 I/O | `storage`、`fork_index` | 避免热路径全目录扫；扩展既有 fork 基线 |
| 3C | 后台扫描与锁 | content-regex scanner、portalocker、原子写 | 扫描间隔/增量策略有数据；锁冲突可观测 |
| 3D | 生成热路径 profiling | `generate` 世界书/trim/重复加载 | 有 profiling 记录与前后对比，只改有证据的点 |

## 强制规则

1. 每项优化必须记录：改前数字、改后数字、回归门槛。
2. 禁止静默换供应商/换模型；性能失败仍走 AppError。
3. 共享 client 不得改变现有业务超时语义（请求级 timeout 可覆盖默认）。
4. 测试环境可懒创建 client；应用 lifespan 负责正式启动/关闭。
5. 本任务不并行启动 T-804。

## 基线矩阵（初始）

| 路径 | 当前已知基线 | 目标 / 门槛 | 状态 |
|------|--------------|-------------|------|
| fork 冷重建 1000 chats / 99 forks | 410.05 ms | `< 5000 ms` | 已有（T-802） |
| LLM 出站 AsyncClient | 每次请求新建 | 进程内复用；连接池 limits 可配置 | 3A done |
| web_search Async/Sync Client | 每次请求新建 | 进程内复用 | 3A done |
| TTS platforms | 实例内已持有 client | 后续评估是否并入共享池 | 待评估 |
| `_find_chat_path_by_id` | O(角色数) exists 扫描 | 索引命中为主路径 | 3B done |
| chat_path 冷重建 1000（50×20） | — | 103.11 ms；门槛 `< 1000 ms` | 3B done |
| chat_path 暖查找 ×1000 | — | 105.55 ms；门槛 `< 500 ms` | 3B done |
| content-regex scanner | 每 5s 全库双载 | 去双载 + mtime 跳过；暖路径 ≪ 冷路径 | 3C done |
| scanner 冷扫 100 chats | — | 130.21 ms；门槛 `< 5000 ms` | 3C done |
| scanner 暖扫 100（mtime 跳过） | — | 16.54 ms；门槛 `< max(100, 冷×25%)` | 3C done |
| portalocker 等待 | 不可见 | health 含 waitMs / acquireCount | 3C done |
| generate worldbook/trim | 未 profiling | 有火焰图或分段计时 | 3D |

## 3A 实现要点

1. 新增 `backend/app/services/http_client.py`：
   - `get_async_http_client()` / `get_sync_http_client()`
   - `startup_http_clients()` / `shutdown_http_clients()`
   - 默认 `Timeout` + `Limits`（keepalive）
2. `main.py` lifespan：启动创建、关闭 `aclose`/`close`
3. 迁移：
   - `openai_compat`：models / nonstream / stream 不再 `async with AsyncClient(...)`
   - `web_search`：async/sync 搜索改用共享 client；请求级 timeout 保留
4. 测试：client 同一性、请求 timeout 覆盖、shutdown 后可重建

## 明确不做（本卡）

- 原生 Responses / Anthropic / Gemini
- usage ledger / 成本 UI
- 前端 health 仪表盘（可另开小批）
- 一次性改完所有 TTS platform client（可在 3A 验收后评估）

## 验收命令

```powershell
cd backend
python -m pytest tests/ -q
```

## 完成记录

### 3A（已完成）

- 新增 `backend/app/services/http_client.py`：进程级 Async/Sync client、默认 Timeout/Limits、懒创建与 lifespan 关闭。
- `openai_compat`（models/nonstream/stream）与 `web_search`（async/sync/usage）改为共享 client；请求级 timeout 保留。
- `main.py` lifespan：`startup_http_clients` / `shutdown_http_clients`。
- 测试：`test_http_client.py`；`test_openai_compat` mock 改为 patch `get_async_http_client`。
- 门禁：后端 204 passed。

### 3B（已完成）

- 新增 `backend/app/chat_path_index.py`（`data/chat_path_index.json`）：`byId → {characterId, format}`。
- `_find_chat_path_by_id` 走索引；miss/stale 回退扫描并回写。
- `save_chat` upsert、`delete_chat` / `delete_chats_by_character` 失效；lifespan 预热。
- 基线（本机）：重建 1000 会话 `103.11 ms`；暖查找 ×1000 `105.55 ms`。
- 测试：`test_chat_path_index.py`；门禁后端 209 passed。

### 3C（已完成）

- `_chat_iter` / 扫描主路径去掉 `list_group_chats`+`list_chats` 双载；改为 `iter_chat_record_paths` 单次枚举。
- mtime/size + 全局规则签名 + 角色卡 mtime 缓存：未变更会话跳过 `read_json`/validate。
- 扫描读路径：`read_json(shared=True)` + 不附加 longTermMemory；消息签名仅在 apply/enqueue 成功后写入。
- 锁观测：`get_lock_observability()`；`/api/content-regex/health` 增加 `lastScanDurationMs`、`chatsLoaded`、`chatsSkippedUnchanged`、`lockWaitMs*`。
- 基线（本机）：冷扫 100 会话 `130.21 ms`；暖扫 `16.54 ms`。
- 测试：`test_content_regex_scanner_baseline.py`；门禁后端 214 passed。
