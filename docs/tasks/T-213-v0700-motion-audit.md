# T-213 v0.700 ChatInput sink 动效与 motion audit

- status: completed
- area: frontend
- theme: 去除 ChatInput 双轨 margin/transform 下沉；常规 UI 动效收束至 150–250ms token

## 已完成

### ChatInput sink（去 margin transition）

- 下沉改为 **仅 `transform` 作用于 `.chat-input-morph-wrap`**（卡片 + 底部提示同相）
- 移除 `.chat-input-shell` 负 `margin-top` 及 margin transition
- `transition` 始终挂在 morph-wrap，侧栏展开/收起时不再出现 margin 瞬变 + transform 缓动不同步
- `prefers-reduced-motion` 下 morph-wrap 禁用 transform

### Motion token（`variables.css`）

| Token | 值 | 用途 |
|-------|-----|------|
| `--motion-duration-fast` | 150ms | 快速反馈 |
| `--motion-duration-normal` | 200ms | 默认交互（同 `--transition-normal`） |
| `--motion-duration-moderate` | 250ms | Tab/pill 指示器 |
| `--motion-duration-expand` | 280ms | 折叠面板 grid 展开 |
| `--motion-ease-product` | `--ease-out-product` | 默认曲线 |

### Motion audit 修复

| 区域 | 原值 | 现值 |
|------|------|------|
| SettingsDrawer 主 Tab pill | 400ms | `--motion-duration-moderate` |
| SettingsDrawerChatTab 子 Tab | 400ms | 同上 |
| SettingsDrawerChatTtsSection pill | 400ms | 同上 |
| SettingsDrawerGlobalAccordion | 800ms ease-in-out | 280ms ease-out |

### 保留的编排动画（有意例外）

| 区域 | 时长 | 说明 |
|------|------|------|
| `chatHeaderMorph.ts` | 420 / 520ms | 顶栏 inset → lifting → full 与 WebGPU/输入区同频 |
| ChatInput placeholder reveal | 随 `--chat-input-trans-dur` | 与顶栏 lifting 同步 |
| MessageList FLIP | 420ms | 与 `HEADER_LIFT_MS` 对齐 |
| TtsPlaybackFab / Agent 顶栏 chip | 220–380ms | 顶栏 full 后 staged reveal |

## verify

```powershell
cd frontend
npm run test
npm run build
```
