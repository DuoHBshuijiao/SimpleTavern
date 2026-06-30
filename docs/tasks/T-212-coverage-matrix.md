# T-212 v0.700 ChatPage 子模块拆分 — 覆盖率矩阵

> 扫描时间：2026-06-30（v0.700 约 92%）

## ChatPage.vue 弹层 / 子模块

| 区域 | 状态 | 落点 |
|------|------|------|
| 角色编辑 + 工作区助手 | ✅ | `CharacterEditorModal.vue` + `useCharacterEditor.ts` |
| Persona 编辑 | ✅ | `PersonaEditorModal.vue` |
| Persona 切换确认 | ✅ | `PersonaSwitchConfirmModal.vue` |
| PNG 内嵌卡 / ST 预览确认 | ✅ | `EmbeddedCardConfirmModal.vue` + `useEmbeddedAvatarImport.ts` |
| 助手设置 | ✅ | `AssistantSettingsModal.vue` |
| 群聊创建 / 群设置 / 成员设置 | ✅（既有） | `GroupCreatorModal` 等 |
| 消息编辑 / 助手消息编辑 | ✅（既有） | `MessageEditorModal` |
| 导入导出 | ✅（既有） | `ChatImportModal` / `ChatExportModal` |
| 设置抽屉 | ✅（既有） | `SettingsDrawer`（T-211 已拆 Tab） |
| 知识图谱 / 错误堆栈 | ✅（既有） | `KnowledgeGraphModal` / `ErrorModal` |
| 头像裁剪 | ✅（组件化） | `AvatarCropper`（仍由 ChatPage 编排 show） |

## ChatPage 仍留父组件的编排（有意保留）

| 区域 | 行数量级 | 说明 |
|------|----------|------|
| 主流式生成 / SSE | ~1500+ | T-212#6 后拆；含 `saveSendDeferCtx` |
| 群聊轮次 / 插话 | ~800+ | 与生成流耦合 |
| 草稿助手 / TTS 预处理 | ~400+ | 可后续 composable |
| MVU Panel 绑定 | ~200 | 与 store 强耦合 |
| Esc 全局栈注册 | ~100 | 依赖多 overlay ref |

## SettingsDrawer（T-211）

| Tab / 模态 | 状态 |
|------------|------|
| Global / Presets / Chat Tab | ✅ 已拆 |
| Teleport 三模态（模型/音色/正则） | ✅ |
| Presets ref 绑定 | ✅ Bugbot 已修（bind 回调） |

## Composable 测试覆盖（frontend）

| composable | 单测 |
|------------|------|
| useChatSearch | ✅ |
| useImageStickyBinding | ✅ |
| useForkLineage | ✅ |
| useCharacterEditor | ❌ 待补 |
| useEmbeddedAvatarImport | ❌ 待补 |

## v0.700 剩余大项

- T-212#6：生成/SSE orchestration composable（低风险块先拆）
- T-213：ChatInput sink 动效 + motion audit
- T-214：可观测性收尾（orphan 扩展等）
