# T-802 v0.800 全后端静默 Fallback 审计与迁移

- status: in-progress（前四批已完成：LLM/generate、Storage、Assistant/tools、MVU/regex；含 F-009）
- area: `backend/app/**`
- priority: P0
- theme: 每个 catch/fallback 都有业务语义、用户可见结果与测试

## 目标

在 T-801 统一错误基座完成后，逐模块清理 backend 的静默失败。此任务不是机械删除所有 `except`；每一处必须归类为：

1. **fatal**：转换为 AppError 并终止当前操作。
2. **partial**：返回 `partialSuccess=true` + `warnings[]`，用户可见。
3. **retryable**：有限重试，最终错误可见。
4. **explicit fallback**：仅用户启用时执行，记录 from/to/reason。
5. **cleanup-only**：主结果已确定，清理失败记录结构化日志/健康状态。

禁止保留无说明的 `pass`、`return []`、`return None`、默认对象或 `continue` 来隐藏业务失败。

## 审计发现的首批高风险点

### Storage / Chats / Fork

- `storage.list_characters()` / `list_worldbooks()`：损坏 JSON 被 `continue`，对象从 UI 静默消失。
- `_load_chat_from_path()`：异常转 `None`，列表与实际磁盘状态不一致。
- `load_update_ignore()`：损坏数据被覆写为空对象。
- 删除图片/会话/工作区清理中的 `pass` / `continue`。
- chatId 路径查找、群聊列表与 fork index 重建存在全目录扫描。

目标：

- 损坏项进入 integrity issue 或列表 `warnings/corruptEntries`。
- 不把损坏数据转换成“未找到”。
- rollback/cleanup 失败保留主异常并附加 cleanup error。
- chatId/fork 索引损坏可检测、可重建、可感知。

### LLM / Generate

- `openai_compat.list_models_openai_compat()`：任意失败返回 `[]`。
- `/llm/models`：空结果静默回退 `modelCandidates/defaultModel`。
- SSE 非法 JSON 行被跳过；可能丢 token/tool chunk。
- generate SSE error 只有裸 `message`。
- 世界书坏 regex 被跳过。
- 角色缺失时部分路径使用占位名称继续。

目标：

- 模型列表失败返回真实错误；候选模型作为“本地配置列表”单独标明 source，不伪装云端成功。
- 非法协议帧 fast-fail；仅识别明确的 keepalive/comment 帧。
- 上游断流、无 finish、空 response、工具参数损坏均有稳定 code。
- 世界书规则错误进入用户可见 warning/error。

### 正文正则契约（F-010，已确认语义 A）

- 消息 content **永远存原文**；`generate` 落库路径**不得**调用 `apply_content_regex_pipeline`。
- 前端 `contentRegex.ts` 在渲染时即时处理显示文本。
- 后端 `apply_content_regex_pipeline` 仅供 `content_regex_scanner` / MVU 提取等非显示路径。
- 静态守卫锁定上述契约；不得改为「落库前改写」。

### Assistant / Tools

- 非法 AssistantChat 消息有保留原对象继续写盘的路径。
- Agent/工具异常部分只返回 `str(exc)`，无 code/requestId/details。
- 记忆刷新失败可能转 `None`，主流程继续。
- 工具参数 JSON 失败可能退为空对象。

目标：

- 持久化前严格校验；脏对象不入库。
- tool error 保留 ToolResult 结构并关联 requestId。
- 参数解析失败直接 `tool_call_invalid`，不得以 `{}` 调用工具。
- 记忆/卡片/世界书副作用失败必须明确 partial 或 fatal。

### MVU / KG / Regex Scanner

- worker/scanner 循环异常多为日志 + continue/退避，用户看不到 lastError。
- chat/角色缺失可能被视为功能关闭。
- QueueFull 被吞。
- 工具参数损坏可能退为空对象。

目标：

- 每个 worker 维护 health/lastError/failureCount/nextRetryAt。
- 连续失败达到阈值后暂停并通知用户，不无限隐式重试。
- 配置关闭与运行失败分开表示。
- QueueFull 记录 dropped event 数并上报。

### Import / Export / Avatar

- 行级损坏、头像下载、MVU 兼容已有 warnings 模式，可保留 partial success，但必须统一结构。
- 角色+世界书 ZIP 遇缺失 worldbook 会 `continue`。
- 导出角色缺失时可能使用占位信息。
- PNG 多候选解析失败被逐个跳过。

目标：

- 统一 `partialSuccess/imported/skipped/warnings/errors`。
- 导出缺失附件必须在 manifest/warnings 中记录。
- “普通导入成功但 MVU 兼容失败”必须由用户策略决定是否接受。
- 所有跳过项带 path/id/reason。

### TTS

- GLM local JSON 请求失败后存在 multipart fallback。
- 音色列表/解析失败可能返回空列表。
- 本地子进程清理/健康检查异常部分只写日志。

目标：

- JSON→multipart fallback 改为显式能力配置或用户可见 warning；默认不静默重试另一端点。
- 音色列表失败不得呈现为“没有音色”。
- 子进程状态 API 暴露 lastError/exitCode/restartCount。

### Web Search

- 主聊天打开搜索但未配置 Key 时，当前可能静默不挂工具并走普通生成。
- provider 失败以 JSON 字符串塞入工具结果；主聊天/Assistant 契约不同。
- async/sync provider 分支重复。

目标：

- 开关开启但未配置时，在发送前或 SSE meta 阶段 fast-fail。
- provider registry + 统一 SearchResult/SearchError。
- 默认禁止跨 provider fallback。
- auth/quota/timeout/invalid response 分开。

### 基础设施与后台任务

- HTTP log 写盘失败可能丢记录。
- tokenizer 不可用返回 `None`。
- update/clipboard/avatar/daemon/sweeper 有清理异常或默认值路径。

目标：

- 观测组件自身失败进入 health 状态，避免“记录系统无记录”。
- tokenizer 估算不可用明确标记 unavailable，不显示为 0。
- cleanup-only 错误记录 requestId/taskId，不覆盖主错误。

## 执行方式

## 当前进度（2026-07-10）

### 首批已完成

- 建立 `docs/audits/v0800-backend-fallback-inventory.md`，覆盖八个 backend 领域的首轮 P0/P1 高风险清单；T-801 已迁项与合理 cleanup/default 单独登记。
- `/llm/models` 与 `/llm/test-models` 上游空列表改为 `model_list_empty`，不再回退本地候选或返回 200 + `[]`。
- OpenAI-compatible 非流空 choices/空消息、流式非法 JSON/未知帧/空流/无结束标记改为稳定 `provider_response_invalid`、`stream_event_invalid`、`stream_interrupted`。
- 明确允许 SSE 空行、`:` comment/keepalive、usage-only 帧，以及有 `finish_reason` 但无 `[DONE]` 的兼容结束。
- 网络搜索工具参数非法 JSON、非对象、空 query 或未知工具改为 `tool_call_invalid`，不再用 `{}` 调用。
- draft-help/group/interject 统一 requestId、SSE meta/terminal error/success-only done 与非流 ErrorEnvelope。
- group/interject 开启网络搜索但未配置时，生成前 `web_search_not_configured` fast-fail。
- 静态守卫覆盖已迁文件的 broad-except silent return、裸 SSE error 与旧 `{ok,error}` 回归。
- 正文正则事实核验：generate 未调用 `apply_content_regex_pipeline`；后确认为语义 A（存原文 + 前端显示），非缺口。
- Grok 4.5 只读复查无阻塞问题；坚持 OpenAI Chat Completions 的 string arguments、integer tool index 与 data/comment 帧契约，不增加隐式兼容。
- 门禁：后端 `150 passed`、前端 `121 passed`、前端 build 通过。

### 第二批已完成

- 角色/世界书列表保持 `list[...]` 兼容契约；坏项实时侧写到既有 data-integrity issue，完整校验与实际加载规则对齐。
- 直接加载损坏角色、世界书、会话时统一 `data_corrupted`，不再把“文件存在但损坏”伪装成 404。
- runtime chat issue 连续轮询仍保持完整 Pydantic 校验，文件真正修复后才从巡检面清除；`read_error` 不允许自动删除。
- `update_ignore.json` 损坏改为 `update_ignore_corrupt`，原文件不再被静默覆写为空对象，启动更新检查保留该 AppError。
- fork index 损坏会从 chat 元数据重建并返回 warning；重建失败为 retryable `fork_index_rebuild_failed`；sync 失败不覆盖已保存会话，并在下次 lineage 强制重建。
- 瞬时并发写/读失败使用 `ScanUnavailable` 保留已有 integrity issue；只有稳定确认文件恢复或消失时才清除。
- fork corrupt/sync warning 在成功重建时写入索引 `warnings[]`，不再被首次 lineage 请求一次性消费。
- 删除/回滚/附件清理失败统一 `cleanup_failed` 结构化日志，关联 requestId，且目录删除保持逐项尽力清理。
- 性能基线：1000 会话、99 fork 冷重建 `410.05 ms`，门槛 `< 5000 ms`，锚点齐全时禁止完整 `load_chat()`。
- Grok 4.5 两轮只读复查无阻塞/高优先级遗留。
- 门禁：后端 `169 passed`、前端 `123 passed`、前端 build 通过。

### 第三批已完成

- F-017：`_normalize_assistant_chat_for_save` 校验失败抛 `assistant_message_invalid`，禁止脏消息落盘。
- F-018：工具参数非法 JSON/非对象写入 `tool_call_invalid` ToolResult，不再退 `{}` 执行；executor 同步拒绝非 dict。
- F-019：agent 非流抛 AppError；流式错误事件携带 ErrorEnvelope + terminal；route 对齐 meta/done/`app_error_response`。
- F-020：workspace character-card 缺失/损坏分别 `data_not_found`/`data_corrupted`；成功直接返回 CharacterCard；前端按 2xx 卡片体适配。
- 新增 `test_assistant_error_contracts.py`；静默 fallback 守卫纳入 assistant/agent/executor。
- 门禁：后端 `178 passed`；本机前端 `node_modules` 缺失未跑（文档基线仍记前端 123）。

### 第四批已完成

- 新增共享 `WorkerHealth`；MVU worker / content-regex scanner 暴露 failureCount、lastError、paused、nextRetryAt。
- F-021/F-022：MVU loop 失败可观测；SSE QueueFull 计入 `sseDropped`。
- F-023：角色不可读与「未启用」分离为 `mvu_character_unreadable`；KG 门控透传。
- F-024：MVU 工具非法 JSON 不再退 `{}`。
- F-025/F-026：scanner health + 队列 dropped；`GET /api/mvu/{chatId}/health`、`GET /api/content-regex/health`。
- F-009：世界书坏 regex → `worldbook_regex_invalid` 进入 generate SSE meta.warnings。
- 门禁：后端 `185 passed`。

### 第五批已完成

- F-027：网络搜索 provider 失败返回结构化 `{ok,code,message}`；助手工具 `ToolResult.err`；generate 工具 content 走 `format_web_search_tool_content`。
- F-028：角色导出 ZIP `manifest.json` 写入 `warnings` / `partialSuccess` / `exportedWorldBookIds`（含 `export_attachment_missing`）。
- F-029：导入 warning 统一 `_import_warning`；前端兼容 string 与 `{code,message}`。
- 静默 fallback 守卫纳入 `web_search.py` / `import_export.py` / web_search handler。
- 门禁：后端 `191 passed`。

### 第六批已完成

- F-030：GLM 本地 JSON→multipart 显式 fallback，带 `tts_endpoint_fallback`（from/to/reason）。
- F-031：SiliconFlow 音色列表失败返回预设 + `tts_voice_list_partial` / `partialSuccess`。
- F-032：GLM 本地进程 health（failureCount/lastError/code）；health/start 路由结构化返回。
- F-033：http_log 写失败计数 + `GET /api/http-log/health`。
- F-034：tokenizer unavailable；generate 不再 `or 0` 伪装 system token；`GET /api/tokenizer/health`。
- 门禁：后端 `198 passed`。

### 下一批

1. T-803：性能基线、profiling、共享 HTTP client、索引与 I/O。
2. 前端消费各类 health / dropped / partial warning UI（可选跟进）。

### 1. 建立机器可读清单

建议维护 `docs/audits/v0800-backend-fallback-inventory.md`，每行：

| 文件/函数 | 当前行为 | 分类 | 新 code | 用户展示 | 测试 | 状态 |
|-----------|----------|------|----------|----------|------|------|

### 2. 分域小批迁移

推荐顺序：

1. LLM/model list/generate。
2. Storage/chat list/fork。
3. Assistant/tools。
4. MVU/KG/regex scanner。
5. Search。
6. Import/export/avatar。
7. TTS。
8. HTTP log/update/clipboard/后台任务。

每批独立测试与 review，不做一次性全仓大改。

### 3. 静态守卫

新增测试/脚本扫描：

- 裸 `except: pass`。
- `except Exception: return []/{}/None`。
- route 层业务失败返回 HTTP 200。
- SSE error 后继续 done。

允许例外必须有邻近注释与规则 ID，说明为何属于 cleanup-only 或显式 partial。

## 性能热点同步登记

迁移错误路径时同时测量，不另起“只改异常不看性能”的重复工程：

- `_find_chat_path_by_id` 全目录扫描。
- content regex scanner 每 5 秒全库扫描。
- group chat summaries / fork index 冷重建。
- portalocker 每次读写链。
- generate 世界书 regex/token trim。
- import/export ZIP。
- HTTP log 分片扫描。
- MVU worker 周期加载。

## 验收

- `backend/app/**` 每个异常捕获点均已登记和分类。
- P0/P1 静默 fallback 全部迁移。
- 用户操作失败可在 UI 看到明确 message/suggestedAction/requestId。
- 批处理 partial success 有逐项 warning，不因单项失败吞掉全批，也不把 partial 标为完整成功。
- 搜索、TTS、导入等显式 fallback 有开关与记录。
- 正文正则语义 A 有事实性回归测试：generate 不调用管线；scanner 保留调用。
- 性能热点有基线记录。

## verify

```powershell
cd backend
python -m pytest tests/ -q

cd ..\frontend
npm run test
npm run build
```

## next

T-802 可与 T-803/T-804 按领域并行，但任何新 provider 或统计 API 必须使用 T-801 错误契约。
