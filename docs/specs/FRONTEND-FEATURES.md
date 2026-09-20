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
- 网络搜索开关（需全局配置 Tavily 或博查）。
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

从 `.vue` 模板抽取交互标签（button/input/select/textarea/自定义表单控件/`role` 交互节点）。动态文案可能显示为插值残留；以界面实际文字为准。共 746 条。设置里的「测模型」「测音色」是产品连通性探测，不是自动化测试。

无独立交互控件、未列入下方清单的组件：`App.vue`（根容器）、`StartupIntegrityWatcher.vue`（空模板，经全局通知框确认修复）、`SelectDropdownSurface.vue`（下拉外壳，控件在插槽内）、`WebSearchQuotaSummary.vue`（只读用量展示）、`ModernAvatar.vue`（只读头像）、`AnimatedClipHeight.vue`（尺寸动画壳）。

### `components/AppNotificationHost.vue`

- **button** `确定`
- **button** `取消`
- **button** `确定` （v-if=current.variant === 'danger'）
- **button** `确定`
- **[dialog]** `dialog`

### `components/AvatarCropper.vue`

- **button** `关闭头像设置弹窗`
- **input[type=file]** `file`
- **button** `取消`
- **button** `重新选择` （v-if=imageSrc）
- **button** `保存头像`

### `components/chat/AssistantPanel.vue`

- **button** `更多`
- **button** `关闭`
- **button** `记忆写入`
- **button** `破坏性工具`
- **button** `网络搜索`
- **button** `移除附件`
- **button** `button`
- **textarea** `输入建议或要求 (Ctrl + Enter)...`
- **ModernSelect** `模型...`
- **button** `清空`
- **button** `发送`
- **[button]** `切换到 MVU 工作日志`

### `components/chat/AssistantThread.vue`

- **summary** `查看结果 JSON`
- **button** `button`
- **button** ``预览图片 ${getAttachmentLabel(attachment)}``
- **button** `重写` （v-if=message.role === 'assistant'）
- **button** `编辑`
- **button** `删除`
- **button** `关闭图片预览`
- **[dialog]** ``图片预览：${preview.alt}``

### `components/chat/ChatInput.vue`

- **button** `终止` （v-if=isDraftHelperRunning）
- **button** `保留`
- **button** `重写`
- **button** `放弃`
- **textarea** `textareaAriaLabel`
- **button** `移除图片`
- **button** `暂停`
- **button** `继续轮次`
- **ModernAvatar** `ModernAvatar`
- **button** `写作辅助`
- **button** `帮我写点什么`
- **button** `润色并扩写我的草稿`
- **button** `网络搜索：开启后每次发送启用，直至关闭；需在全局设置配置 Tavily 或博查`
- **button** `选择图片`
- **button** `更多输入选项`
- **button** `网络搜索`
- **button** `选择图片`
- **input[type=file]** `file`
- **button** `button`
- **button** `打开聊天助手`
- **button** `打开 MVU 工作日志` （v-if=mvuStore.isConnected）
- **button** `打开聊天助手`
- **[button]** ``让 ${member.name} 单次回应一条``

### `components/chat/ChatSidebar.vue`

- **button** `+ 新建`
- **ModernAvatar** `ModernAvatar`
- **button** `编辑身份`
- **button** `删除身份`
- **button** `+ 新建`
- **ModernAvatar** `ModernAvatar`
- **button** `编辑角色`
- **button** `删除角色`
- **button** `+ 群聊`
- **button** `新建会话`
- **ModernAvatar** `ModernAvatar`
- **input[type=text]** `input`
- **button** `button`
- **button** `创建分支`
- **button** `重命名会话`
- **button** `删除会话`
- **ModernAvatar** `ModernAvatar`
- **input[type=text]** `input`
- **button** `button`
- **button** `创建副本改为群聊`
- **button** `创建分支`
- **button** `重命名群聊`
- **button** `删除群聊`
- **[button]** `切换侧边栏`

### `components/chat/ForkLineageBanner.vue`

- **button** `跳转到源会话`

### `components/chat/InitialStateEditor.vue`

- **label** `初始状态栏`
- **button** `新建表格`
- **input[type=text]** `表格名称`
- **button** `+列`
- **button** `+行`
- **button** `删除`
- **input[type=text]** `列名`
- **button** `&times;`
- **input[type=text]** `字段`
- **input[type=text]** `col`
- **button** `&times;`

### `components/chat/MessageList.vue`

- **button** `getMessageAvatar(m) ? `预览 ${getMessageLabel(m)} 的头像` : `${getMessageLabel(m)} 头像``
- **button** ``已有 ${getOutgoingFork(m)?.count ?? 0} 个分叉，点击查看``
- **button** `role=menuitem`
- **button** ``预览图片 ${img.originalName || 'chat-image'}``
- **button** ``上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})``
- **button** ``下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})``
- **button** `朗读` （v-if=settingsStore.settings?.ttsEnabled && (m.role === 'assistant' || m.role === 'user') && !m.id.startsWith('local_') && getDisplayContent(m).trim()）
- **button** `分支` （v-if=canForkMessage(m)）
- **button** `重写` （v-if=m.role === 'assistant' && !m.id.startsWith('local_')）
- **button** `编辑`
- **button** `删除`
- **button** `回到底部` （v-if=showScrollToBottom && !isNearBottom）
- **button** `关闭图片预览`
- **[dialog]** ``图片预览：${preview.alt}``

### `components/chat/ModelControlPanel.vue`

- **button** `triggerAriaLabel`
- **label** `label`
- **button** `role=option`
- **button** `思考`
- **button** `button`
- **button** `chip.available ? `思考深度 ${chip.label}` : `思考深度 ${chip.label}：该模型不支持，将自动收敛到最近可用档``
- **button** `Fast 模式 约 2× 计费 ·`
- **[dialog]** `模型控制面板`
- **[radiogroup]** `思考深度`

### `components/chat/MvuCapabilityEditor.vue`

- **label** `MVU 模式`
- **ModernSelect** `选择 MVU 模式...`
- **label** `MVU 指令`
- **textarea** `描述如何从回复中识别状态变化、如何更新状态栏。`
- **button** `新建规则`
- **input[type=text]** `规则名称（可选）`
- **label** `updateRule(idx, { enabled: v })" /> 启用`
- **button** `删除`
- **textarea** `pattern`
- **textarea** `replacement` （v-if=rule.action === 'replace' || rule.action === 'extract_and_replace'）

### `components/chat/MvuPanel.vue`

- **button** `关闭`
- **label** `启用知识图谱`
- **button** `查看知识图谱` （v-if=hasKnowledgeGraph）
- **ModernSelect** `留空则使用默认模型名称与候选回退`
- **[button]** `切换到聊天助手`

### `components/chat/ReasoningBubble.vue`

- **button** `isExpanded ? '收起思考' : '展开思考'`

### `components/chat/StateVariablesBar.vue`

- **button** `MVU 工作日志`

### `components/chat/TtsPlaybackFab.vue`

- **button** `打开 TTS 队列`
- **button** `isPlaying && !audioPaused ? '暂停播放' : '播放'`
- **button** `打开 TTS 队列`
- **button** `isPlaying && !audioPaused ? '暂停播放' : '播放'`
- **button** `终止传输`
- **[region]** `TTS 队列`

### `components/common/CodeViewer.vue`

- **button** `foldedStarts.has(row.lineIndex) ? '展开' : '折叠'` （v-if=row.kind === 'line' && canFold(row.lineIndex)）
- **button** `… 折叠了 行`

### `components/ConfirmPopover.vue`

- **button** `button`
- **[dialog]** `title || message`

### `components/http-log/HttpLogDetailPane.vue`

- **button** `Pretty`
- **button** `Raw JSON`
- **button** `Request`
- **button** `Response`
- **CodeViewer** `CodeViewer`

### `components/http-log/HttpRecordPreview.vue`

- **CodeViewer** `CodeViewer`
- **CodeViewer** `CodeViewer` （v-if=shouldUseCodeViewer(part.text)）
- **CodeViewer** `CodeViewer`

### `components/LlmPresetNameCombobox.vue`

- **input[type=text]** `placeholder`
- **button** `清空`
- **button** `展开供应商列表`
- **label** `label`
- **button** `无缓存 登录 需参数`

### `components/modals/AssistantSettingsModal.vue`

- **button** `关闭聊天助手设置弹窗`
- **label** `温度`
- **input[type=number]** `number`
- **label** `思考深度`
- **button** `Fast 模式 约 2× 计费。不支持的模型会在发送时明确报错。`
- **label** `上下文长度`
- **input[type=number]** `未启用（不限制）`
- **label** `助手读取消息条数上限`
- **input[type=number]** `未限制（仅受服务端硬上限）`
- **label** `助手读取消息 token 上限（估算）`
- **input[type=number]** `未限制`
- **label** `最大工具轮次`
- **input[type=number]** `默认 8`
- **label** `单轮工具数上限`
- **input[type=number]** `未限制`
- **label** `允许网络搜索 开启后聊天助手与工具区助手可调用全局设置里的 Tavily / 博查搜索；MVU Agent 不会挂载此工具。`
- **label** `允许记忆写入 开启后助手可在当前聊天会话中追加或覆盖长期记忆；仅作用于「聊天助手」，工作区助手不可用。`
- **label** `允许破坏性工具 开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。`
- **button** `取消`
- **button** `保存`

### `components/modals/CharacterEditorModal.vue`

- **button** `关闭角色编辑弹窗`
- **ModernAvatar** `ModernAvatar`
- **button** `更换头像`
- **label** `名称 该项参与对话`
- **input[type=text]** `角色名称`
- **label** `简介`
- **textarea** `简短描述`
- **label** `Personality（性格/外貌） 该项参与对话`
- **textarea** `详细设定...`
- **label** `Scenario（情景/世界观） 该项参与对话`
- **textarea** `世界背景...`
- **label** `系统提示词 该项参与对话`
- **textarea** `回复格式要求...`
- **label** `MVU 能力`
- **label** `(character!.mvuEnabled = v)" /> 启用 MVU 管线`
- **label** `首句 支持 占位符 该项参与对话`
- **textarea** `开场白...`
- **label** `额外首句 支持 占位符 该项参与对话`
- **textarea** `其他开场情景...`
- **button** `追加为草稿（保留输入框）`
- **button** `追加为已保存并清空输入`
- **button** `已保存 草稿`
- **button** `从列表移除此条`
- **label** `示例对话 该项参与对话`
- **textarea** `示例对话...`
- **label** `绑定世界书 随角色保存；「角色+世界书」ZIP 导出用此顺序`
- **ModernSelect** `选择世界书加入列表...`
- **button** `加入`
- **button** `上移`
- **button** `下移`
- **button** `移除`
- **button** `button`
- **button** `记忆写入，仅聊天会话中可用`
- **button** `破坏性工具`
- **button** `网络搜索`
- **button** `移除图片附件`
- **button** `button`
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
- **button** `button`
- **input[type=file]** `file`
- **button** `重新选择`
- **label** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `button`
- **input[type=text]** `https://janitorai.com/chats/...`
- **button** `打开并尝试获取`
- **label** `导入后打开该会话`
- **button** `button`
- **input[type=text]** `https://janitorai.com/characters/...`
- **button** `打开并抓取`

### `components/modals/EmbeddedCardConfirmModal.vue`

- **button** `关闭 PNG 内嵌角色卡确认弹窗`
- **label** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `仅使用头像`
- **button** `button`

### `components/modals/ErrorModal.vue`

- **button** `关闭错误提示`
- **button** `button` （v-if=item.action?.type === 'open_settings'）
- **button** `button`

### `components/modals/GroupCreatorModal.vue`

- **button** `关闭群聊创建弹窗`
- **label** `群聊名称`
- **input[type=text]** `新群聊`
- **button** `button`
- **label** `系统提示词注入深度`
- **input[type=number]** `number`
- **button** `button`
- **label** `MVU 来源`
- **ModernAvatar** `ModernAvatar`
- **label** `{ const inc = groupMemberInclusions[c.id] ?? { includePersonality: true, include`
- **button** `取消`
- **button** `创建群聊`

### `components/modals/GroupSettingsModal.vue`

- **button** `关闭群聊设置弹窗`
- **label** `发言延迟 (ms)`
- **input[type=number]** `number`
- **label** `永远在底部（默认）`
- **button** `button`
- **label** `系统提示词注入深度`
- **input[type=number]** `number`
- **button** `button`
- **label** `锚定成员（须在成员列表内）`
- **label** `模板成员（可选，仅作记录）`
- **label** `成员与发言顺序`
- **ModernAvatar** `ModernAvatar`
- **button** `详情设置`
- **button** `取消`
- **button** `保存并应用`

### `components/modals/HttpLogViewerModal.vue`

- **button** `关闭` （v-if=isNarrowPortrait）
- **button** `刷新`
- **button** `复制`
- **button** `清空`
- **button** `关闭` （v-if=!isNarrowPortrait）
- **button** `ERR — stream ms`
- **button** `button` （v-if=selectedId === it.id）

### `components/modals/KnowledgeGraphModal.vue`

- **button** `刷新`
- **button** `新建实体`
- **button** `新建关系`
- **button** `关闭知识图谱弹窗`
- **label** `注入位置`
- **label** `注入深度（从末尾计）` （v-if=injectPositionUi === 'depth'）
- **label** `锚定消息角色` （v-if=injectPositionUi === 'before_last'）
- **button** `添加首个实体`
- **label** `名称`
- **label** `类型 ({ label: t, value: t }))" class="w-full" @select="onEntityTypeSelect" />`
- **label** `属性（每行 键: 值）`
- **button** `保存`
- **button** `取消` （v-if=panelMode === 'view'）
- **button** `删除实体` （v-if=selectedEntity && panelMode === 'view'）
- **button** `删除`
- **label** `主体 { newRelSubject = typeof opt === 'string' ? opt : String(opt.value) }" />`
- **label** `谓语`
- **label** `客体为字面量（非实体）`
- **label** `客体实体 { newRelObject = typeof opt === 'string' ? opt : String(opt.value) }" />` （v-if=!useLiteralObject）
- **label** `客体字面量`
- **button** `保存`
- **button** `取消`

### `components/modals/MemberSettingsModal.vue`

- **button** `关闭成员设置弹窗`
- **ModernAvatar** `ModernAvatar`
- **label** `绑定模型`
- **button** `清除`
- **ModernSelect** `使用全局模型...`
- **label** `Temperature (覆写)`
- **input[type=number]** `使用全局设置`
- **label** `Top P (覆写)`
- **input[type=number]** `使用全局设置`
- **label** `思考深度`
- **label** `Fast 模式`
- **label** `参与概率`
- **input[type=number]** `number`
- **label** `system prompt 插入字段`
- **label** `插入 Personality`
- **label** `插入 Scenario`
- **button** `取消`
- **button** `保存`

### `components/modals/MessageEditorModal.vue`

- **button** `关闭编辑消息弹窗`
- **label** `发送者 / 头像`
- **ModernAvatar** `ModernAvatar`
- **label** `内容`
- **textarea** `输入消息内容（支持 Markdown）`
- **button** `取消`
- **button** `仅保存`
- **button** `保存并发送`

### `components/modals/PersonaEditorModal.vue`

- **button** `关闭身份编辑弹窗`
- **ModernAvatar** `ModernAvatar`
- **button** `更换头像`
- **label** `姓名（ ）`
- **input[type=text]** `你的角色名称`
- **label** `简介`
- **textarea** `你的角色身份、背景等`
- **button** `取消`
- **button** `保存`

### `components/modals/PersonaSwitchConfirmModal.vue`

- **button** `关闭身份切换确认弹窗`
- **button** `取消`
- **button** `仍然继续对话`
- **button** `新建会话`

### `components/modals/PromptCacheGuideModal.vue`

- **button** `关闭教学`
- **label** `输入 token：`
- **button** `button`
- **button** `我了解费用，允许以后在 HTTP 日志里核对 cache 读写（本页不自动发请求）`
- **button** `上一步`
- **button** `button`

### `components/modals/WebGpuShaderEditorModal.vue`

- **button** `关闭`
- **label** `预设名称`
- **input[type=text]** `为此预设命名`
- **WgslMonospaceEditor** `请选择或新建 WebGPU 预设后编辑 WGSL`
- **button** `编译`
- **button** `保存源码`
- **button** `运行（仅本次）`

### `components/modals/WorldBookEditorModal.vue`

- **button** `关闭`
- **label** `书名`
- **input[type=text]** `世界书名称`
- **button** `新增条目`
- **button** `上移`
- **button** `下移`
- **button** `编辑`
- **button** `复制`
- **button** `删除`
- **button** `button`
- **button** `取消`
- **button** `button`

### `components/modals/WorldBookEntryEditModal.vue`

- **button** `关闭`
- **label** `标题`
- **input[type=text]** `条目标题`
- **label** `启用`
- **textarea** `例如 keyword 或 /keyword/iu`
- **textarea** `匹配后注入的文本`
- **textarea** `测试文本`
- **button** `试匹配`
- **button** `取消`
- **button** `确定`

### `components/modals/WorldBookSessionAttachModal.vue`

- **button** `关闭`
- **label** `扫描深度`
- **input[type=text]** `scanPlaceholder()`
- **label** `插入深度`
- **input[type=number]** `number`
- **button** `取消`
- **button** `保存`

### `components/ModernSelect.vue`

- **input[type=text]** `allowCreate ? '搜索或输入新值...' : '搜索...'`

### `components/settings-drawer/LlmConnectionAdvancedSection.vue`

- **label** `供应商参数`
- **a** `官方文档` （v-if=catalogProvider?.docsUrl）
- **label** `label`
- **a** `文档` （v-if=catalogProvider.docsUrl）
- **label** `提示词缓存策略`
- **button** `缓存原理与断点教学`
- **button** `button`
- **button** `在消息上打显式缓存标记（百炼 DashScope 等中国厂商需要）`
- **button** `回传思考内容（reasoning_content） 开：把上一轮 assistant 的思考链一并发回（DeepSeek 带工具调用时 必须 开启）；关：省 t`
- **input[type=text]** `输入模型名预览（如 claude-opus-4-6）`

### `components/settings-drawer/OAuthLoginModal.vue`

- **button** `关闭登录弹窗`
- **label** `GitHub Enterprise 域名（可选）`
- **input[type=text]** `github.com`
- **label** `登录方式`
- **button** `设备码`
- **button** `浏览器粘贴回调`
- **button** `button`
- **a** `打开验证页面` （v-if=verificationUri）
- **a** `打开 ChatGPT 授权页`
- **textarea** `http://localhost:1455/auth/callback?code=…&state=…`
- **button** `取消`
- **button** `开始登录` （v-if=!sessionId）
- **button** `完成登录` （v-else-if=authorizeUrl）

### `components/settings-drawer/SettingsDrawerChatRegexSection.vue`

- **button** `正文正则后处理（规则全局可见，会话独立启用）`
- **label** `默认扫描深度（最近 assistant 条数）`
- **input[type=number]** `number`
- **button** `全部启用`
- **button** `全部禁用`
- **button** `新建规则`
- **button** `编辑`
- **button** `上移`
- **button** `下移`
- **button** `删除`

### `components/settings-drawer/SettingsDrawerChatTab.vue`

- **label** `会话系统提示`
- **button** `追加全局`
- **button** `覆盖全局`
- **textarea** `留空则使用角色默认提示词`
- **label** `长期记忆`
- **button** `从已存记忆处截断`
- **button** `恢复完整上下文`
- **input[type=number]** `N`
- **textarea** `会插入系统提示词，留空则不启用`
- **label** `每隔几条消息自动总结`
- **input[type=number]** `关闭`
- **label** `静默总结`
- **label** `模型覆盖`
- **ModernSelect** `选择模型 (自动关联预设)...`
- **label** `Temperature`
- **input[type=number]** `使用全局`
- **label** `Top P`
- **input[type=number]** `使用全局`
- **label** `最大输出长度`
- **input[type=number]** `使用全局`
- **label** `上下文长度`
- **input[type=number]** `未启用（使用全局）`
- **label** `草稿助手上下文条数限制`
- **input[type=text]** `使用全局；留空则继续回退`
- **label** `{ if (chat.chatDraft) chat.chatDraft.groupMvuEnabled = v }" /> 启用群聊 MVU`
- **label** `锚定成员`
- **label** `模板成员（可选）`
- **label** `{ if (chat.chatDraft) chat.chatDraft.knowledgeGraphEnabled = v }" /> 启用知识图谱`
- **button** `打开图谱`
- **button** `清空图谱` （v-if=chat.mvuStore.hasKnowledgeGraph）

### `components/settings-drawer/SettingsDrawerChatTtsSection.vue`

- **label** `TTS 模型`
- **ModernSelect** `选择 TTS 模型...`
- **button** `button`
- **label** `朗读间隔（秒）`
- **input[type=number]** `number`
- **button** `启用文本后处理`
- **button** `注入英文情绪标签`
- **label** `后处理目标语言`
- **input[type=text]** `例如 简体中文、English（留空则不按语言翻译）`
- **ModernSelect** `选择文本后处理模型...` （v-if=chat.chatDraft.tts?.preprocessEnabled）
- **TtsVoiceInput** `输入或下拉选择 voice_id`

### `components/settings-drawer/SettingsDrawerChatWorldBookSection.vue`

- **button** `新建世界书`
- **input[type=text]** `世界书名称`
- **button** `创建`
- **button** `取消`
- **ModernSelect** `选择世界书加入会话顺序...`
- **button** `加入顺序`
- **button** `button`
- **button** `移除会话`
- **button** `编辑`
- **button** `全部世界书（ 本）`
- **button** `编辑`
- **button** `button`
- **button** `编辑`
- **button** `上移`
- **button** `下移`
- **button** `删除`

### `components/settings-drawer/SettingsDrawerGlobalAccordion.vue`

- **button** `button`

### `components/settings-drawer/SettingsDrawerGlobalAppearanceSection.vue`

- **button** `导入图片`
- **button** `清除` （v-if=draft.pageBackgroundImage）
- **input[type=file]** `file`
- **label** `透明度 % 100% 为完整显示图片，降低后可透出主题底色。`
- **label** `模糊 px 仅作用于图片层，不会影响主题底色与界面内容。`
- **label** `启用着色器背景`
- **button** `button`
- **button** `新建预设`
- **ModernSelect** `ModernSelect`
- **button** `编辑`
- **button** `运行`
- **button** `删除`
- **label** `界面色系`
- **ModernSelect** `选择色系...`
- **ModernSelect** `选择字体...`
- **button** `减小字号`
- **input[type=number]** `number`
- **button** `增大字号`
- **button** `导入字体`
- **input[type=file]** `file`
- **button** `基本设置`
- **button** `包含角色卡`
- **button** `包含全部聊天记录`
- **button** `button`
- **input[type=file]** `file`
- **button** `清除`
- **label** `启用 MVU 兼容 已检测到候选结构`
- **ModernSelect** `选择 MVU 模式`
- **button** `button`

### `components/settings-drawer/SettingsDrawerGlobalAppSection.vue`

- **a** `成本计算器`
- **button** `查看 HTTP 请求`
- **button** `检查更新`
- **a** `a`

### `components/settings-drawer/SettingsDrawerGlobalConnectionSection.vue`

- **label** `流式传输`
- **button** `button`
- **label** `纯 AI 模式`
- **button** `button`
- **label** `思考模式`
- **ModernSelect** `选择思考深度...`
- **label** `回传思考内容`
- **label** `默认 API 基础地址`
- **input[type=text]** `https://api.openai.com 或 …/v1/chat/completions`
- **label** `默认 LLM 协议`
- **label** `默认 API Key`
- **input[type=showApiKeyModel ? 'text' : 'password']** `input`
- **button** `button`
- **label** `默认模型名称`
- **input[type=text]** `例如: gpt-3.5-turbo`
- **label** `MVU Agent 模型`
- **ModernSelect** `留空则使用默认模型名称与候选回退`

### `components/settings-drawer/SettingsDrawerGlobalPromptsSection.vue`

- **label** `全局系统提示词`
- **textarea** `textarea`
- **label** `预填内容`
- **button** `button`
- **textarea** `以助手身份附加在请求末尾，模型在其后续写；留空则不启用`
- **label** `Temperature`
- **input[type=number]** `默认`
- **label** `Top P`
- **input[type=number]** `默认`
- **label** `最大输出长度`
- **input[type=number]** `默认`
- **label** `上下文长度`
- **input[type=number]** `未启用（默认不限制）`
- **label** `草稿助手上下文条数限制`
- **input[type=text]** `未启用（跟随当前逻辑）`

### `components/settings-drawer/SettingsDrawerGlobalTtsSection.vue`

- **label** `启用文字转语音`
- **button** `button`
- **label** `缓存上限（MB）`
- **input[type=number]** `number`
- **button** `清空缓存`

### `components/settings-drawer/SettingsDrawerGlobalWebSearchSection.vue`

- **label** `提供方`
- **ModernSelect** `选择搜索提供方…`
- **label** `Tavily API Key`
- **input[type=password]** `tvly-...`
- **label** `max_results（0–20）`
- **input[type=number]** `number`
- **label** `search_depth`
- **input[type=text]** `basic / advanced / fast …`
- **label** `博查 API Key`
- **input[type=password]** `password`
- **label** `API 根地址`
- **input[type=text]** `https://api.bocha.cn`
- **label** `count（1–50）`
- **input[type=number]** `number`
- **WebSearchQuotaSummary** `WebSearchQuotaSummary`

### `components/settings-drawer/SettingsDrawerModelSelectorModal.vue`

- **button** `关闭模型选择弹窗`
- **input[type=text]** `筛选模型...`
- **button** `取消`
- **button** `确认`
- **[dialog]** `model-selector-title`

### `components/settings-drawer/SettingsDrawerPresetsTab.vue`

- **button** `+ 新建`
- **button** `button`
- **label** `预设名称`
- **button** `作为 TTS 服务`
- **LlmPresetNameCombobox** `输入或下拉选择供应商/预设名称` （v-if=!presets.isTtsPreset(presets.editingPreset)）
- **input[type=text]** `text`
- **label** `TTS 提供商`
- **ModernSelect** `选择 TTS 提供商…`
- **label** `API 基础地址`
- **input[type=text]** `presets.editingPresetBaseUrlPlaceholder`
- **label** `LLM 协议`
- **label** `API Key`
- **input[type=presets.editingPresetShowApiKey ? 'text' : 'password']** `input`
- **button** `button`
- **button** `退出登录` （v-if=presets.oauthStatusFor(presets.editingPreset?.id)?.loggedIn）
- **label** `模型列表`
- **button** `从 API 获取并筛选`
- **button** `全选`
- **button** `清空选择`
- **button** `删除所选`
- **button** `清空全部`
- **button** `移除此模型`
- **label** `仓库路径`
- **input[type=text]** `E:\GLM-TTS（GLM-TTS 仓库根目录）`
- **label** `端口`
- **input[type=number]** `8088`
- **label** `托管启动`
- **button** `button`
- **label** `仓库路径`
- **input[type=text]** `E:\Qwen3-TTS（Qwen3-TTS 仓库根目录）`
- **label** `主端口（CustomVoice 网关）`
- **input[type=number]** `8080`
- **label** `语音克隆端口（Base 网关）`
- **input[type=number]** `留空 = 主端口 + 1`
- **label** `托管启动`
- **button** `button`
- **label** `设备`
- **input[type=text]** `cuda:0`
- **label** `CustomVoice 模型 ID（/custom_voice）`
- **input[type=text]** `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`
- **label** `Base 模型 ID（/voice_clone）`
- **input[type=text]** `Qwen/Qwen3-TTS-12Hz-1.7B-Base`
- **label** `默认语言`
- **input[type=text]** `Auto`
- **label** `仓库路径`
- **input[type=text]** `E:\OmniVoice（OmniVoice 仓库根目录）`
- **label** `端口`
- **input[type=number]** `8089`
- **label** `托管启动`
- **button** `button`
- **label** `模型 ID / 路径`
- **input[type=text]** `k2-fsa/OmniVoice`
- **label** `设备`
- **input[type=text]** `cuda:0（留空则交给 OmniVoice 自动选择）`
- **label** `默认语言`
- **input[type=text]** `例如 zh、Chinese、English（可留空）`
- **label** `音色列表`
- **button** `从 API 获取并筛选` （v-if=presets.editingPresetSupportsVoiceFetch）
- **button** `全选`
- **button** `清空选择`
- **button** `删除所选`
- **button** `清空全部`
- **button** `button`
- **input[type=text]** `音色 ID（唯一标识）`
- **input[type=text]** `音色名称（显示用）`
- **input[type=text]** `参考音频路径（wav/flac 绝对路径）`
- **input[type=text]** `参考音频对应转写文本（推荐填写）`
- **button** `添加音色`
- **input[type=text]** `音色 ID（唯一标识；无参考音频时作为 speaker 传给 custom_voice）`
- **input[type=text]** `显示名称（可选）`
- **input[type=text]** `参考音频路径（wav/flac 绝对路径，语音克隆时填写）`
- **input[type=text]** `参考音频对应转写文本（语音克隆时推荐填写）`
- **input[type=text]** `instruction（可选，仅 custom_voice 模式）`
- **button** `添加音色`
- **input[type=text]** `音色 ID（用于会话里选择）`
- **input[type=text]** `显示名称（可选）`
- **input[type=text]** `参考音频路径（克隆模式，可选）`
- **input[type=text]** `参考音频转写文本（克隆模式，可选）`
- **input[type=text]** `instruction / instruct（音色设计模式，可选）`
- **button** `添加音色`
- **button** `选择参考音频`
- **input[type=file]** `file`
- **input[type=text]** `自定义音色名称（customName）`
- **textarea** `参考音频对应文本（必填）`
- **button** `button`
- **a** `OpenRouter 文档`
- **button** `选择源音频`
- **input[type=file]** `file`
- **input[type=text]** `voice_id`
- **textarea** `presets.editingPresetTtsProvider === 'glm' ? '试听文本（GLM 必填，留空则后端用默认试听文案）' : '试听文本（可选）'`
- **button** `选择示例音频`
- **input[type=file]** `file` （v-if=presets.editingPresetSupportsPromptAudio）
- **input[type=text]** `presets.editingPresetTtsProvider === 'glm' ? '示例音频文本（可选）' : '示例音频对应文本（可选）'`
- **button** `降噪`
- **button** `音量归一`
- **button** `button`
- **textarea** `用自然语言描述想要的声音`
- **textarea** `试听文本`
- **input[type=text]** `voice_id（可选，不填则自动生成）`
- **button** `button`
- **[button]** `button`

### `components/settings-drawer/SettingsDrawerRegexRuleEditorModal.vue`

- **button** `关闭正文正则规则编辑弹窗`
- **label** `规则名称（可选）`
- **input[type=text]** `留空将使用 pattern 前缀`
- **label** `Pattern`
- **textarea** `支持 /pattern/imsu 或普通正则`
- **label** `动作`
- **ModernSelect** `ModernSelect`
- **label** `Replacement`
- **label** `提取来源`
- **ModernSelect** `ModernSelect`
- **label** `提取分组下标`
- **input[type=number]** `默认 1`
- **label** `匹配模式`
- **ModernSelect** `ModernSelect`
- **label** `覆盖扫描深度（可选）`
- **input[type=number]** `留空使用会话默认深度`
- **ThemedRadioTags** `试运行来源`
- **textarea** `输入测试文本（最多 10000 字符）` （v-if=trialSourceMode === 'manual'）
- **button** `试运行`
- **button** `取消`
- **button** `保存`
- **[dialog]** `regex-editor-title`

### `components/settings-drawer/SettingsDrawerVoiceSelectorModal.vue`

- **button** `关闭音色选择弹窗`
- **input[type=text]** `筛选音色（名称、ID、类型）...`
- **button** `取消`
- **button** `确认`
- **[dialog]** `voice-selector-title`

### `components/SettingsDrawer.vue`

- **button** `关闭设置抽屉`
- **button** `button`
- **button** `取消`
- **button** `button`

### `components/StartupUpdateCard.vue`

- **button** `button`
- **button** `更新`

### `components/ThemedCheckbox.vue`

- **button** `ariaLabel`

### `components/ThemedRadioTags.vue`

- **button** `role=radio`
- **[radiogroup]** `ariaLabel`

### `components/TtsVoiceInput.vue`

- **input[type=text]** `placeholder`
- **button** `清空`
- **button** `展开音色列表`
- **button** `button`

### `components/WgslMonospaceEditor.vue`

- **textarea** `placeholder`

### `views/ChatPage.vue`

- **button** `搜索当前会话，快捷键 Ctrl+F 搜索 Ctrl+F` （v-if=!showChatSearch && !holdSearchChipUntilSearchPanelClosed）
- **button** `群聊设置 群聊` （v-if=activeChat.isGroup）
- **button** `设置 设置`
- **button** `更多操作`
- **button** `导出当前会话 聊天记录`
- **button** `导入会话 JSON / 扩展来源`
- **input[type=text]** `搜索当前会话`
- **button** `上一个搜索结果`
- **button** `下一个搜索结果`
- **button** `关闭会话搜索`
- **button** `button`
- **ModernAvatar** `ModernAvatar`
- **button** `导出`
- **button** `导入`
- **button** `设置`
- **button** `创建角色`
- **button** `返回`
- **button** `清除图片重试`
- **[menu]** `更多操作`
- **[search]** `会话内搜索`
- **[dialog]** `image-fallback-title`

