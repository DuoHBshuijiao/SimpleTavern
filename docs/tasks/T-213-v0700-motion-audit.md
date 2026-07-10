# T-213 v0.700 ChatInput sink 动效与 motion audit

- status: completed
- area: frontend
- theme: 去除 ChatInput 双轨 margin/transform 下沉；常规 UI 动效收束至 150–250ms token

## 已完成

### ChatInput sink

- 下沉：`.chat-input-morph-wrap` 用 `translateY`（卡片 + 底部提示同相）
- **布局补偿**：`.chat-input-shell--sink` 等量负 `margin-top`（抵消 transform 不占流的空隙）
- `margin-top` 的 transition 挂在**壳基类**上，避免去掉 `--sink` 后 margin 瞬变、transform 仍缓动
- `prefers-reduced-motion` 下禁用 margin/transform

> Bugbot（`887737b`）：仅 transform、无负 margin 时 steady 态会多出 `--chat-input-sink-shift` 空隙；已恢复布局补偿。

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
