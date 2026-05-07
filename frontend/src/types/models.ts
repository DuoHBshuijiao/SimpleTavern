/**
 * 数据模型类型定义模块
 *
 * 定义应用中使用的所有TypeScript类型和接口，包括聊天、角色、设置等核心数据模型。
 *
 * 主要功能：
 *    - 定义聊天相关类型：ChatRole、ChatMessage、Chat等
 *    - 定义角色相关类型：CharacterCard
 *    - 定义用户身份类型：UserPersona
 *    - 定义设置相关类型：Settings、ApiPreset、GenerationParams等
 *    - 定义群聊相关类型：GroupMemberSettings、ChatOverrides等
 *
 * 主要类型：
 *    - ChatRole: 聊天消息角色类型
 *    - GenerationParams: LLM生成参数
 *    - ChatOverrides: 聊天覆盖设置
 *    - UserPersona: 用户身份
 *    - ApiPreset: API预设配置
 *    - Settings: 应用设置
 *    - CharacterCard: 角色卡片
 *    - ChatMessage: 聊天消息
 *    - GroupMemberSettings: 群聊成员设置
 *    - Chat: 聊天会话
 *
 * 文件关系：
 *    - 被导入：被stores、composables、components、views等模块导入用于类型定义
 *    - 导入：无
 *    - 依赖：无
 *    - 位置：类型定义层，提供全局类型定义
 */

/**
 * 主聊天可编辑/追加的角色（不含 tool，避免客户端伪造工具链）
 */
export type MainChatRole = 'system' | 'user' | 'assistant'

/**
 * 聊天消息角色类型（含 OpenAI 对齐的 tool；主会话正常不应出现 tool）
 */
export type ChatRole = MainChatRole | 'tool'

/**
 * LLM生成参数接口
 *
 * 定义调用LLM API时的生成参数配置。
 *
 * 字段说明：
 *    - model: 模型名称
 *    - temperature: 温度参数，控制输出的随机性（0-2）
 *    - top_p: 核采样参数，控制输出的多样性
 *    - max_tokens: 最大生成token数
 */
export interface GenerationParams {
  model?: string | null
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  /** 上下文总长度限制（token 数），用于裁剪最近消息；实际总限制 = context_size + 角色卡/用户信息/系统提示词 */
  context_size?: number | null
}

export interface DraftHelpSettings {
  /** 草稿助手读取的最近上下文消息条数；空值表示不单独限制，回退到现有上下文逻辑 */
  context_message_limit?: number | null
}

export type WebSearchProvider = 'tavily' | 'bocha'

/** Tavily Search POST /search 可选字段（apiKey 存在全局嵌套） */
export interface WebSearchTavilySettings {
  apiKey?: string
  max_results?: number | null
  search_depth?: string | null
  topic?: string | null
  include_answer?: boolean | string | null
  include_raw_content?: boolean | string | null
  time_range?: string | null
  start_date?: string | null
  end_date?: string | null
  include_domains?: string[] | null
  exclude_domains?: string[] | null
  chunks_per_source?: number | null
  include_images?: boolean | null
  include_image_descriptions?: boolean | null
  include_favicon?: boolean | null
}

/** 博查 POST /v1/web-search */
export interface WebSearchBochaSettings {
  apiKey?: string
  baseUrl?: string
  count?: number | null
  freshness?: string | null
  summary?: boolean | null
  include?: string | null
  exclude?: string | null
}

export interface WebSearchSettings {
  provider: WebSearchProvider
  tavily?: WebSearchTavilySettings
  bocha?: WebSearchBochaSettings
}

/**
 * 聊天覆盖设置接口
 *
 * 定义聊天会话的覆盖设置，用于覆盖全局设置。
 *
 * 字段说明：
 *    - prompt: 自定义提示词
 *    - longTermMemory: 长期记忆内容
 *    - presetId: API预设ID
 *    - pureAiMode: 纯AI模式（不包含用户消息）
 *    - params: LLM生成参数
 *    - memberSettings: 群聊成员设置（仅群聊使用）
 */
/** 会话内绑定的一本世界书及其扫描/插入深度 */
export interface WorldBookAttachment {
  worldBookId: string
  /** 留空或 0 表示使用全局默认扫描深度 */
  scanDepth?: number | null
  insertDepth: number
}

export type SessionSystemPromptMode = 'append' | 'override'
export type MvuMode = 'regex' | 'directive'
export type ChatMvuMode = MvuMode | null
export type GroupMvuPreset = 'off' | 'inherit_member' | 'fork_session'
export type RegexRuleAction = 'remove' | 'replace' | 'extract' | 'extract_and_replace'
export type RegexRuleMatchMode = 'global' | 'first'
export type RegexExtractSource = 'whole_match' | 'capture_group'

export interface ChatContentRegexRule {
  id: string
  name?: string | null
  enabled: boolean
  order: number
  pattern: string
  action: RegexRuleAction
  replacement?: string | null
  matchMode?: RegexRuleMatchMode
  scanDepthOverride?: number | null
  extractSource?: RegexExtractSource
  extractGroupIndex?: number | null
}

export interface ChatOverrides {
  prompt?: string | null
  sessionSystemPromptMode?: SessionSystemPromptMode
  longTermMemory?: string | null
  /** 上下文起点消息ID：设置后仅从该消息开始参与发送上下文 */
  contextStartMessageId?: string | null
  /** 从上下文起点向前额外保留的消息条数（<=1 视为无效） */
  contextStartKeepBeforeMessages?: number | null
  presetId?: string | null
  pureAiMode?: boolean | null
  /** 与 worldBookAttachments 顺序一致，兼容旧数据 */
  worldBookIds?: string[]
  worldBookAttachments?: WorldBookAttachment[]
  /** 从顺序中移除的全局世界书 ID；该会话生成时不再注入这些书 */
  worldBookGlobalExclusions?: string[]
  /** 正文正则默认扫描深度（最近 assistant 消息条数） */
  contentRegexScanDepthDefault?: number
  /** 会话级正文后处理规则 */
  contentRegexRules?: ChatContentRegexRule[]
  /** 会话级规则启用开关（key=全局规则 id），用于各会话独立启停 */
  contentRegexEnabledByRuleId?: Record<string, boolean>
  params: GenerationParams
  draftHelp?: DraftHelpSettings
  memberSettings?: Record<string, GroupMemberSettings>
  tts?: TtsSessionConfig | null
  /** 每隔若干条主会话消息后自动触发助手总结；未设置或 0 表示关闭 */
  autoMemorySummaryEveryN?: number | null
  /** 上次自动总结成功时锚定的主会话最后一条消息 ID */
  lastAutoMemorySummaryAfterMessageId?: string | null
  /** 为 true 时不弹窗直接触发 */
  autoMemorySummarySilent?: boolean
  /** 非静默下拒绝确认后的倍数，下次在 n*tier 条时再问 */
  autoMemorySummaryNextAskTier?: number
  /** @deprecated 会话级 MVU 模型已废弃；全局 settings.mvuModel */
  mvuModel?: string | null
  /** 会话级 MVU 模式覆盖；null 表示继承角色设置 */
  mvuMode?: ChatMvuMode
  /** 会话级 MVU 指令覆盖；空值表示无覆盖 */
  mvuDirective?: string | null
  /** 群聊 MVU 总开关；null/undefined 表示旧档未显式写入 */
  groupMvuEnabled?: boolean | null
  /** 群聊 MVU 锚定成员（须在 memberIds 内） */
  groupMvuAnchorCharacterId?: string | null
  /** fork/沿用快照时的模板成员 */
  groupMvuTemplateCharacterId?: string | null
}

export type AutoReadScope = 'off' | 'assistant_only' | 'user_only' | 'all'
export type TtsProvider = 'minimax' | 'glm' | 'glm_local' | 'qwen3_local' | 'omnivoice_local' | 'openrouter' | 'siliconflow'

export interface ApiPresetVoice {
  voiceId: string
  name: string
  voiceType: string
  promptText?: string | null
  promptAudioPath?: string | null
  instruction?: string | null
}

export interface TtsSessionConfig {
  autoReadScope?: AutoReadScope
  readGapSeconds?: number
  model?: string | null
  voiceByCharacterId?: Record<string, string>
  voiceByPersonaId?: Record<string, string>
  presetId?: string | null
  preprocessEnabled?: boolean
  preprocessModel?: string | null
  preprocessPresetId?: string | null
  /** 后处理目标语言，填入提示词与请求 JSON 的 language 字段；留空则不按语言翻译 */
  preprocessTargetLanguage?: string | null
  injectEmotionTags?: boolean
}

export interface WorldBookEntry {
  id: string
  title: string
  regex: string
  content: string
  enabled: boolean
  orderIndex: number
}

export interface WorldBook {
  id: string
  name: string
  entries: WorldBookEntry[]
  globalActive: boolean
  sessionChatIds: string[]
  createdAt: string
  updatedAt: string
}

/**
 * 用户身份接口
 *
 * 定义用户的身份信息，用于在聊天中标识用户。
 *
 * 字段说明：
 *    - id: 身份唯一标识
 *    - name: 身份名称
 *    - description: 身份描述
 *    - avatar: 头像文件名
 *    - createdAt: 创建时间（ISO格式）
 *    - updatedAt: 更新时间（ISO格式）
 */
export interface UserPersona {
  id: string
  name: string
  description: string
  avatar: string
  createdAt: string
  updatedAt: string
}

/**
 * API预设配置接口
 *
 * 定义LLM API的预设配置，包括基础URL、API密钥和可用模型列表。
 *
 * 字段说明：
 *    - id: 预设唯一标识
 *    - name: 预设名称
 *    - baseUrl: API基础URL
 *    - apiKey: API密钥
 *    - models: 可用模型列表
 */
export interface ApiPreset {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  models: string[]
  presetKind?: string | null
  ttsProvider?: TtsProvider | null
  voiceCatalog?: ApiPresetVoice[]
  ttsGlmLocalRepoPath?: string | null
  ttsGlmLocalPort?: number
  ttsGlmLocalManaged?: boolean
  ttsQwen3LocalRepoPath?: string | null
  ttsQwen3LocalPort?: number
  ttsQwen3LocalManaged?: boolean
  ttsQwen3LocalModelId?: string | null
  ttsQwen3LocalBaseModelId?: string | null
  ttsQwen3LocalVoiceClonePort?: number | null
  ttsQwen3LocalDevice?: string | null
  ttsQwen3LocalDefaultLanguage?: string | null
  ttsOmniVoiceLocalRepoPath?: string | null
  ttsOmniVoiceLocalPort?: number
  ttsOmniVoiceLocalManaged?: boolean
  ttsOmniVoiceLocalModelId?: string | null
  ttsOmniVoiceLocalDevice?: string | null
  ttsOmniVoiceLocalDefaultLanguage?: string | null
}

/**
 * 应用设置接口
 *
 * 定义应用的全局设置，包括LLM配置、API预设、生成默认值等。
 *
 * 字段说明：
 *    - version: 设置版本号
 *    - llm: LLM配置（基础URL、API密钥、默认模型等）
 *    - apiPresets: API预设列表
 *    - generationDefaults: 生成参数默认值
 *    - prompts: 提示词配置
 *    - streamEnabled: 是否启用流式输出
 *    - pureAiMode: 全局纯AI模式
 *    - userPersonas: 用户身份列表
 *    - selectedPersonaId: 当前选中的身份ID
 *    - createdAt: 创建时间（ISO格式）
 *    - updatedAt: 更新时间（ISO格式）
 */
/** 界面色系：统一保持暗色玻璃底，仅替换柔和强调色 */
export const THEME_IDS = ['blue', 'green', 'teal', 'violet', 'amber', 'rose', 'sunset'] as const
export type ThemeId = (typeof THEME_IDS)[number]

export const THEME_OPTIONS: Array<{ label: string; value: ThemeId }> = [
  { label: '雾玫瑰', value: 'rose' },
  { label: '天青蓝', value: 'blue' },
  { label: '鼠尾草', value: 'green' },
  { label: '青碧色', value: 'teal' },
  { label: '雾紫色', value: 'violet' },
  { label: '琥珀色', value: 'amber' },
  { label: '落日紫', value: 'sunset' },
]

const LEGACY_THEME_IDS: Record<string, ThemeId> = {
  dark: 'blue',
  light: 'green',
}

export const REASONING_EFFORT_VALUES = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh'] as const
export type ReasoningEffort = (typeof REASONING_EFFORT_VALUES)[number]

export const REASONING_EFFORT_OPTIONS: Array<{ label: string; value: ReasoningEffort }> = [
  { label: 'none（关闭）', value: 'none' },
  { label: 'minimal（极低）', value: 'minimal' },
  { label: 'low（低）', value: 'low' },
  { label: 'medium（中）', value: 'medium' },
  { label: 'high（高）', value: 'high' },
  { label: 'extra high（极高）', value: 'xhigh' },
]

/** 将旧版 dark/light 与非法值归一为受支持的主题 ID */
export function normalizeThemeId(raw: string | null | undefined): ThemeId {
  if (raw != null && (THEME_IDS as readonly string[]).includes(raw)) return raw as ThemeId
  if (raw != null && raw !== '' && raw in LEGACY_THEME_IDS) {
    return LEGACY_THEME_IDS[raw]!
  }
  return 'rose'
}

/** 将 reasoning effort 归一化为受支持值；兼容历史 extra_high 与布尔开关 */
export function normalizeReasoningEffort(
  raw: unknown,
  legacyThinkingMode?: boolean | null | undefined,
): ReasoningEffort {
  if (typeof raw === 'string') {
    const normalized = raw.trim().toLowerCase().replace(/ /g, '_')
    if (normalized === 'extra_high') return 'xhigh'
    if ((REASONING_EFFORT_VALUES as readonly string[]).includes(normalized)) {
      return normalized as ReasoningEffort
    }
  }
  return legacyThinkingMode ? 'medium' : 'none'
}

export interface Settings {
  version: number
  /** 主题色系，空值或非法值时前端兜底为 rose（雾玫瑰） */
  themeId?: ThemeId | string | null
  llm: {
    baseUrl: string
    apiKey: string
    defaultModel: string
    modelCandidates: string[]
    usedModels: string[]
  }
  apiPresets: ApiPreset[]
  generationDefaults: GenerationParams
  draftHelpDefaults?: DraftHelpSettings
  prompts: {
    globalSystem: string
    globalPrefill: string
    globalPrefillEnabled: boolean
  }
  streamEnabled: boolean
  pureAiMode: boolean
  /** 推理深度档位：none 表示关闭推理，其他档位表示开启推理并设定深度 */
  reasoningEffort?: ReasoningEffort | string | null
  /** 旧版布尔开关，仅用于前端归一化迁移 */
  thinkingMode?: boolean
  userPersonas: UserPersona[]
  selectedPersonaId: string | null
  /** 当前选中的自定义字体文件名，存于 data/fonts，不随备份导出 */
  selectedFont?: string | null
  /** 页面背景图文件名，存于 data/page_backgrounds，不随备份导出 */
  pageBackgroundImage?: string | null
  /** 页面背景图透明度，空值表示按 1 处理 */
  pageBackgroundOpacity?: number | null
  /** 页面背景图模糊半径(px)，空值表示按 0 处理 */
  pageBackgroundBlurPx?: number | null
  /** 是否启用 WebGPU 着色器背景（仅保存开关，不代表运行时设备一定可用） */
  webgpuBackgroundEnabled?: boolean
  /** WebGPU 背景预设元数据，WGSL 文件内容保存在 data/shader_presets */
  webgpuBackgroundPresets?: Array<{
    id: string
    name: string
    wgslFile: string
  }>
  /** 当前活动的 WebGPU 预设 ID（保存后用于默认运行） */
  webgpuBackgroundActivePresetId?: string | null
  /** WebGPU 背景着色器目标帧率（12–120），未设置时前端按 60 处理 */
  webgpuBackgroundTargetFps?: number | null
  /** 聊天窗口内消息文字字号（仅作用于消息气泡内容），不指定则不覆盖 */
  messageFontSize?: number | null
  /** TTS 总开关，默认关闭 */
  ttsEnabled?: boolean
  /** TTS 音频缓存上限（MB） */
  ttsAudioCacheLimitMb?: number
  /** MVU Agent / directive 导入 Agent 专用模型；空则回退 llm.defaultModel 与 modelCandidates */
  mvuModel?: string | null
  /** 主聊天网络搜索（Tavily / 博查）的全局配置；输入区开关状态见 ChatPage */
  webSearch?: WebSearchSettings | null
  worldBookEntryScanDepthDefault?: number
  /** 全局正文正则规则库：所有会话可见 */
  contentRegexRuleLibrary?: ChatContentRegexRule[]
  createdAt: string
  updatedAt: string
}

/**
 * 角色卡片接口
 *
 * 定义角色的完整信息，包括性格、场景、首句等。
 *
 * 字段说明：
 *    - version: 卡片版本号
 *    - id: 角色唯一标识
 *    - name: 角色名称
 *    - description: 角色简介
 *    - personality: 性格/外貌描述
 *    - scenario: 情景/世界观描述
 *    - firstMessage: 首句消息
 *    - exampleDialogue: 示例对话
 *    - systemPrompt: 系统提示词
 *    - avatar: 头像文件名
 *    - createdAt: 创建时间（ISO格式）
 *    - updatedAt: 更新时间（ISO格式）
 *    - extraFirstMessageEntries: 额外首句（chip 为 true 时在编辑区显示为矩形 chip）
 */
export interface ExtraFirstMessageEntry {
  text: string
  chip: boolean
}

export interface CharacterCard {
  version: number
  id: string
  name: string
  description: string
  personality: string
  scenario: string
  firstMessage: string
  exampleDialogue: string
  systemPrompt: string
  avatar: string
  /** 头像展示焦点（百分比，0-100），用于会话内矩形头像定位，不会修改原图像素 */
  avatarFocusX?: number | null
  avatarFocusY?: number | null
  attachedWorldBookIds?: string[]
  extraFirstMessageEntries?: ExtraFirstMessageEntry[]
  mvuEnabled?: boolean
  mvuMode?: MvuMode
  mvuDirective?: string | null
  contentRegexRules?: ChatContentRegexRule[]
  /** 新会话初始状态栏定义：创建会话时自动写入 stateVariables.tables */
  initialStateTables?: StatusTableDef[]
  createdAt: string
  updatedAt: string
}

/**
 * 聊天消息接口
 *
 * 定义聊天中的一条消息，包括内容、角色、发送者信息等。
 *
 * 字段说明：
 *    - version: 消息版本号
 *    - id: 消息唯一标识
 *    - role: 消息角色（system/user/assistant）
 *    - content: 消息内容
 *    - characterId: 群聊中标识发言角色ID（仅assistant消息使用）
 *    - senderPersonaId: 发送者身份ID（用于persona切换后，历史user消息仍显示原发言者）
 *    - senderName: 发送者名称（快照）
 *    - senderAvatar: 发送者头像（快照）
 *    - ts: 时间戳（ISO格式）
 */
export interface ChatMessage {
  version: number
  id: string
  role: ChatRole
  content: string
  images?: ChatImageAttachment[]
  attachments?: AssistantAttachment[]
  characterId?: string | null
  senderPersonaId?: string | null
  senderName?: string | null
  senderAvatar?: string | null
  ts: string
  /** 长期记忆在上一条保存后、本条消息之后被更新；仅最新一条带此标记的消息存在 */
  memoryUpdatedAfterThis?: boolean
  /**
   * 多候选 assistant 正文（与开场/重写多版共用，占位符已替换）；
   * 新一条用户发言前由客户端 PUT 与 generate 落库时清除元数据
   */
  greetingVariants?: string[] | null
  /** 当前选中的变体下标（与 greetingVariants 对齐） */
  greetingVariantIndex?: number | null
  /** 与 greetingVariants 各下标一一对应的思考/推理文（可短于列表则视为空串） */
  greetingVariantReasoningContents?: string[] | null
  /** 与各 greetingVariants 下标一一对应的思考耗时（秒） */
  greetingVariantReasoningDurations?: (number | null)[] | null
  /** 已合成的 TTS 音频文件 UUID */
  ttsAudioAssetId?: string | null
  /** 实际送入 TTS 合成的文本（含后处理/翻译后的朗读稿） */
  ttsAudioSourceText?: string | null
  /** 推理/思考链持久化文本（与后端 reasoningContent 对齐） */
  reasoningContent?: string | null
  /** 推理/思考耗时（秒，浮点，前端展示一位小数） */
  reasoningDurationSec?: number | null
  /** MVU 已消费标记，同一会话最多一条消息持有 */
  mvuProcessed?: boolean
}

export interface ChatImageAttachment {
  id: string
  filename: string
  mimeType: string
  size?: number | null
  width?: number | null
  height?: number | null
  originalName?: string | null
}

export type AssistantAttachmentKind = 'image' | 'text'
export type AssistantAttachmentStorageScope = 'assistant_chat' | 'workspace_session'

export interface AssistantAttachment {
  id: string
  kind: AssistantAttachmentKind
  storageScope: AssistantAttachmentStorageScope
  storageKey: string
  filename: string
  mimeType: string
  size: number
  originalName?: string | null
}

/**
 * 群聊成员设置接口
 *
 * 定义群聊中每个成员的个性化设置，包括模型、参数、参与概率等。
 *
 * 字段说明：
 *    - model: 使用的模型（覆盖全局设置）
 *    - presetId: API预设ID
 *    - temperature: 温度参数（覆盖全局设置）
 *    - top_p: 核采样参数（覆盖全局设置）
 *    - probability: 参与概率（0-1，默认1，用于随机决定是否参与本轮对话）
 *    - includePersonality: 是否包含性格描述
 *    - includeScenario: 是否包含场景描述
 */
export interface GroupMemberSettings {
  model?: string | null
  presetId?: string | null
  temperature?: number | null
  top_p?: number | null
  probability: number
  includePersonality?: boolean
  includeScenario?: boolean
}

/**
 * MVU 状态表格行接口
 * 对应后端 StatusTableRow
 */
export interface StatusTableRow {
  field: string
  cells: Record<string, string>
}

/**
 * MVU 状态表格定义接口
 * 对应后端 StatusTableDef
 */
export interface StatusTableDef {
  name: string
  columns: string[]
  rows: StatusTableRow[]
}

/**
 * MVU 状态变量快照接口
 * 对应后端 StateVariables
 */
export interface StateVariables {
  version: number
  updatedAt: string
  source: 'mvu_agent' | 'chat_assistant'
  tables: StatusTableDef[]
}

/**
 * MVU 工作日志条目接口
 * 对应后端 MvuWorkLogEntry
 */
export interface MvuWorkLogEntry {
  id: string
  chatId: string
  timestamp: string
  eventType: 'triggered' | 'planning' | 'tool_call' | 'commit' | 'error'
  summary: string
  detail?: Record<string, unknown>
}

/**
 * 聊天会话接口
 *
 * 定义一次完整的聊天会话，包括消息列表、设置、成员信息等。
 *
 * 字段说明：
 *    - version: 会话版本号
 *    - id: 会话唯一标识
 *    - characterId: 主角色ID（单聊）或第一个成员ID（群聊）
 *    - title: 会话标题
 *    - messages: 消息列表
 *    - overrides: 覆盖设置
 *    - userPersonaId: 用户身份ID
 *    - isGroup: 是否为群聊
 *    - memberIds: 群聊成员ID列表（仅群聊使用）
 *    - memberSettings: 群聊成员设置映射（characterId -> settings，仅群聊使用）
 *    - groupDelay: 群聊角色间延迟时间（毫秒，仅群聊使用）
 *    - groupSystemInjectDepth: 整段 system 按深度插入时在最后 N 条之前（仅 groupSystemAlwaysAtBottom 为 false 时）
 *    - groupSystemAlwaysAtBottom: 为 true（默认）时整段 system 在首条，不启深度插入
 *    - createdAt: 创建时间（ISO格式）
 *    - updatedAt: 更新时间（ISO格式）
 */
export interface Chat {
  version: number
  id: string
  characterId: string
  title: string
  messages: ChatMessage[]
  overrides: ChatOverrides
  userPersonaId?: string | null
  isGroup: boolean
  memberIds: string[]
  memberSettings: Record<string, GroupMemberSettings>
  groupDelay: number
  groupSystemInjectDepth?: number
  groupSystemAlwaysAtBottom?: boolean
  createdAt: string
  updatedAt: string
  stateVariables?: StateVariables | null
}
