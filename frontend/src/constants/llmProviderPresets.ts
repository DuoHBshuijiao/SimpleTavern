/**
 * LLM API 预设：下拉名称时联动 baseUrl。
 * URL 与各平台 OpenAI 兼容文档核对日期：2026-04-19。
 */

export interface LlmProviderPreset {
  id: string
  label: string
  name: string
  baseUrl: string
  keywords?: string[]
  /** 含 <resource> / <region> 等占位符，需用户替换 */
  requiresManualEdit?: boolean
  hint?: string
}

// https://openrouter.ai/docs
// https://docs.siliconflow.cn/
// https://api-docs.deepseek.com/
// https://platform.moonshot.cn/docs/
// https://platform.minimaxi.com/
// https://ai.google.dev/gemini-api/docs/openai
// https://platform.openai.com/docs
// https://docs.x.ai/docs
// https://docs.mistral.ai/
// https://docs.perplexity.ai/
// https://docs.fireworks.ai/
// https://cloud.tencent.com/document/product/1729/111007
// https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
// https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
// https://learn.microsoft.com/azure/ai-services/openai/how-to/switching-endpoints
// https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html

export const LLM_PROVIDER_PRESETS: LlmProviderPreset[] = [
  {
    id: 'openrouter',
    label: 'OpenRouter',
    name: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    keywords: ['openrouter'],
  },
  {
    id: 'siliconflow',
    label: '硅基流动 SiliconFlow',
    name: '硅基流动',
    baseUrl: 'https://api.siliconflow.cn/v1',
    keywords: ['siliconflow', '硅基'],
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    name: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    keywords: ['deepseek'],
  },
  {
    id: 'moonshot',
    label: '月之暗面 Moonshot',
    name: '月之暗面',
    baseUrl: 'https://api.moonshot.cn/v1',
    keywords: ['moonshot', 'kimi'],
  },
  {
    id: 'minimax',
    label: 'MiniMax',
    name: 'MiniMax',
    baseUrl: 'https://api.minimaxi.com/v1',
    keywords: ['minimax'],
  },
  {
    id: 'google-ai-studio',
    label: 'Google AI Studio（Gemini OpenAI 兼容）',
    name: 'Google AI Studio',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    keywords: ['google', 'gemini', 'generativelanguage'],
  },
  {
    id: 'openai',
    label: 'OpenAI 官方',
    name: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    keywords: ['openai'],
  },
  {
    id: 'xai',
    label: 'xAI Grok',
    name: 'xAI',
    baseUrl: 'https://api.x.ai/v1',
    keywords: ['xai', 'grok'],
  },
  {
    id: 'mistral',
    label: 'Mistral',
    name: 'Mistral',
    baseUrl: 'https://api.mistral.ai/v1',
    keywords: ['mistral'],
  },
  {
    id: 'perplexity',
    label: 'Perplexity',
    name: 'Perplexity',
    baseUrl: 'https://api.perplexity.ai/v1',
    keywords: ['perplexity'],
  },
  {
    id: 'fireworks',
    label: 'Fireworks AI',
    name: 'Fireworks',
    baseUrl: 'https://api.fireworks.ai/inference/v1',
    keywords: ['fireworks'],
  },
  {
    id: 'tencent-hunyuan',
    label: '腾讯混元',
    name: '腾讯混元',
    baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1',
    keywords: ['hunyuan', '混元', 'tencent'],
  },
  {
    id: 'dashscope',
    label: '阿里云百炼 DashScope',
    name: '阿里云百炼',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    keywords: ['dashscope', '百炼', 'aliyun', 'qwen'],
  },
  {
    id: 'zhipu',
    label: '智谱 GLM（国内）',
    name: '智谱',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    keywords: ['zhipu', 'glm', 'bigmodel', '智谱'],
  },
  {
    id: 'azure-openai',
    label: 'Azure OpenAI',
    name: 'Azure OpenAI',
    baseUrl: 'https://<resource>.openai.azure.com/openai/v1',
    keywords: ['azure', 'microsoft'],
    requiresManualEdit: true,
    hint: '将 <resource> 替换为 Azure 门户中的资源名。',
  },
  {
    id: 'aws-bedrock',
    label: 'AWS Bedrock（OpenAI 兼容）',
    name: 'AWS Bedrock',
    baseUrl: 'https://bedrock-mantle.<region>.api.aws/v1',
    keywords: ['bedrock', 'aws', 'amazon'],
    requiresManualEdit: true,
    hint: '将 <region> 替换为区域代码（如 us-east-1）。',
  },
]
