# T-209 v0.700 UI/动画全面收束

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: done
- area: frontend
- theme: Impeccable 全量扫尾 + 滚动条/圆角 token 统一 + side-tab 消除

## read_first

- `frontend/src/styles/variables.css`
- `frontend/src/styles/scrollbar.css`
- `frontend/src/components/chat/*.vue`
- `frontend/src/components/modals/*.vue`
- `frontend/src/components/SettingsDrawer.vue`

## acceptance

- Impeccable detect 通过：`components/chat`、`components/modals`、`SettingsDrawer.vue`（ChatInput margin 动画另开 T-211）。
- 全局 `.custom-scrollbar` 定义于 `scrollbar.css`，组件内重复 scoped 块删除或仅保留非滚动条样式。
- SettingsDrawer 正文正则列表移除 `border-l-4` side-tab，改用 `surface-selected`。
- `--radius-track` / `--radius-scrollbar` / `--radius-xs` 覆盖全部非标准圆角。

## verify

```powershell
cd E:\SimpleTavern\frontend
npm run test
npm run build
npx impeccable detect frontend/src/components/chat
npx impeccable detect frontend/src/components/modals
npx impeccable detect frontend/src/components/SettingsDrawer.vue
```
