# T-214 v0.700 可观测性收尾

- status: completed
- area: frontend + docs（v0.700 边界内不扩后端）
- theme: 导入/完整性提示统一、v0.700 版本收口与 v0.800 排期

## 已完成（前端）

1. **数据完整性巡检文案**：`formatIssueLine` 在存在 `detail` 时附加说明（如 orphan `characterId=…`）
2. **Janitor 导入提示**：`ChatImportModal` 确认路径改用 `formatImportResultMessage`，与全局 `/api/import` 一致
3. **v0.700 文档收口**：ROADMAP/BACKLOG/CURRENT/LAST_HANDOFF/CHANGELOG 更新；T-211~213 标记完成

## v0.700 范围内已交付的可观测性（T-205/T-206 回顾）

- 后端：settings/characters/worldbooks 扫描 + chat `characterId` orphan（T-205，已在 v0.700 早期完成）
- 前端：`StartupIntegrityWatcher` 自动/人工分区；`formatImportResultMessage` 合并 MVU warning
- 导入：TXT/JSONL 行级 warning 透传（后端 T-206）

## 推迟到 v0.800（与 SSE composable、后端性能同批）

| 项 | 说明 |
|----|------|
| T-212#8 `useChatGeneration` | ChatPage SSE 主体（send/rewrite/group/interject） |
| 数据完整性 orphan 扩展 | 角色 `attachedWorldBookIds`、会话 overrides 世界书引用等 |
| 导出跳过项 warning | ZIP 导出缺失世界书 / globalActive 跳过需 API 返回 warnings |
| 后端性能 | chatId 索引、扫描路径、生成/MVU 热路径 |

## 后续排期调整

- 原生 Responses / Anthropic Messages / Gemini 多厂商对话协议层：T-214 完成时原定 v0.900+，现已调整为 **v0.800 T-805/T-806**。
- Playwright E2E：仍为 v0.900+。

## verify

```powershell
cd frontend
npm run test
npm run build
cd ..\backend
python -m pytest tests/ -q
```
