# T-800 v0.800 后端性能与生成流拆分

- status: planned
- area: backend + frontend（生成 composable 与后端热路径同批）
- theme: 性能、SSE 编排提炼、数据完整性后端扩展

## 背景

v0.700 专责**前端**组件化、UI/动画与前端侧可观测性。以下项在 v0.800 **合并推进**（共享生成/持久化边界，避免前后端重复改接口）：

1. **ChatPage SSE orchestration composable**（T-212#8 遗留）
2. **后端性能改进**（路线图 v0.800 定位）
3. **数据完整性 orphan 扩展**（世界书引用等，需后端扫描 + 前端展示）
4. **导出跳过项 API warnings**（角色+世界书 ZIP 等）

## 不在 v0.800

- 原生多厂商对话协议（Responses / Anthropic / Gemini）→ **v0.900+**

## 建议子任务（草案）

| ID | 内容 |
|----|------|
| T-801 | `useChatGeneration` / SSE 事件消费 composable，ChatPage 只保留编排 |
| T-802 | chatId 索引与 chats 目录扫描优化 |
| T-803 | 生成/MVU 热路径 profiling + 批量化 I/O |
| T-804 | 完整性：worldbook orphan + 导出 warnings API |
| T-805 | 全链路 pytest + 前端 composable 单测 |

## read_first

- `frontend/src/views/ChatPage.vue`（sendUserMessage / handleRewriteMessage / triggerInterject）
- `frontend/src/composables/useGenerationDeferState.ts`
- `backend/app/services/data_integrity.py`
- `backend/app/routes/import_export.py`（export_character ZIP）
- `docs/01-ROADMAP.md` v0.800 节
