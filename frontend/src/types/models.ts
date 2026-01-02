export type ChatRole = 'system' | 'user' | 'assistant'

export interface GenerationParams {
  model?: string | null
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
}

export interface ChatOverrides {
  prompt?: string | null
  presetId?: string | null
  params: GenerationParams
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
  ts: string
}

export interface Chat {
  version: number
  id: string
  characterId: string
  title: string
  messages: ChatMessage[]
  overrides: ChatOverrides
  createdAt: string
  updatedAt: string
}
