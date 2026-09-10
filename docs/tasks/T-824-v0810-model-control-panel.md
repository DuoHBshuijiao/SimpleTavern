# T-824 v0.810 聊天栏「模型控制面板」

- status: **done**
- area: `frontend/src/components/chat/ModelControlPanel.vue`、`ChatInput.vue`、`ChatPage.vue`、`useAssistant`、`schemas.GenerationParams`、`resolution.py`
- priority: P0
- depends_on: T-822 后端解析

## 目标

把 ChatInput 底部的模型下拉升级为主流风格的**模型控制面板**弹层：切换模型时可一并切换思考深度与 Fast 模式；`none` 在所有协议路径上真正关闭思考。不照抄参考图，只对齐能力。

## 数据模型

- `GenerationParams` 新增 `reasoningEffort?: ReasoningEffort | null`（`null` = 沿用全局）与 `fastMode?: boolean | null`；随 `ChatOverrides.params` 落盘；助手 `assistantSettings` 同步加两字段。群聊成员级本版不做（v0.820）。
- 后端优先级：会话 `params.reasoningEffort` → 全局 `Settings.reasoningEffort`。

## `none` 的多协议写法

| 协议 | 写法 |
|------|------|
| Chat compat | `thinking: {type: disabled}` + `enable_thinking: false`；不发 `reasoning_effort`（家族声明支持 `none` 时才发 `reasoning_effort: none`） |
| Responses | 不发 `reasoning`（GPT-6 Astra 不接受 `none`） |
| Anthropic | `thinking: {type: disabled}`；不发 `output_config.effort` |
| Gemini | `thinkingConfig.thinkingBudget: 0`；家族不可关思考时 `thinkingLevel: minimal` 并记 adjustment |

`none` 时保留 temperature。

## Fast 模式写法（[OpenAI Fast mode](https://developers.openai.com/api/docs/guides/fast-mode)）

| 协议 | 写法 |
|------|------|
| OpenAI 官方 / Azure Chat+Responses | `service_tier: "fast"`（`priority` 同义）；其他 OpenAI 兼容网关不发送 |
| Anthropic | body `speed: "fast"` + 头 `anthropic-beta: fast-mode-2026-02-01` |
| Gemini | `serviceTier: "priority"` |
| 不支持家族 | 面板开关禁用并显示原因；后端仍收到 `fastMode=true` → `provider_capability_unsupported` fast-fail |

响应回报的 `service_tier`/`serviceTier` 写入 `done.usage.serviceTier`，被降级为 `default` 时徽标提示「Fast 未生效」。

## 面板

- 行「模型」→ 二级面板（可搜索 / 可新建 / 按预设分组）
- 行「思考」→ 开关（关 = `none`；开 = 恢复上次非 none 深度）
- 行「思考深度」→ 极低/低/中/高/极高/最高；不可用档灰显并标原因
- 行「Fast 模式」→ 开关；旁注「约 2× 计费」
- 底部只读摘要：协议与缓存（`resolve-preview`）
- 换模型自动夹紧深度 / 关闭不支持的 Fast，并在面板内一行轻提示
- 入口 pill「Claude Opus 5 · 高」，Fast 开启加闪电图标；移动端底部抽屉

## 验收

```powershell
cd backend
python -m pytest tests/test_reasoning_override.py -q
cd ../frontend
npm run test -- ModelControlPanel
```
