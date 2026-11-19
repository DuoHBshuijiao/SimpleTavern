# v1.000 外观模式与 DeepSeek 朗读接入调研

2026-11-18。作者已撤销发版前的新功能冻结。以下是两个子代理基于当前实现和公开文档给出的接入建议。阈值、回退及分阶段安排仍属于方案。文件解析和 OCR 暂缓。

## 外观模式

沿用现有七个色系。新增独立的外观设置 `themeMode`，与 `themeId` 分开保存。旧设置和旧备份缺少此字段时保持暗色外观。

| 选项 | 生效规则 |
| --- | --- |
| 跟随系统 | 使用 `prefers-color-scheme`，系统模式变化时更新 |
| 跟随背景亮度 | 使用主界面实际显示的静态图片。L* 达到 58 时使用亮色。中间亮度、无有效图片、图片完全透明、页面背景不可见或 WebGPU 正在绘制时使用暗色 |
| 固定亮色 | 使用亮色 |
| 固定暗色 | 使用暗色 |

图片解码后，在浏览器离屏画布中等比例缩至最长边 64 像素。将 sRGB 转为线性相对亮度，再换算为感知明度 L*。以 alpha 加权的两端各 10% 截尾均值代表整图明度，降低透明区域、少量高光和暗角的影响。L* ≥ 58 使用亮色，其余使用暗色。亮度分数使用图片像素，背景滑块为零时使用暗色。算法在浏览器本地运行。 [相对亮度定义](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html#dfn-relative-luminance) · [Canvas 图片处理规则](https://html.spec.whatwg.org/multipage/canvas.html#drawing-images)

亮度结论可按背景资源及版本缓存。图片解码结束后重新核对当前图片、模式和预览状态，避免快速换图或取消设置后被旧结果覆盖。判定依据是主页面实际采用的静态背景，包含 WebGPU 临时运行对该背景显示状态的影响。若设置草稿能改变全页实际背景，退出或取消时需同步恢复外观。 [背景加载](../../frontend/src/composables/usePageBackground.ts) · [页面的 WebGPU 背景状态](../../frontend/src/views/ChatPage.vue#L276)

让应用根节点、浏览器原生控件、抽屉及传送到 `body` 的弹窗共享一个有效的 `data-color-scheme`，保留 `data-theme` 负责色系。先把内容、面板、气泡、按钮、代码块、边框和焦点的颜色整理成成对的明暗语义变量。亮色模式用有足够覆盖度的浅色面板和深色文字保护正文。色彩验收基于文字与合成后背景的实际对比度，普通文字以 4.5:1、关键控件与图标以 3:1 为目标。检查高亮纯色、雪景、剪影和明暗各半的壁纸，以及默认和高背景不透明度。 [根主题入口](../../frontend/src/App.vue#L40) · [设置主题预览](../../frontend/src/components/SettingsDrawer.vue#L802) · [当前颜色变量](../../frontend/src/styles/variables.css) · [文字对比](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) · [控件对比](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)

建议先落地固定明暗和跟随系统，再加图片判定。用构建产物核对七个色系、弹层、系统切换、快速换图、透明图、读图失败、WebGPU 来回切换、草稿取消、旧备份恢复，以及窄窗口与键盘焦点。

## DeepSeek 朗读

建议 1.0 先接整段朗读。服务端新增独立的 `deepseek` TTS 适配器，使用 Bearer 鉴权向 `POST https://api.deepseek.com/v1/tools/tts` 提交 `text`、`voice_id`、`format: "wav"` 和 `filter_markdown: true`。官方请求没有 `model` 字段，音色是海星 `stella` 和暗潮 `tide`，语种自动识别。现有手动和自动朗读可以复用同一播放队列。边接收模型文字边播放需要另接 WebSocket 和实时音频队列，建议作为后续阶段。 [DeepSeek 语音合成文档](https://api-docs.deepseek.com/zh-cn/guides/tts/) · [现有播放队列](../../frontend/src/composables/useTtsPlaybackQueue.ts#L227)

复用现有预设、角色音色映射、`/api/tts/synthesize`、音频缓存和消息绑定。内置音色目录可在本地展示，实际试听或合成才需要 API Key。设置界面隐藏该供应商不支持的模型、语速以及音色复刻和设计选项。缓存身份应包含预设、供应商、音色及最终朗读稿，保证换音色后不会复用原录音。 [合成路由](../../backend/app/routes/tts.py#L536) · [当前缓存复用判断](../../frontend/src/views/ChatPage.vue#L543)

对实际发出的文本和 UTF-8 JSON 分别校验 10,000 计费字符和 64 KiB 的上限，汉字按 2 个字符计。首版完整收取 WAV 再播，捕获取消、明确断流及 WAV 可检测的截断。空音频、拒绝合成、并发限额、服务繁忙或超时均应给出对应反馈。失败时不写可复用缓存或消息绑定。没有长度信息且连接正常结束的响应，仍需用真实上游样本核对截断检测边界。 [请求限制与错误说明](https://api-docs.deepseek.com/zh-cn/guides/tts/)

先用本地模拟响应核对请求字段、边界长度、分块 WAV、断流、取消、失败无缓存，以及不同供应商和音色的缓存隔离。再用隔离会话核对试听、手动朗读和自动朗读。真实音色、首包延迟与上游异常行为保留为独立实测。
