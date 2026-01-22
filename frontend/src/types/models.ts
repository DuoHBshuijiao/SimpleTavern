export type ChatRole = 'system' | 'user' | 'assistant'

export interface GenerationParams {
  model?: string | null
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
}

export interface ChatOverrides {
  prompt?: string | null
  longTermMemory?: string | null
  presetId?: string | null
  pureAiMode?: boolean | null
  params: GenerationParams
  memberSettings?: Record<string, GroupMemberSettings>
}

export interface UserPersona {
  id: string
  name: string
  description: string
  avatar: string
  createdAt: string
  updatedAt: string
}

export interface ApiPreset {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  models: string[]
}

export interface Settings {
  version: number
  llm: {
    baseUrl: string
    apiKey: string
    defaultModel: string
    modelCandidates: string[]
    usedModels: string[]
  }
  apiPresets: ApiPreset[]
  generationDefaults: GenerationParams
  prompts: {
    globalSystem: string
  }
  streamEnabled: boolean
  pureAiMode: boolean
  userPersonas: UserPersona[]
  selectedPersonaId: string | null
  createdAt: string
  updatedAt: string
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
  createdAt: string
  updatedAt: string
}

export interface ChatMessage {
  version: number
  id: string
  role: ChatRole
  content: string
  characterId?: string | null  // 群聊中标识发言角色ID
  // 发送者快照：用于 persona 切换后，历史 user 消息仍显示原发言者
  senderPersonaId?: string | null
  senderName?: string | null
  senderAvatar?: string | null
  ts: string
}

export interface GroupMemberSettings {
  model?: string | null
  presetId?: string | null
  temperature?: number | null
  top_p?: number | null
  probability: number  // 参与概率 0-1，默认1
  includePersonality?: boolean
  includeScenario?: boolean
}

export interface Chat {
  version: number
  id: string
  characterId: string
  title: string
  messages: ChatMessage[]
  overrides: ChatOverrides
  userPersonaId?: string | null
  // 群聊相关字段
  isGroup: boolean
  memberIds: string[]
  memberSettings: Record<string, GroupMemberSettings>  // {characterId: settings}
  groupDelay: number  // 群聊角色间延迟时间（毫秒）
  createdAt: string
  updatedAt: string
}
