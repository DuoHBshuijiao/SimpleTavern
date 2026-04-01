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

export interface ChatOverrides {
  prompt?: string | null
  longTermMemory?: string | null
  /** 上下文起点消息ID：设置后仅从该消息开始参与发送上下文 */
  contextStartMessageId?: string | null
  presetId?: string | null
  pureAiMode?: boolean | null
  /** 与 worldBookAttachments 顺序一致，兼容旧数据 */
  worldBookIds?: string[]
  worldBookAttachments?: WorldBookAttachment[]
  /** 从顺序中移除的全局世界书 ID；该会话生成时不再注入这些书 */
  worldBookGlobalExclusions?: string[]
  params: GenerationParams
  draftHelp?: DraftHelpSettings
  memberSettings?: Record<string, GroupMemberSettings>
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
export const THEME_IDS = ['blue', 'green', 'teal', 'violet', 'amber', 'rose'] as const
export type ThemeId = (typeof THEME_IDS)[number]

export const THEME_OPTIONS: Array<{ label: string; value: ThemeId }> = [
  { label: '蓝色（默认）', value: 'blue' },
  { label: '绿色（鼠尾草）', value: 'green' },
  { label: '青碧色', value: 'teal' },
  { label: '雾紫色', value: 'violet' },
  { label: '琥珀色', value: 'amber' },
  { label: '雾玫瑰', value: 'rose' },
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
  return 'blue'
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
  /** 主题色系，空值或非法值时前端兜底为 blue */
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
  /** 聊天窗口内消息文字字号（仅作用于消息气泡内容），不指定则不覆盖 */
  messageFontSize?: number | null
  worldBookEntryScanDepthDefault?: number
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
  characterId?: string | null
  senderPersonaId?: string | null
  senderName?: string | null
  senderAvatar?: string | null
  ts: string
  /** 长期记忆在上一条保存后、本条消息之后被更新；仅最新一条带此标记的消息存在 */
  memoryUpdatedAfterThis?: boolean
  /** 单聊开场白多版本（占位符已替换）；开始对话后由服务端清除 */
  greetingVariants?: string[] | null
  /** 当前选中的开场变体下标（与 greetingVariants 对齐） */
  greetingVariantIndex?: number | null
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
  createdAt: string
  updatedAt: string
}
