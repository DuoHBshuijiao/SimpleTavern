# T-211 v0.700 SettingsDrawer 渐进拆分

- status: in-progress
- area: frontend
- theme: 低风险子组件/Teleport 先拆，草稿生命周期保留父组件

## 已完成

1. Teleport 子组件：`SettingsDrawerRegexRuleEditorModal`、`SettingsDrawerModelSelectorModal`、`SettingsDrawerVoiceSelectorModal`
2. Global Tab accordion（全部）：
   - `SettingsDrawerGlobalAccordion`（共用折叠壳）
   - `SettingsDrawerGlobalConnectionSection`
   - `SettingsDrawerGlobalWebSearchSection`
   - `SettingsDrawerGlobalPromptsSection`
   - `SettingsDrawerGlobalAppearanceSection`
   - `SettingsDrawerGlobalTtsSection`
   - `SettingsDrawerGlobalAppSection`（含检查更新 / HTTP 日志入口）
3. Presets Tab：
   - `SettingsDrawerPresetsTab.vue`（列表 + 编辑器 UI，inject 上下文）
   - `useSettingsDrawerPresetListHeight.ts`（左栏列表高度）
   - `utils/voiceCatalog.ts`（`normalizeVoiceCatalog` 共享）

## 待做

4. Chat Tab：世界书、正文正则列表、TTS 会话
5. （可选）Presets 逻辑迁入 `useSettingsDrawerPresets.ts`，弱化 provide/inject

## 约束

- `handleSaveAll` / 脏检查 / 打开时 init 保留在父组件或 `useSettingsDrawerDraft()` composable。
