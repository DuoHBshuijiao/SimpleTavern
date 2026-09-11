# T-831 v0.820 群聊成员级思考深度 / Fast

- status: **done**
- area: `schemas.GroupMemberSettings`、`generate.py` `_prepare_generation`、`MemberSettingsModal.vue`、`useChatActions.ts`
- priority: P0
- depends_on: T-824（会话级 `reasoningEffort` / `fastMode`）

## 目标

群聊每个成员可覆盖思考深度与 Fast，优先级与既有 `pick_param` 一致：

`runtime.params` → `memberSettings` → `chat.overrides.params` → 全局 `settings.reasoningEffort`（Fast 默认关）。

`null` / 缺省 = 沿用上一层；成员显式 `fastMode: false` 必须关掉，不能被 `bool(None)` 误伤（先 pick 再 `bool`）。

## UI

成员设置弹窗：思考深度下拉（含「沿用会话/全局」）；Fast 三态（沿用 / 开 / 关）。文案对齐助手设置。

## 路径

群聊 generate 与 rewrite 两处 `_prepare_generation` 都传入 `member_settings`。单聊路径不传。
