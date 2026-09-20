# SimpleTavern 前端功能与可见控件清单

本文供黑盒测试对照界面行为。应用只有一条用户路由：`/` 与 `/characters` 均重定向到 `/chat`（`ChatPage`）。壳层另有启动完整性提示、启动更新卡片、全局通知/确认框。

无障碍约定：原生 HTML 控件禁止用 `title` 做名称，须用可见文字或 `aria-label` / `aria-labelledby`。

## 功能分区

### 1. 应用壳

- 主题：`data-theme` 跟随全局 `themeId`。
- 自定义字体：全局 `selectedFont`。
- `StartupIntegrityWatcher`：启动数据完整性扫描结果；可提示修复。
- `StartupUpdateCard`：启动约 40 秒后检查新版本；按钮「忽略」「更新」（打开设置更新流程）。
- `AppNotificationHost`：警告对话框与确认对话框；主按钮 / 取消；Esc 关闭；点遮罩关闭。

### 2. 聊天页顶栏

- 打开/关闭侧栏。
- 会话内搜索：打开搜索条、输入关键字、上一个/下一个结果、关闭搜索。
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
- 群聊：新建群聊、选择、重命名、删除、创建分支、「创建副本改为群聊」（从单聊提升）。

### 4. 消息列表

- 消息气泡：Markdown、思考块（展开/收起、思考要点）。
- 头像点击预览；聊天图片预览与关闭。
- 版本切换：上一个/下一个版本。
- 操作：朗读、分叉、重写、编辑、删除（确认）。
- 已有分叉入口：查看子分叉。
- 缓存读/写徽标、Fast 未生效徽标（有 usage 时）。
- 回到底部。

### 5. 输入区

- 多行输入；发送 / 停止生成。
- 移除已选图片；选择图片。
- 网络搜索开关（Tavily/博查，或当前协议为 OpenAI Responses 时走厂商内建 web_search）。
- 更多输入选项。
- 写作辅助：写/润色、停止、保留、重写、放弃。
- 群聊：暂停、继续；成员「单次回应一条」插话。
- 模型控制面板：模型搜索与选择、思考开关、思考深度档位、Fast、解析预览。
- 打开聊天助手；打开 MVU 工作日志。

### 6. 状态栏 / MVU / 助手 / TTS

- 状态栏：展示 MVU 表字段，点击打开 MVU 面板。
- MVU 面板：切到助手、关闭、知识图谱开关、打开知识图谱、工作日志、模型选择、能力/初始状态编辑。
- 助手面板：切到 MVU、更多菜单、关闭、设置、附件移除、发送/停止、重置会话、删除工作区聊天。
- 助手消息：重写、编辑、删除、图片预览。
- TTS 浮层：打开队列、播放/暂停、终止传输、队列列表。

### 7. 设置抽屉

三个 Tab：**全局设置**、**API 预设**、**当前会话**。关闭按钮；底部保存。

全局设置折叠区包括：连接（URL/Key/协议/OAuth 登录、模型、缓存策略、回传思考、解析预览、测模型）、外观（主题、字号增减、字体、页面背景图、透明度/模糊、WebGPU 开关与预设编辑）、提示词、网络搜索（Tavily/博查）、TTS、应用（更新检查/下载/执行、数据完整性、备份导入导出相关）。

API 预设：列表、新建/复制/删除、名称 combobox（供应商目录分组搜索）、模型增删、测模型、OAuth 登录/退出、高级连接字段与缓存教学入口。

当前会话：模型与生成参数覆盖、纯 AI、世界书挂载/排序/全局激活/编辑、正文正则规则开关与编辑/试运行、会话 TTS、群聊延迟与成员入口、知识图谱清空/打开、记忆锚点截断等。

### 8. 弹窗（按出现场景）

- 角色编辑：字段、头像、额外问候、图片附件、记忆写入、MVU 模式/指令、保存/取消。
- 身份编辑：名称、头像、保存/取消。
- 身份切换确认。
- PNG 内嵌角色卡确认：仅用头像 / 导入卡片、是否启用 MVU。
- 群聊创建 / 群设置 / 成员设置（含成员思考深度与 Fast）。
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
- `ConfirmPopover`：就地确认。
- `CodeViewer`：折叠/展开代码行。

## 按文件的可见控件清单

计数规则（供仓库外黑盒点按，一条模板节点算一条；`v-for` 不按运行时行数展开）：

- 计入：`button` / `input` / `textarea` / `select` / `a` / `summary`；`role` 为 button/dialog/menu/search/radiogroup 的壳；自定义表单控件（`ThemedCheckbox`、`ThemedRadioTags`、`ModernSelect`、`LlmPresetNameCombobox`、`TtsVoiceInput`、`WgslMonospaceEditor`、`CodeViewer`）；带 `cursor-pointer` / 遮罩关闭的 `@click` 节点。
- 不计入：纯说明用 `<label>`、只读 `ModernAvatar` / `WebSearchQuotaSummary`、下拉外壳 `SelectDropdownSurface`、根容器与动画壳。已作为按钮计入的节点内部的 `ThemedCheckbox` 不重复计。
- 文案取 `aria-label` / `placeholder` / 可见文字；动态插值以界面实际为准。
- 「测模型」「测音色」是产品连通性探测，不是自动化测试。

共 **649** 条可点/可填控件（旧稿标题写 746，清单机械计数 725；725 含大量非点击 caption `label`，且 7 条因属性里的 `>` 被截断而乱码。649 是按上列规则对当前 `.vue` 模板的引号感知抽取）。

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
- **button** `无缓存 登录 需参数 （地址由参数生成）` （v-for=preset in group.items）

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
- **button** `网络搜索：开启后每次发送启用，直至关闭；Tavily/博查，或 OpenAI Responses 内建搜索`
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

- **button** `+ 新建`
- **button** `编辑身份`
- **button** `删除身份`
- **button** `+ 新建`
- **button** `编辑角色`
- **button** `删除角色`
- **button** `+ 群聊`
- **button** `新建会话`
- **[click:div]** `+ ( 人)` （v-for=c in groupList）
- **[click:div]** `下拉选项` （v-for=c in chatList.filter(chat => !chat.isGroup)）
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

- **button** `getMessageAvatar(m) ? '预览 ${getMessageLabel(m)} 的头像' : '${getMessageLabel(m)} 头像'`
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
- **button** `思考 关 = none`
- **button** `恢复沿用全局`
- **[radiogroup]** `思考深度`
- **button** `chip.available ? '思考深度 ${chip.label}' : '思考深度 ${chip.label}：该模型不支持，将自动收敛到最近可用档'` （v-for=chip in effortChips）
- **button** `Fast 模式 约 2× 计费 · 当前模型不支持`

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
- **ThemedCheckbox** `允许网络搜索 开启后聊天助手与工具区助手可调用全局设置里的 Tavily / 博查搜索；MVU Agent 不会挂载此工具。`
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
- **button** `导出角色 JSON`
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
- **button** `仍然继续对话`
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
- **a** `文档` （v-if=catalogProvider.docsUrl）
- **button** `缓存原理与断点教学`
- **ModernSelect** `选择缓存模式…`
- **ModernSelect** `供应商默认`
- **ModernSelect** `ModernSelect`
- **button** `按钮` （v-for=bp in PROMPT_CACHE_BREAKPOINTS）
- **button** `在消息上打显式缓存标记（百炼 DashScope 等中国厂商需要）`
- **button** `回传思考内容（reasoning_content） 开：把上一轮 assistant 的思考链一并发回（DeepSeek 带工具调用时必须开启）；关：省 token，多数厂商可接受。`
- **ModernSelect** `选择要预览的模型` （v-if=previewModelOptions.length）
- **input[type=text]** `输入模型名预览（如 claude-opus-4-6）`

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

- **ModernSelect** `选择搜索提供方…`
- **input[type=password]** `tvly-...`
- **input[type=number]** `input`
- **input[type=text]** `basic / advanced / fast …`
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
- **button** `从 API 获取并筛选`
- **button** `全选`
- **button** `清空选择`
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
