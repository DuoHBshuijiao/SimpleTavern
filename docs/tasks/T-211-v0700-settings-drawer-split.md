# T-211 v0.700 SettingsDrawer 渐进拆分

- status: in-progress
- area: frontend
- theme: 低风险子组件/Teleport 先拆，草稿生命周期保留父组件

## 已完成

1. Teleport 子组件：`SettingsDrawerRegexRuleEditorModal`、`SettingsDrawerModelSelectorModal`、`SettingsDrawerVoiceSelectorModal`（草稿/保存逻辑仍留父组件）

## 待做

2. Global Tab accordion：Web Search、TTS 全局、检查更新
3. Presets Tab 整体
4. Chat Tab：世界书、正文正则列表、TTS 会话

## 约束

- `handleSaveAll` / 脏检查 / 打开时 init 保留在父组件或 `useSettingsDrawerDraft()` composable。
