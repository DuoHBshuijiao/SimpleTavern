# SimpleTavern 前端功能与可见控件清单

本文供黑盒测试对照界面行为。应用只有一条用户路由：`/` 与 `/characters` 均重定向到 `/chat`（`ChatPage`）。壳层另有启动完整性提示、启动更新卡片、全局通知/确认框。

无障碍约定：原生 HTML 控件禁止用 `title` 做名称，须用可见文字或 `aria-label` / `aria-labelledby`。

## 功能分区

### 1. 应用壳

- 主题色系由 `themeId` 选择，明暗模式由 `themeMode` 选择。「跟随背景亮度」仅在当前静态图 L* 达到 58 时用亮色。无有效静态图或 WebGPU 正在显示时用暗色。抽屉、弹窗、通知和原生控件共用根节点外观，设置草稿可实时预览。
- 桌面亮色控件通过底色和留白表达层级。深浅色共用单层键盘焦点轮廓。占位头像在无图、加载或失败时显示名称首字，当前头像图片成功加载后才提供消息头像预览。详见 [桌面亮色主题设计规范](DESKTOP-LIGHT-THEME.md)。
- 自定义字体：全局 `selectedFont`。消息正文另有阅读字体 `readingFont` 和行高 `messageLineHeight`，为空时跟随界面字体和默认行高；代码块保持等宽。
- `StartupIntegrityWatcher`：启动数据完整性扫描结果；可提示修复。
- `StartupUpdateCard`：启动约 40 秒后检查新版本；按钮「忽略」「更新」（打开设置更新流程）。
- `AppNotificationHost`：警告对话框与确认对话框；主按钮 / 取消；Esc 关闭；点遮罩关闭。

### 2. 聊天页顶栏

- 打开/关闭侧栏。
- 群聊切换为单聊时，成员行向上淡出，顶栏随之收矮，消息区的顶部留白同步更新。切回群聊时，顶栏随成员行展开。
- 会话内搜索：打开搜索条、输入关键字、上一个/下一个结果、关闭搜索。跳转后用中性底色标出目标消息，计数显示「当前/总数」；超过后端上限（300 条）时总数显示为「300+」。
- 设置：打开设置抽屉。
- 更多操作菜单（导入、其它入口视布局而定）。
- 窄屏竖屏下部分按钮仅图标 + `sr-only` 文字。
- 分叉血缘横幅：可跳转到源会话。
- 图片粘滞绑定失败对话框：「返回」等。

### 3. 侧栏（身份 / 角色 / 会话 / 群聊）

- 折叠侧栏。
- 身份：新建、选择、编辑、删除（删除需确认）。
- 角色：新建、选择、编辑、删除（删除需确认）。
- 会话：新建、选择、重命名（输入框 + 保存/取消）、删除、创建分支。
- 群聊：新建群聊、选择、重命名、删除、创建分支、「创建副本改为群聊」（从单聊提升）。默认显示前四个群聊，其余可通过省略号展开。

### 4. 消息列表

- 消息气泡：Markdown、思考块（展开/收起、思考要点）。
- 头像点击预览；聊天图片预览与关闭。
- 版本切换：上一个/下一个版本与「重写」同组。切换时只有正文按方向滑入；重写、流式和“减少动态效果”时不滑。
- 操作：朗读、分叉、重写、编辑、删除。鼠标进入消息时显示操作，键盘聚焦时也可操作。生成完成后恢复编辑类操作。末尾未获回复的用户消息可在同一行重试。删除是原地确认：第一次点击变成「确认？」，3 秒后、失焦或按 Esc 复原，再点一次才删除，没有撤销。
- 已有分叉入口：查看子分叉。
- 正文末尾显示输出长度上限和 Fast 未生效等结果状态。空间足够时，消息页脚与工具栏同排显示「XX 上下文  已缓存 XX」。用量默认对齐正文和首个按钮文字，鼠标悬停或键盘聚焦工具栏时向右滑出，离开后归位。大于 10000 的计数换算成 K，保留一位小数。
- 回到底部。
- 进入会话：最后一条放不下时停在它的开头，放得下时贴底；无论从别的会话切换，还是从没有打开会话的状态进入，都不先闪结尾。
- 跟随：流式输出时贴底跟随，向上滚即停止跟随，回到底部后恢复。不生成时内容变高（如图片晚加载），只有本来贴在底部才跟。

### 5. 输入区

- 多行输入从两行正文高度起步，超过两行再随内容增长，达到当前窗口的上限后显示滚动条。两行起始高度给底部卡片及其下沉留出足够体量。输入工具在左，模型和发送 / 停止在右。侧栏展开时，快捷键提示在输入卡片下方居中显示。收起侧栏后，提示随卡片下沉淡出，卡片底部保留留白。
- 移除已选图片；选择图片。
- 聊天输入区的「网络搜索」按钮控制是否联网。来源和第三方供应商在全局「网络搜索」设置中选择。
- 聊天和助手的历史回复把末尾纯链接来源收在右侧「来源 · N 篇」。来源的有无和展开状态不影响消息操作按钮的位置。展开后显示文章标题与站名，缺标题的同站文章用序号区分。相同网址合并，正文内的引用照常显示。
- 更多输入选项。
- 写作辅助：写/润色、终止、保留、重写、放弃。
- 群聊：暂停、继续；成员「单次回应一条」插话。
- 模型控制面板按视口与锚点间的空间限高。搜索始终可见，方向键浏览匹配模型，Enter 选择，Esc 关闭并回焦。「最近使用」最多五个，已选标记优先显示在实际连接组。
- 思考深度保留模型支持的分段按钮。按住已选胶囊时略缩小，胶囊连续跟随指针，松手吸附并保存档位。也可点击或用方向键切换，支持恢复沿用全局。Fast 不可用时显示原因，诊断在 API 预设的「请求预览」中展开。
- 打开聊天助手；打开 MVU 工作日志。

### 6. 状态栏 / MVU / 助手 / TTS

- 状态栏：展示 MVU 表字段，点击打开 MVU 面板。
- MVU 面板：切到助手、关闭、知识图谱开关、打开知识图谱、工作日志、模型选择、能力/初始状态编辑。
- 关闭 MVU 能力后，已有单聊停止注入状态表和发起后台维护请求。群聊按会话的 MVU 开关执行。
- 助手面板：切到 MVU、通过齿轮打开助手设置、关闭、附件移除、发送、重置会话、删除工作区聊天。空态提示当前作用范围内的任务，尚无助手模型时提供「选择助手模型」。角色工作区的空态图标使用主题色。
- 主聊天助手使用面板背景模糊。展开及退场期间隐藏悬浮「助手」和顶栏 Agent 入口，退场后恢复对应入口。
- 主聊天与角色工作区共用助手模型设置。思考深度按已配置连接的实际能力给出档位。桌面分段胶囊可点击、跟手拖动和用方向键切换，窄窗口用下拉。保存才提交档位和继承状态。思考使温度实际失效时保留已填值，Fast 支持时显示计费提示。
- 助手消息：重写、编辑、删除、图片预览。
- TTS 浮层：打开队列、播放/暂停、终止传输、队列列表。
- DeepSeek TTS：已保存的预设可以试听海星与暗潮。在会话内选择预设，为角色和用户身份分配内置音色。手动朗读和新消息自动朗读都在整段 WAV 准备好后使用队列播放。

### 7. 设置抽屉

三个 Tab：**全局设置**、**API 预设**、**当前会话**。关闭按钮；底部保存。

主聊天助手开启时，能容纳两块面板的横屏中，设置从窗口右缘滑动到助手左侧，退出时沿原路径返回。设置遮罩铺满整个窗口，助手面板在遮罩上方可操作。竖屏与宽度不足的窗口依次显示助手和设置。设置真正关闭后恢复先前打开的助手，保留输入草稿和滚动位置。

左右方向键在页签之间移动焦点，Enter 或空格打开对应页签。每次打开抽屉后首次进入某页签从顶部开始，返回已访问的页签时恢复它自己的滚动位置。折叠区的内容退出键盘顺序。

抽屉背景模糊 12px（Tailwind 工具类，构建后生效）。拖动背景透明度或模糊滑块时，页面背景实时跟随未保存的值，遮罩和抽屉淡出，只留正在拖的滑块；松手恢复，取消或关闭抽屉回到已保存的值。

「外观与数据」内依次显示界面与字体、页面背景、高级背景、数据备份与导入。壁纸缩略图与透明度、模糊在宽抽屉内并排，窄抽屉内上下排布。透明度、模糊和消息行高使用同一套细轨、主题色填充、环形滑块和带单位的右侧读数。

全局设置折叠区包括：连接（URL/Key/协议/OAuth 登录、模型、缓存策略、回传思考、解析预览、测模型）、外观（主题、字号增减、字体、阅读字体、消息行高及「恢复默认」、页面背景图、透明度/模糊、WebGPU 开关与预设编辑）、提示词、网络搜索（供应商原生或第三方搜索，配置 Tavily/博查/Brave）、TTS（含缓存巡检错误）、应用（用量与成本摘要、成本计算器外链、更新检查/下载/执行、数据完整性、备份导入导出相关）。定价规则与用量 events API **没有设置页入口**，只能打 API 或改 `pricing_rules.json`。

「连接与默认模型」先显示模型名称和默认连接，随后是对话与思考选项。「网络搜索」选择供应商原生时可按需展开「第三方搜索配置」，供单独使用第三方搜索的 API 预设使用。TTS 的「前往 API 预设」切换到同一抽屉的预设页签，保留全局设置草稿。

API 预设里的「获取模型」使用当前草稿的 API Key。保存设置后才更新预设。OAuth 预设使用对应账号的授权。

连接和模型列表直接显示。原生联网、提示词缓存和回传思考在默认收起的「高级设置」里。错误提示的设置跳转会展开并定位到相关字段。「请求预览」默认收起，展开后查看实际协议、思考深度和缓存，可继续查看技术详情。

API 预设：列表、新建/复制/删除、名称 combobox（供应商目录分组搜索）、模型增删、测模型、OAuth 登录/退出、高级连接字段与缓存教学入口。左栏列表吸附，右栏滚到任意位置都能滚到列表最后一项。协议下拉含 Bedrock Converse 和 Mistral Conversations；鉴权风格选「Google 服务账号（Vertex）」时，密钥框改为多行，粘贴服务账号 JSON，重新打开时私钥显示为占位值。TTS 预设的本地引擎用开关「由程序启动」。切换 TTS 提供商不再弹提示框。

预设列表名称最多显示两行，可用 Tab 聚焦并用 Enter 或空格选择。列表标明「模型服务」或「语音服务」，悬停删除按钮覆盖在卡片上。详情标题显示正在编辑的预设名称，「作为 TTS 服务」放在独立的服务类型行。

当前会话：模型与生成参数覆盖、纯 AI、世界书挂载/排序/全局激活/编辑、正文正则规则开关与编辑/试运行、会话 TTS、群聊延迟与成员入口、知识图谱清空/打开、记忆锚点截断等。「从已存记忆处截断」与「恢复完整上下文」只修改草稿，与会话提示词等改动一起在页脚保存。页脚显示未保存状态，取消可放弃草稿。

当前会话顶部显示会话名称和已保存设置解析出的模型与连接。群聊显示会话默认模型与连接。修改绑定时另列「保存后」。模型与生成参数显示继承来源或会话覆盖值。清空数值恢复沿用全局，写入 `0` 关闭本会话的上下文长度限制。

### 8. 弹窗（按出现场景）

所有弹窗统一用 `<Transition name="modal">`：遮罩和内容分别淡入淡出，根元素不淡；遮罩模糊 6px（Tailwind 工具类）；关闭按钮是图标；Esc 每次只关最上面一层。

- 角色编辑：字段、头像、额外问候、图片附件、记忆写入、MVU 模式/指令、保存/取消。已有角色可导出已保存的 JSON。
- 身份编辑：名称、头像、保存/取消。
- 身份切换确认。
- PNG 内嵌角色卡确认：仅用头像 / 导入卡片、是否启用 MVU。
- 群聊创建 / 群设置 / 成员设置（含成员思考深度与 Fast）。
- 群成员参与概率可以暂时清空或输入超出范围的数值，离开输入框时收敛到 0–1。留空恢复默认的 100%，手输小数保留原精度。概率条可点击和拖动，拖动时连续跟随，松手按 0.05 吸附，方向键同样按 0.05 调整。保存后才更新成员设置。
- 消息编辑。
- 导入 / 导出。
- 世界书编辑与条目编辑、会话挂载编辑。
- 知识图谱：实体/关系可视化与增删。
- 助手设置。
- 错误栈：关闭、复制、按 `action` 跳转设置。
- HTTP 日志查看。
- WebGPU 着色器编辑。
- 头像裁剪。
- 模型多选、音色选择。
- 正文正则规则编辑与试运行。
- Prompt 缓存教学（多步，下一步/关闭）。
- OAuth 登录（设备码/PKCE 粘贴、轮询、取消）。

### 9. 复用控件

- `ThemedCheckbox`：开关，空格/回车切换。
- `ThemedRadioTags`：互斥标签。
- `ModernSelect`：下拉选择。
- `LlmPresetNameCombobox`：供应商搜索、清空、展开。
- `TtsVoiceInput`：音色输入、清空、展开列表。
- `ConfirmPopover`：就地确认（侧栏删除身份、角色、会话仍用它）。
- `InlineConfirmButton`：原地确认按钮（消息删除、助手消息删除）。
- `CodeViewer`：折叠/展开代码行。

## 按文件的可见控件清单

计数规则（供仓库外黑盒点按，一条模板节点算一条；`v-for` 不按运行时行数展开）：

- 计入：`button` / `input` / `textarea` / `select` / `a` / `summary`；`role` 为 button/dialog/menu/search/radiogroup 的壳；自定义表单控件（`ThemedCheckbox`、`ThemedRadioTags`、`ModernSelect`、`LlmPresetNameCombobox`、`TtsVoiceInput`、`WgslMonospaceEditor`、`CodeViewer`）；带 `cursor-pointer` / 遮罩关闭的 `@click` 节点。
- 不计入：纯说明用 `<label>`、只读 `ModernAvatar` / `WebSearchQuotaSummary`、下拉外壳 `SelectDropdownSurface`、根容器与动画壳。已作为按钮计入的节点内部的 `ThemedCheckbox` 不重复计。
- 文案取 `aria-label` / `placeholder` / 可见文字；动态插值以界面实际为准。
- 「测模型」「测音色」是产品连通性探测，不是自动化测试。

**2026-11-07 说明：** v1.000 验收改用精简清单（`docs/tasks/T-814-v1000-release-acceptance.md`），不再逐条点按本节。下面的按文件清单停在 10 月 23 日，之后的界面改动只更新了上面的功能分区，没有逐条重新计数。

共 **659** 条可点/可填控件（旧稿标题写 746，清单机械计数 725；725 含大量非点击 caption `label`，且 7 条因属性里的 `>` 被截断而乱码。649 是 T-806/T-807 批次按上列规则的抽取；本批 T-808 用量摘要 +3、T-809 Brave 输入 +2 → 654；Gemini 搜索来源会话 3 枚 + 全局 2 枚 → **659**）。

无独立交互控件、未列入下方清单的组件：`App.vue`（根容器）、`StartupIntegrityWatcher.vue`（空模板，经全局通知框确认修复）、`SelectDropdownSurface.vue`（下拉外壳，控件在插槽内）、`WebSearchQuotaSummary.vue`（只读用量展示）、`ModernAvatar.vue`（只读头像）、`AnimatedClipHeight.vue`（尺寸动画壳）。

### `components/AppNotificationHost.vue`

- **[click:div]** `点击遮罩关闭`
- **[dialog]** `'app-notify-title-${current.id}'`
- **button** `确定`
- **button** `取消`
- **button** `确定` （v-if=current.variant === 'danger'）
- **button** `确定`

### `components/AvatarCropper.vue`

- **button** `关闭头像设置弹窗`
- **input[type=file]** `input`
- **[click:div]** `点击选择图片 支持 JPG、PNG、GIF、WebP 格式（可拖拽到此区域）` （v-if=!imageSrc）
- **button** `取消`
- **button** `重新选择` （v-if=imageSrc）
- **button** `保存头像`

### `components/ConfirmPopover.vue`

- **[dialog]** `确认` （v-if=show）
- **button** `取消`
- **button** `确认删除`

### `components/LlmPresetNameCombobox.vue`

- **input[type=text]** `placeholder`
- **button** `清空`
- **button** `展开供应商列表`
- **input[type=text]** `搜索供应商`
- **button** 供应商项，三行：厂商名（右侧可带 `登录` 或 `需参数`）、协议和缓存方式标签、地址（无固定地址时显示 `地址由参数生成`）（v-for=preset in group.items）
- 面板 Teleport 到 `body`，不窄于 380px，右边对齐输入框；Esc 只关面板。分组顺序：中国厂商、国际厂商、模型托管平台、聚合网关、需要登录。

### `components/settings-drawer/VertexServiceAccountFields.vue`

鉴权方式是 Google 服务账号时，代替 API Key 输入框。

- 没有账号或点了「更换」：**button** `导入 JSON 文件`，**textarea** `粘贴服务账号 JSON`（粘贴完整 JSON 立即导入）。不是服务账号、缺字段、私钥已被隐去时显示错误，不导入。更换时 **button** `取消` 回到原账号。
- 有账号：**input[readonly]** `服务账号邮箱`，**input[readonly]** `私钥`（只显示「已导入」或「已保存」和密钥 ID 前 8 位，不显示正文），**input** `项目 ID`（默认取 JSON 的 `project_id`，可改），**input** `位置`（JSON 里没有，必填，空着时提示）。项目 ID 和位置只在地址模板含对应占位符时显示，写入 `providerParams`；高级区不再重复显示这两项。

### `components/ModernSelect.vue`

- **[click:div]** `打开选项列表`
- **input[type=text]** `搜索或输入新值 / 搜索`
- **[click:div]** `下拉选项` （v-for=opt in item.options）
- **[click:div]** `下拉选项`

### `components/SettingsDrawer.vue`

- **[click:div]** `点击遮罩关闭`
- **button** `关闭设置抽屉`
- **button** `当前会话` （v-for=t in ['global', 'presets', 'chat']）
- **button** `取消`
- **button** `保存设置`

### `components/StartupUpdateCard.vue`

- **button** `忽略`
- **button** `更新`

### `components/ThemedCheckbox.vue`

- **button** `切换选项`

### `components/ThemedRadioTags.vue`

- **[radiogroup]** `切换选项`
- **button** `按钮` （v-for=(item, idx) in options）

### `components/TtsVoiceInput.vue`

- **input[type=text]** `placeholder`
- **button** `清空`
- **button** `展开音色列表`
- **button** `按钮` （v-for=voice in filteredVoices）

### `components/WgslMonospaceEditor.vue`

- **textarea** `placeholder`

### `components/chat/AssistantPanel.vue`

- **[button]** `切换到 MVU 工作日志`
- **button** `更多`
- **button** `关闭`
- **button** `记忆写入`
- **button** `破坏性工具`
- **button** `网络搜索`
- **button** `移除附件`
- **button** `按钮`
- **textarea** `输入建议或要求 (Ctrl + Enter)...`
- **ModernSelect** `模型...`
- **button** `清空`
- **button** `发送`

### `components/chat/AssistantThread.vue`

- **summary** `查看结果 JSON`
- **button** `按钮` （v-for=attachment in getTextAttachments(message)）
- **button** `'预览图片 ${getAttachmentLabel(attachment)}'` （v-for=attachment in getImageAttachments(message)）
- **button** `重写` （v-if=message.role === 'assistant'）
- **button** `编辑`
- **button** `删除`
- **[dialog]** `'图片预览：${preview.alt}'` （v-for=preview in imagePreviews）
- **button** `关闭图片预览`

### `components/chat/ChatInput.vue`

- **button** `终止` （v-if=isDraftHelperRunning）
- **button** `保留`
- **button** `重写`
- **button** `放弃`
- **textarea** `textareaAriaLabel`
- **button** `移除图片`
- **button** `暂停`
- **button** `继续轮次`
- **[button]** `'让 ${member.name} 单次回应一条'` （v-for=member in groupMembers）
- **button** `写作辅助`
- **button** `帮我写点什么`
- **button** `润色并扩写我的草稿`
- **button** `网络搜索`
- **button** `选择图片`
- **button** `更多输入选项`
- **button** `网络搜索`
- **button** `选择图片`
- **input[type=file]** `input`
- **button** `按钮`
- **button** `打开聊天助手`
- **button** `打开 MVU 工作日志` （v-if=mvuStore.isConnected）
- **button** `打开聊天助手`

### `components/chat/ChatSidebar.vue`

- **button** `+ 新建`（我的身份）
- **button** 当前身份卡。身份浮层与侧栏等宽，从卡片下缘展开，列出全部身份，最多完整显示五张，余项滚动。每张卡片直接提供编辑和删除图标。
- **button** `+ 新建`
- **button** `编辑角色`
- **button** `删除角色`
- **separator** 角色列表与历史会话的分界线，支持拖动和方向键调节。各区独立滚动，滚动条仅在鼠标所在分区显色。
- **分段按钮** `新建会话` 与 `新建群聊`。箭头直接打开群聊创建。
- **会话行** 沿用行内操作胶囊。群聊显示前三枚头像，超出的头像用省略号标识。
- **[button]** `切换侧边栏`

### `components/chat/ForkLineageBanner.vue`

- **button** `跳转到源会话`

### `components/chat/InitialStateEditor.vue`

- **button** `新建表格`
- **input[type=text]** `表格名称`
- **button** `+列`
- **button** `+行`
- **button** `删除`
- **input[type=text]** `列名`
- **button** `×`
- **input[type=text]** `字段`
- **input[type=text]** `col`
- **button** `×`

### `components/chat/MessageList.vue`

- **button** `预览 ${getMessageLabel(m)} 的头像`（当前头像图片加载成功后可用）
- **button** `'已有 ${getOutgoingFork(m)?.count ?? 0} 个分叉，点击查看'`
- **button** `按钮` （v-for=fc in getOutgoingFork(m)?.chats ?? []）
- **button** `'预览图片 ${img.originalName || 'chat-image'}'` （v-for=img in m.images）
- **button** `'上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})'`
- **button** `'下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})'`
- **button** `朗读` （v-if=settingsStore.settings?.ttsEnabled && (m.role === 'assistant' || m.role === 'user') && !m.id.startsWith('local_') && getDisplayContent(m).tr）
- **button** `分支` （v-if=canForkMessage(m)）
- **button** `重写` （v-if=m.role === 'assistant' && !m.id.startsWith('local_')）
- **button** `编辑`
- **button** `删除`
- **button** `回到底部` （v-if=showScrollToBottom && !isNearBottom）
- **[dialog]** `'图片预览：${preview.alt}'` （v-for=preview in imagePreviews）
- **button** `关闭图片预览`

### `components/chat/ModelControlPanel.vue`

- **button** `triggerAriaLabel`
- **input[type=text]** `搜索模型`
- **[dialog]** `模型控制面板`
- **button** `按钮` （v-for=opt in group.options）
- **switch** `思考`
- **button** `恢复沿用全局`
- **[radiogroup]** `思考深度`。
- **radio** `思考深度 ${label}`（当前模型支持的档位，可拖动选中按钮换档）。
- **switch** `Fast 模式`（可用时显示计费倍率）

### `components/chat/MvuCapabilityEditor.vue`

- **ModernSelect** `选择 MVU 模式...`
- **textarea** `描述如何从回复中识别状态变化、如何更新状态栏。`
- **button** `新建规则`
- **input[type=text]** `规则名称（可选）`
- **ThemedCheckbox** `启用`
- **button** `删除`
- **textarea** `pattern`
- **ModernSelect** `选择处理动作...`
- **ModernSelect** `选择匹配模式...`
- **input[type=number]** `覆盖深度(可选)`
- **textarea** `replacement` （v-if=rule.action === 'replace' || rule.action === 'extract_and_replace'）
- **ModernSelect** `选择提取来源...`
- **input[type=number]** `提取分组下标` （v-if=rule.extractSource === 'capture_group'）

### `components/chat/MvuPanel.vue`

- **[button]** `切换到聊天助手`
- **button** `关闭`
- **ThemedCheckbox** `启用知识图谱`
- **button** `查看知识图谱` （v-if=hasKnowledgeGraph）
- **ModernSelect** `留空则使用默认模型名称与候选回退`

### `components/chat/ReasoningBubble.vue`

- **[click:div]** `已思考 秒 已思考 已思考 秒 已思考`

### `components/chat/StateVariablesBar.vue`

- **button** `MVU 工作日志`

### `components/chat/TtsPlaybackFab.vue`

- **button** `打开 TTS 队列`
- **button** `isPlaying && !audioPaused ? '暂停播放' : '播放'`
- **button** `打开 TTS 队列`
- **button** `isPlaying && !audioPaused ? '暂停播放' : '播放'`
- **button** `终止传输`

### `components/common/CodeViewer.vue`

- **button** `foldedStarts.has(row.lineIndex) ? '展开' : '折叠'` （v-if=row.kind === 'line' && canFold(row.lineIndex)）
- **button** `… 折叠了 行`

### `components/http-log/HttpLogDetailPane.vue`

- **button** `Pretty`
- **button** `Raw JSON`
- **button** `Request`
- **button** `Response`
- **CodeViewer** `CodeViewer`

### `components/http-log/HttpRecordPreview.vue`

- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer` （v-if=shouldUseCodeViewer(part.text)）
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer`

### `components/modals/AssistantSettingsModal.vue`

- **button** `关闭聊天助手设置弹窗`
- **input[type=number]** `input`
- **ModernSelect** `沿用全局…`
- **button** `Fast 模式 约 2× 计费。不支持的模型会在发送时明确报错。`
- **input[type=number]** `未启用（不限制）`
- **input[type=number]** `未限制（仅受服务端硬上限）`
- **input[type=number]** `未限制`
- **input[type=number]** `默认 8`
- **input[type=number]** `未限制`
- **ThemedCheckbox** `允许网络搜索 开启后聊天助手与工具区助手可调用全局设置里的 Tavily / 博查 / Brave 搜索；MVU Agent 不会挂载此工具。`
- **ThemedCheckbox** `允许记忆写入 开启后助手可在当前聊天会话中追加或覆盖长期记忆；仅作用于「聊天助手」，工作区助手不可用。`
- **ThemedCheckbox** `允许破坏性工具 开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。`
- **button** `取消`
- **button** `保存`

### `components/modals/CharacterEditorModal.vue`

- **button** `关闭角色编辑弹窗`
- **button** `更换头像`
- **input[type=text]** `角色名称`
- **textarea** `简短描述`
- **textarea** `详细设定...`
- **textarea** `世界背景...`
- **textarea** `回复格式要求...`
- **ThemedCheckbox** `启用 MVU 管线`
- **textarea** `开场白...`
- **textarea** `其他开场情景...`
- **button** `追加为草稿（保留输入框）`
- **button** `追加为已保存并清空输入`
- **button** `已保存 草稿`
- **button** `从列表移除此条`
- **textarea** `示例对话...`
- **ModernSelect** `选择世界书加入列表...`
- **button** `加入`
- **button** `上移`
- **button** `下移`
- **button** `移除`
- **button** `按钮`
- **button** `记忆写入，仅聊天会话中可用`
- **button** `破坏性工具`
- **button** `网络搜索`
- **button** `移除图片附件`
- **button** `按钮`
- **textarea** `输入建议或要求 (Ctrl + Enter)...`
- **ModernSelect** `模型...`
- **button** `发送`
- **button** `导出已保存角色 JSON`（编辑已有角色时显示）
- **button** `取消`
- **button** `保存`

### `components/modals/ChatExportModal.vue`

- **button** `关闭导出弹窗`
- **button** `导出 TXT`
- **button** `导出 JSON`
- **button** `导出 JSONL（精简）`
- **button** `导出角色（JSON）`
- **button** `导出角色+世界书（ZIP）`

### `components/modals/ChatImportModal.vue`

- **button** `关闭导入弹窗`
- **button** `选择文件导入`
- **button** `导入 SillyTavern 数据`
- **input[type=file]** `input`
- **input[type=file]** `input`
- **button** `重新选择`
- **ThemedCheckbox** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `按钮`
- **input[type=text]** `https://janitorai.com/chats/...`
- **button** `打开并尝试获取`
- **ModernSelect** `选择角色`
- **ModernSelect** `选择 Persona`
- **ThemedCheckbox** `导入后打开该会话`
- **button** `确认导入 Janitor 聊天`
- **input[type=text]** `https://janitorai.com/characters/...`
- **button** `打开并抓取`

### `components/modals/EmbeddedCardConfirmModal.vue`

- **button** `关闭 PNG 内嵌角色卡确认弹窗`
- **ThemedCheckbox** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `仅使用头像`
- **button** `按钮`

### `components/modals/ErrorModal.vue`

- **button** `关闭错误提示`
- **button** `打开设置` （v-if=item.action?.type === 'open_settings'）
- **button** `复制错误`

### `components/modals/GroupCreatorModal.vue`

- **button** `关闭群聊创建弹窗`
- **input[type=text]** `新群聊`
- **button** `关闭`
- **button** `关闭`
- **input[type=number]** `input`
- **button** `关闭`
- **ModernSelect** `（未选择）`
- **button** `关闭`
- **ModernSelect** `（请选择）`
- **[click:div]** `暂无简介 system prompt 插入： Personality Scenario` （v-for=c in characters）
- **button** `取消`
- **button** `创建群聊`

### `components/modals/GroupSettingsModal.vue`

- **button** `关闭群聊设置弹窗`
- **input[type=number]** `input`
- **button** `关闭`
- **input[type=number]** `input`
- **button** `关闭`
- **ModernSelect** `选择成员`
- **ModernSelect** `可选`
- **button** `详情设置`
- **button** `取消`
- **button** `保存并应用`

### `components/modals/HttpLogViewerModal.vue`

- **button** `关闭` （v-if=isNarrowPortrait）
- **button** `刷新`
- **button** `复制`
- **button** `清空`
- **button** `关闭` （v-if=!isNarrowPortrait）
- **button** `ERR — stream ms` （v-for=it in items）
- **button** `ERR — stream ms`
- **button** `查看` （v-if=selectedId === it.id）

### `components/modals/KnowledgeGraphModal.vue`

- **button** `刷新`
- **button** `新建实体`
- **button** `新建关系`
- **button** `关闭知识图谱弹窗`
- **ModernSelect** `ModernSelect`
- **input[type=number]** `input`
- **ModernSelect** `ModernSelect`
- **button** `添加首个实体`
- **input[type=text]** `input`
- **ModernSelect** `ModernSelect`
- **textarea** `textarea`
- **button** `保存`
- **button** `取消` （v-if=panelMode === 'view'）
- **button** `删除实体` （v-if=selectedEntity && panelMode === 'view'）
- **button** `删除`
- **ModernSelect** `选择实体`
- **input[type=text]** `如：信任、位于`
- **input[type=checkbox]** `input`
- **ModernSelect** `选择实体`
- **input[type=text]** `input`
- **button** `保存`
- **button** `取消`

### `components/modals/MemberSettingsModal.vue`

- **button** `关闭成员设置弹窗`
- **button** `清除`
- **ModernSelect** `使用全局模型...`
- **input[type=number]** `使用全局设置`
- **input[type=number]** `使用全局设置`
- **ModernSelect** `沿用会话 / 全局…`
- **ModernSelect** `沿用会话 / 全局…`
- **input[type=number]** `input`
- **ThemedCheckbox** `插入 Personality`
- **ThemedCheckbox** `插入 Scenario`
- **button** `取消`
- **button** `保存`

### `components/modals/MessageEditorModal.vue`

- **button** `关闭编辑消息弹窗`
- **[click:div]** `系统`
- **[click:div]** `角色`
- **[click:div]** `用户`
- **textarea** `输入消息内容（支持 Markdown）`
- **button** `取消`
- **button** `仅保存`
- **button** `保存并发送`

### `components/modals/PersonaEditorModal.vue`

- **button** `关闭身份编辑弹窗`
- **button** `更换头像`
- **input[type=text]** `你的角色名称`
- **textarea** `你的角色身份、背景等`
- **button** `取消`
- **button** `保存`

### `components/modals/PersonaSwitchConfirmModal.vue`

- **button** `关闭身份切换确认弹窗`
- **button** `取消`
- **button** `继续对话`
- **button** `新建会话`

### `components/modals/PromptCacheGuideModal.vue`

- **[click:div]** `点击遮罩关闭`
- **button** `关闭教学`
- **input[type=range]** `input`
- **button** `按钮` （v-for=card in MODE_CARDS）
- **button** `现在写入当前预设`
- **button** `我了解费用，允许以后在 HTTP 日志里核对 cache 读写（本页不自动发请求）`
- **button** `上一步`
- **button** `下一步`

### `components/modals/WebGpuShaderEditorModal.vue`

- **button** `关闭`
- **input[type=text]** `为此预设命名`
- **WgslMonospaceEditor** `请选择或新建 WebGPU 预设后编辑 WGSL`
- **[click:li]** `li` （v-for=(d, i) in diagnostics）
- **button** `编译`
- **button** `保存源码`
- **button** `运行（仅本次）`

### `components/modals/WorldBookEditorModal.vue`

- **button** `关闭`
- **input[type=text]** `世界书名称`
- **button** `新增条目`
- **button** `上移`
- **button** `下移`
- **button** `编辑`
- **button** `复制`
- **button** `删除`
- **button** `删除世界书`
- **button** `取消`
- **button** `保存`

### `components/modals/WorldBookEntryEditModal.vue`

- **button** `关闭`
- **input[type=text]** `条目标题`
- **ThemedCheckbox** `启用`
- **textarea** `例如 keyword 或 /keyword/iu`
- **textarea** `匹配后注入的文本`
- **textarea** `测试文本`
- **button** `试匹配`
- **button** `取消`
- **button** `确定`

### `components/modals/WorldBookSessionAttachModal.vue`

- **button** `关闭`
- **input[type=text]** `scanPlaceholder()`
- **input[type=number]** `input`
- **button** `取消`
- **button** `保存`

### `components/settings-drawer/LlmConnectionAdvancedSection.vue`

- **a** `官方文档` （v-if=catalogProvider?.docsUrl）
- **input[type=text]** `ph.example || ph.key`
- **summary** `高级设置`
- **button** `缓存指南`
- **ModernSelect** `选择缓存模式`
- **ModernSelect** `供应商默认`
- **ModernSelect** `缓存范围`（协议支持时显示）
- **checkbox** `缓存断点`（策略支持时显示）
- **switch** `标记要缓存的消息`（供应商支持时显示）
- **switch** `回传思考内容`
- **summary** `请求预览`、`技术详情`
- **ModernSelect** `选择模型`
- **input[type=text]** `输入模型名称`

### `components/settings-drawer/OAuthLoginModal.vue`

- **button** `关闭登录弹窗`
- **input[type=text]** `github.com`
- **button** `设备码`
- **button** `浏览器粘贴回调`
- **button** `复制`
- **a** `打开验证页面` （v-if=verificationUri）
- **a** `打开 ChatGPT 授权页`
- **textarea** `http://localhost:1455/auth/callback?code=…&state=…`
- **button** `取消`
- **button** `开始登录` （v-if=!sessionId）
- **button** `完成登录` （v-if=authorizeUrl）

### `components/settings-drawer/SettingsDrawerChatRegexSection.vue`

- **button** `正文正则后处理（规则全局可见，会话独立启用） 展开`
- **input[type=number]** `input`
- **button** `全部启用`
- **button** `全部禁用`
- **button** `新建规则`
- **ThemedCheckbox** `编辑 上移 下移 删除`
- **button** `编辑`
- **button** `上移`
- **button** `下移`
- **button** `删除`

### `components/settings-drawer/SettingsDrawerChatTab.vue`

- **button** `追加全局`
- **button** `覆盖全局`
- **textarea** `留空则使用角色默认提示词`
- **button** `从已存记忆处截断`
- **button** `恢复完整上下文`
- **input[type=number]** `N`
- **textarea** `会插入系统提示词，留空则不启用`
- **input[type=number]** `关闭`
- **ThemedCheckbox** `静默总结`
- **ModernSelect** `选择模型 (自动关联预设)...`
- **input[type=number]** `使用全局`
- **input[type=number]** `使用全局`
- **input[type=number]** `使用全局`
- **input[type=number]** `未启用（使用全局）`
- **input[type=text]** `使用全局；留空则继续回退`
- **ThemedCheckbox** `启用群聊 MVU`
- **ModernSelect** `选择成员`
- **ModernSelect** `可选`
- **ThemedCheckbox** `启用知识图谱`
- **button** `打开图谱`
- **button** `清空图谱` （v-if=chat.mvuStore.hasKnowledgeGraph）

### `components/settings-drawer/SettingsDrawerChatTtsSection.vue`

- **ModernSelect** `选择 TTS 模型...`
- **button** `按钮` （v-for=option in chat.TTS_AUTO_READ_OPTIONS）
- **input[type=number]** `input`
- **button** `启用文本后处理`
- **button** `注入英文情绪标签`
- **input[type=text]** `例如 简体中文、English（留空则不按语言翻译）`
- **ModernSelect** `选择文本后处理模型...` （v-if=chat.chatDraft.tts?.preprocessEnabled）
- **TtsVoiceInput** `输入或下拉选择 voice_id`
- **TtsVoiceInput** `输入或下拉选择 voice_id`

### `components/settings-drawer/SettingsDrawerChatWorldBookSection.vue`

- **button** `新建世界书`
- **input[type=text]** `世界书名称`
- **button** `创建`
- **button** `取消`
- **ModernSelect** `选择世界书加入会话顺序...`
- **button** `加入顺序`
- **button** `设为全局`
- **button** `移除会话`
- **button** `编辑`
- **button** `全部世界书（ 本） 展开`
- **button** `编辑`
- **button** `收起列表`
- **button** `编辑`
- **button** `上移`
- **button** `下移`
- **button** `删除`

### `components/settings-drawer/SettingsDrawerGlobalAccordion.vue`

- **button** `按钮`

### `components/settings-drawer/SettingsDrawerGlobalAppSection.vue`

- **a** `成本计算器`
- **button** `查看 HTTP 请求`
- **button** `检查更新`
- **a** `…`

### `components/settings-drawer/SettingsDrawerGlobalUsageSummary.vue`

- **button** `刷新`
- **ThemedRadioTags** `用量统计范围`
- **ModernSelect** `选择时间范围…`

### `components/settings-drawer/SettingsDrawerGlobalAppearanceSection.vue`

- **button** `导入图片`
- **button** `清除` （v-if=draft.pageBackgroundImage）
- **input[type=file]** `input`
- **input[type=range]** `input`
- **input[type=range]** `input`
- **button** `已关闭`
- **button** `新建预设`
- **ModernSelect** `ModernSelect`
- **[click:div]** `编辑 运行 删除`
- **ModernSelect** `选择色系...`
- **ModernSelect** `选择字体...`
- **button** `减小字号`
- **input[type=number]** `input`
- **button** `增大字号`
- **button** `导入字体`
- **input[type=file]** `input`
- **button** `基本设置`
- **button** `包含角色卡`
- **button** `包含全部聊天记录`
- **button** `导入数据`
- **button** `仅选择 SillyTavern 角色卡（PNG / JSON）`
- **input[type=file]** `input`
- **input[type=file]** `input`
- **button** `清除`
- **ThemedCheckbox** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `按钮`

### `components/settings-drawer/SettingsDrawerGlobalConnectionSection.vue`

- **button** `已关闭`
- **button** `已关闭：正常对话模式`
- **ModernSelect** `选择思考深度...`
- **ModernSelect** `按预设…`
- **input[type=text]** `https://api.openai.com 或 …/v1/chat/completions`
- **ModernSelect** `选择协议…`
- **input[type=showApiKeyModel ? 'text' : 'password']** `input`
- **button** `按钮`
- **input[type=text]** `例如: gpt-3.5-turbo`
- **ModernSelect** `留空则使用默认模型名称与候选回退`

### `components/settings-drawer/SettingsDrawerGlobalPromptsSection.vue`

- **textarea** `textarea`
- **button** `已关闭：保留文案但暂不生效`
- **textarea** `以助手身份附加在请求末尾，模型在其后续写；留空则不启用`
- **input[type=number]** `默认`
- **input[type=number]** `默认`
- **input[type=number]** `默认`
- **input[type=number]** `未启用（默认不限制）`
- **input[type=text]** `未启用（跟随当前逻辑）`

### `components/settings-drawer/SettingsDrawerGlobalTtsSection.vue`

- **button** `已关闭`
- **input[type=number]** `input`
- **button** `清空缓存`

### `components/settings-drawer/SettingsDrawerGlobalWebSearchSection.vue`

- **button** `原生 Google Search`
- **button** `第三方（Tavily / 博查 / Brave）`
- **ModernSelect** `选择搜索提供方…`
- **input[type=password]** `tvly-...`
- **input[type=number]** `input`
- **input[type=text]** `basic / advanced / fast …`
- **input[type=password]** `BSA...`
- **input[type=number]** `input`
- **input[type=password]** `input`
- **input[type=text]** `https://api.bocha.cn`
- **input[type=number]** `input`

### `components/settings-drawer/SettingsDrawerModelSelectorModal.vue`

- **[click:div]** `点击遮罩关闭`
- **[dialog]** `model-selector-title`
- **button** `关闭模型选择弹窗`
- **input[type=text]** `筛选模型...`
- **[click:div]** `下拉选项` （v-for=m in candidates）
- **button** `取消`
- **button** `确认`

### `components/settings-drawer/SettingsDrawerPresetsTab.vue`

- **button** `+ 新建`
- **[click:div]** `t` （v-for=(presetItem, idx) in presets.globalDraft!.apiPresets）
- **button** `作为 TTS 服务`
- **LlmPresetNameCombobox** `输入或下拉选择供应商/预设名称` （v-if=!presets.isTtsPreset(presets.editingPreset)）
- **input[type=text]** `input`
- **ModernSelect** `选择 TTS 提供商…`
- **input[type=text]** `presets.editingPresetBaseUrlPlaceholder`
- **ModernSelect** `选择协议…`
- **input[type=presets.editingPresetShowApiKey ? 'text' : 'password']** `input`
- **button** `按钮`
- **button** `登录`
- **button** `退出登录` （v-if=presets.oauthStatusFor(presets.editingPreset?.id)?.loggedIn）
- **button** `获取模型`
- **button** `全选`
- **button** `取消选择`
- **button** `删除所选`
- **button** `清空全部`
- **[button]** `下拉选项` （v-for=(m, idx) in presets.editingPreset!.models）
- **button** `移除此模型`
- **input[type=text]** `手动输入模型名...`
- **input[type=text]** `E:\GLM-TTS（GLM-TTS 仓库根目录）`
- **input[type=number]** `8088`
- **button** `手动启动`
- **input[type=text]** `E:\Qwen3-TTS（Qwen3-TTS 仓库根目录）`
- **input[type=number]** `8080`
- **input[type=number]** `留空 = 主端口 + 1`
- **button** `手动启动`
- **input[type=text]** `cuda:0`
- **input[type=text]** `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`
- **input[type=text]** `Qwen/Qwen3-TTS-12Hz-1.7B-Base`
- **input[type=text]** `Auto`
- **input[type=text]** `E:\OmniVoice（OmniVoice 仓库根目录）`
- **input[type=number]** `8089`
- **button** `手动启动`
- **input[type=text]** `k2-fsa/OmniVoice`
- **input[type=text]** `cuda:0（留空则交给 OmniVoice 自动选择）`
- **input[type=text]** `例如 zh、Chinese、English（可留空）`
- **button** `从 API 获取并筛选` （v-if=presets.editingPresetSupportsVoiceFetch）
- **button** `全选`
- **button** `清空选择`
- **button** `删除所选`
- **button** `清空全部`
- **button** `按钮` （v-for=voice in presets.editingPresetVoiceCatalog）
- **input[type=text]** `手动输入 voice_id 后按回车添加…`
- **input[type=text]** `音色 ID（唯一标识）`
- **input[type=text]** `音色名称（显示用）`
- **input[type=text]** `参考音频路径（wav/flac 绝对路径）`
- **input[type=text]** `参考音频对应转写文本（推荐填写）`
- **button** `添加音色`
- **input[type=text]** `参考音频路径`
- **input[type=text]** `参考转写文本`
- **input[type=text]** `音色 ID（唯一标识；无参考音频时作为 speaker 传给 custom_voice）`
- **input[type=text]** `显示名称（可选）`
- **input[type=text]** `参考音频路径（wav/flac 绝对路径，语音克隆时填写）`
- **input[type=text]** `参考音频对应转写文本（语音克隆时推荐填写）`
- **input[type=text]** `instruction（可选，仅 custom_voice 模式）`
- **button** `添加音色`
- **input[type=text]** `显示名称`
- **input[type=text]** `参考音频路径`
- **input[type=text]** `参考转写文本`
- **input[type=text]** `instruction（可选）`
- **input[type=text]** `音色 ID（用于会话里选择）`
- **input[type=text]** `显示名称（可选）`
- **input[type=text]** `参考音频路径（克隆模式，可选）`
- **input[type=text]** `参考音频转写文本（克隆模式，可选）`
- **input[type=text]** `instruction / instruct（音色设计模式，可选）`
- **button** `添加音色`
- **input[type=text]** `显示名称`
- **input[type=text]** `参考音频路径（可选）`
- **input[type=text]** `参考转写文本（可选）`
- **input[type=text]** `instruction / instruct（可选）`
- **button** `选择参考音频`
- **input[type=file]** `input`
- **input[type=text]** `自定义音色名称（customName）`
- **ModernSelect** `TTS 模型（如 FunAudioLLM/CosyVoice2-0.5B）`
- **textarea** `参考音频对应文本（必填）`
- **button** `上传并写入音色`
- **a** `OpenRouter 文档`
- **button** `选择源音频`
- **input[type=file]** `input`
- **input[type=text]** `voice_id`
- **ModernSelect** `presets.editingPresetTtsProvider === 'glm' ? '复刻模型（可选，默认 glm-tts-clone）' : '试听模型（可选）'`
- **textarea** `presets.editingPresetTtsProvider === 'glm' ? '试听文本（GLM 必填，留空则后端用默认试听文案）' : '试听文本（可选）'`
- **button** `选择示例音频`
- **input[type=file]** `input` （v-if=presets.editingPresetSupportsPromptAudio）
- **input[type=text]** `presets.editingPresetTtsProvider === 'glm' ? '示例音频文本（可选）' : '示例音频对应文本（可选）'`
- **button** `降噪`
- **button** `音量归一`
- **button** `复刻并试听`
- **textarea** `用自然语言描述想要的声音`
- **textarea** `试听文本`
- **input[type=text]** `voice_id（可选，不填则自动生成）`
- **button** `生成并试听`

### `components/settings-drawer/SettingsDrawerRegexRuleEditorModal.vue`

- **[dialog]** `regex-editor-title`
- **button** `关闭正文正则规则编辑弹窗`
- **input[type=text]** `留空将使用 pattern 前缀`
- **textarea** `支持 /pattern/imsu 或普通正则`
- **ModernSelect** `ModernSelect`
- **textarea** `支持 $1 / $<name>，保存后会归一化`
- **ModernSelect** `ModernSelect`
- **input[type=number]** `默认 1`
- **ModernSelect** `ModernSelect`
- **input[type=number]** `留空使用会话默认深度`
- **ThemedRadioTags** `试运行来源`
- **textarea** `输入测试文本（最多 10000 字符）` （v-if=trialSourceMode === 'manual'）
- **button** `试运行`
- **button** `取消`
- **button** `保存`

### `components/settings-drawer/SettingsDrawerVoiceSelectorModal.vue`

- **[click:div]** `点击遮罩关闭`
- **[dialog]** `voice-selector-title`
- **button** `关闭音色选择弹窗`
- **input[type=text]** `筛选音色（名称、ID、类型）...`
- **[click:div]** `下拉选项` （v-for=v in candidates）
- **button** `取消`
- **button** `确认`

### `views/ChatPage.vue`

- **button** `搜索当前会话，快捷键 Ctrl+F 搜索 Ctrl+F` （v-if=!showChatSearch && !holdSearchChipUntilSearchPanelClosed）
- **button** `群聊设置 群聊` （v-if=activeChat.isGroup）
- **button** `设置 设置`
- **button** `更多操作`
- **[menu]** `更多操作` （v-if=showHeaderMoreMenu）
- **button** `导出当前会话 聊天记录`
- **button** `导入会话 JSON / 扩展来源`
- **[search]** `会话内搜索` （v-if=showChatSearch）
- **input[type=text]** `搜索当前会话`
- **button** `上一个搜索结果`
- **button** `下一个搜索结果`
- **button** `关闭会话搜索`
- **button** `搜索命中摘要` （v-for=(hit, idx) in chatSearchChipsDisplayHits）
- **[click:div]** `%` （v-for=(member, idx) in groupMembers）
- **button** `导出`
- **button** `导入`
- **button** `设置`
- **button** `创建角色`
- **[click:div]** `点击遮罩关闭`
- **[dialog]** `image-fallback-title`
- **button** `返回`
- **button** `清除图片重试`


### 订阅登录与原生联网（2026-10-22）

- API 预设名录区分「使用 ChatGPT 登录」官方 `openai-chatgpt`、历史 `openai-codex` 和 `xai-oauth`；历史授权不作为新官方机制授权。
- ChatGPT 使用浏览器 PKCE 回环授权，弹窗显示授权页链接并自动等待完成，无需粘贴回调；关闭、取消、切换预设、销毁弹窗取消待处理会话。首次完成订阅授权显示确认提示；缺少订阅权限在账号区明确提示重新授权。
- Grok 使用设备码，默认采用已配置的官方公开客户端，可选提供自己的已注册 xAI 公开 Client ID；不显示 GitHub Enterprise 或 Codex 登录方式。设备码显示复制、验证链接、轮询状态；拒绝、过期和网络错误明确可见。
- ChatGPT 登录弹窗提示在浏览器授权使用订阅额度。登录完成后显示成功状态。
- ChatGPT 订阅用量及「管理用量」入口位于对应的 API 预设。[ChatGPT 用量管理](https://chatgpt.com/settings/usage)
- 账号区「订阅用量」显示真实套餐、额度窗口、已用/剩余百分比、设备本地刷新时间与倒计时。没有官方数据时显示暂无法查询，不推算5小时、周额度或剩余消息数。支持手动「刷新额度」。
- 账号区在可见且页面前台时至多每60秒自动查询；失败保留上次成功数据并标为过期；退出、换号及切换预设清空快照，异步旧请求不覆盖新账号。
- API 预设高级区可设置原生搜索和网页抓取。GPT 使用「搜索与网页读取联动」。联网来源由设置中的「网络搜索」统一管理。聊天和助手各自的联网开关控制是否调用工具。
- 人工核对场景：Plus/Pro真实账号、未授权订阅权限、Grok错误Client ID、取消/拒绝/过期、退出重登、用量缺失/耗尽/请求失败保留快照、跨时区刷新、隐藏页停止自动查询、旧预设联网行为、GPT联动控制、DeepSeek及Claude搜索与抓取。构建通过不表示真实账号链路已验收。

- 点击订阅登录前保存当前预设配置；其余全局设置草稿保持待保存。DeepSeek等应用工具循环的联网状态在生成中显示「网络搜索中/完成/失败」「网页读取中/完成/失败」。
