"""
数据模型定义模块

本模块定义了应用中使用的所有Pydantic数据模型，包括：
- 设置相关模型（Settings, SettingsLLM, SettingsPrompts等）
- 角色相关模型（CharacterCard）
- 聊天相关模型（Chat, ChatMessage, ChatOverrides等）
- 用户Persona模型（UserPersona）
- API预设模型（ApiPreset）
- 请求/响应模型（CreateChatRequest, GenerateStreamRequest等）

主要类：
    - GenerationParams: 生成参数配置
    - SettingsPrompts: 提示词设置
    - SettingsLLM: LLM配置
    - ApiPreset: API预设配置
    - UserPersona: 用户Persona
    - Settings: 全局设置
    - AssistantSettings: AI助手设置
    - AssistantSettingsUpdate: AI助手设置部分更新（PUT 合并用）
    - AssistantChat: AI助手聊天记录
    - CharacterCard: 角色卡片
    - ChatMessage: 聊天消息
    - ChatOverrides: 聊天覆盖设置
    - GroupMemberSettings: 群聊成员设置
    - Chat: 聊天会话
    - CreateChatRequest: 创建聊天请求
    - AppendMessageRequest: 追加消息请求
    - UpdateMessageRequest: 更新消息请求
    - UpdateChatRequest: 更新聊天请求
    - GenerateStreamRequest: 流式生成请求
    - GroupGenerateRequest: 群聊生成请求
    - SingleInterjectRequest: 单次插话请求

文件关系：
    - 被导入：被storage.py、main.py和所有routes模块导入
    - 导入：仅导入标准库和第三方库（pydantic、datetime、uuid等）
    - 依赖：无依赖其他应用模块
    - 位置：基础数据模型层，是整个应用的数据结构基础
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.regex_compat import compile_user_regex


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
TtsProvider = Literal["minimax", "glm", "glm_local", "qwen3_local", "omnivoice_local"]


class ReasoningRequestConfig(TypedDict):
    effort: ReasoningEffort
    thinking_enabled: bool
    extra_body: dict[str, Any]


def normalize_reasoning_effort(raw: Any) -> ReasoningEffort:
    """
    归一化 reasoning effort 字段，兼容历史/别名值。
    """
    if isinstance(raw, str):
        normalized = raw.strip().lower().replace(" ", "_")
        if normalized == "extra_high":
            return "xhigh"
        if normalized in {"none", "minimal", "low", "medium", "high", "xhigh"}:
            return normalized  # type: ignore[return-value]
    return "none"


def build_reasoning_request_config(settings: "Settings") -> ReasoningRequestConfig:
    """
    从设置构建统一的推理请求配置（开关 + extra_body）。
    """
    effort = normalize_reasoning_effort(getattr(settings, "reasoningEffort", "none"))
    thinking_enabled = effort != "none"
    return {
        "effort": effort,
        "thinking_enabled": thinking_enabled,
        "extra_body": {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
            "reasoning": {"effort": effort},
            "reasoning_effort": effort,
        },
    }


def _model_name_contains_gemini_keyword(model: str | None) -> bool:
    """当前所选模型 ID/名称是否含 gemini（不区分大小写）。用于与需特殊裁剪请求体的 Gemini 家族对齐。"""
    if not model:
        return False
    return "gemini" in model.strip().lower()


# 与 OpenAI/Anthropic 等兼容的思考扩展字段；名称含 gemini 的模型在 Google 托管的 OpenAI 兼容层上会整段拒绝
_REASONING_EXTRA_BODY_KEYS_INCOMPATIBLE_WITH_GEMINI = frozenset({"thinking", "reasoning", "reasoning_effort"})


def filter_reasoning_extra_body_for_upstream(model: str | None, extra_body: dict[str, Any]) -> dict[str, Any]:
    """
    按所选模型裁剪 extra_body：名称含 \"gemini\" 时不发送 thinking/reasoning/reasoning_effort，
    否则会 400（Unknown name \"thinking\" / \"reasoning\"）。不按 baseURL 判断，避免同一网关下非 Gemini 模型被误伤。
    """
    if not _model_name_contains_gemini_keyword(model):
        return extra_body
    return {k: v for k, v in extra_body.items() if k not in _REASONING_EXTRA_BODY_KEYS_INCOMPATIBLE_WITH_GEMINI}


def _now_iso() -> str:
    """
    获取当前时间的ISO格式字符串
    
    Returns:
        str: 当前时间的ISO格式字符串，包含时区信息
    """
    return datetime.now().astimezone().isoformat()


class GenerationParams(BaseModel):
    """
    生成参数配置模型
    
    用于配置LLM生成时的参数，包括模型、温度、top_p、最大token数等。
    支持通过extra="allow"允许额外字段。
    
    主要属性：
        model: 使用的模型名称
        temperature: 温度参数，范围0.0-2.0，控制输出的随机性
        top_p: 核采样参数，范围0.0-1.0，控制输出的多样性
        max_tokens: 最大生成token数，至少为1
    """
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    context_size: int | None = Field(default=None, ge=0, description="上下文总长度限制(token)，0或空表示未启用；长期记忆+最近消息<=此值")


class DraftHelpSettings(BaseModel):
    """草稿助手专用设置。"""
    model_config = ConfigDict(extra="allow")

    context_message_limit: int | None = Field(
        default=None,
        ge=0,
        description="草稿助手读取的最近上下文消息条数；0或空表示不单独限制，回退到现有上下文逻辑",
    )


class SettingsPrompts(BaseModel):
    """
    提示词设置模型
    
    用于存储全局系统提示词配置。
    
    主要属性：
        globalSystem: 全局系统提示词，会注入到所有对话中
        globalPrefill: 全局 Prefill，以 assistant 身份附加在请求末尾供模型续写；不通过 SSE 展示，也不写入已保存消息
    """
    model_config = ConfigDict(extra="allow")

    globalSystem: str = ""
    globalPrefill: str = ""
    globalPrefillEnabled: bool = True


class SettingsLLM(BaseModel):
    """
    LLM配置模型
    
    用于配置LLM API的连接信息和模型选择。
    
    主要属性：
        baseUrl: API基础URL，默认为OpenAI官方API
        apiKey: API密钥
        defaultModel: 默认使用的模型名称
        modelCandidates: 候选模型列表
        usedModels: 已使用的模型列表
    """
    model_config = ConfigDict(extra="allow")

    baseUrl: str = "https://api.openai.com"
    apiKey: str = ""
    defaultModel: str = ""
    modelCandidates: list[str] = Field(default_factory=list)
    usedModels: list[str] = Field(default_factory=list)


class ApiPreset(BaseModel):
    """
    API预设配置模型
    
    用于存储API预设配置，允许用户保存多组不同的API配置。
    
    主要属性：
        id: 预设唯一标识符，自动生成
        name: 预设名称
        baseUrl: API基础URL
        apiKey: API密钥
        models: 该预设关联的模型列表
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新预设"
    baseUrl: str = "https://api.openai.com"
    apiKey: str = ""
    models: list[str] = Field(default_factory=list)
    presetKind: str | None = Field(default=None, description="预设用途；'tts' 表示 TTS 服务预设")
    ttsProvider: TtsProvider | None = Field(default=None, description="TTS 服务提供商；仅当 presetKind='tts' 时有意义")
    voiceCatalog: list["ApiPresetVoice"] = Field(default_factory=list)
    ttsGlmLocalRepoPath: str | None = Field(default=None, description="GLM-TTS 仓库根目录（glm_local 专用）")
    ttsGlmLocalPort: int = Field(default=8088, description="GLM-TTS 本地 API 端口（glm_local 专用）")
    ttsGlmLocalManaged: bool = Field(default=False, description="是否由应用托管 GLM-TTS 子进程（glm_local 专用）")
    ttsQwen3LocalRepoPath: str | None = Field(default=None, description="Qwen3-TTS 仓库根目录（qwen3_local 专用）")
    ttsQwen3LocalPort: int = Field(default=8080, description="Qwen3-TTS 本地 FastAPI 网关端口（qwen3_local 专用）")
    ttsQwen3LocalManaged: bool = Field(default=False, description="是否由应用托管 Qwen3-TTS 子进程（qwen3_local 专用）")
    ttsQwen3LocalModelId: str | None = Field(
        default="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        description="Qwen3-TTS CustomVoice 网关模型 ID（POST /v1/tts/custom_voice；qwen3_local 专用）",
    )
    ttsQwen3LocalBaseModelId: str | None = Field(
        default="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        description="Qwen3-TTS Base 网关模型 ID（POST /v1/tts/voice_clone；第二端口子进程；qwen3_local 专用）",
    )
    ttsQwen3LocalVoiceClonePort: int | None = Field(
        default=None,
        description="语音克隆专用网关端口，默认为主端口+1；须与主端口不同（qwen3_local 专用）",
    )
    ttsQwen3LocalDevice: str | None = Field(default="cuda:0", description="Qwen3-TTS 启动 device（qwen3_local 专用）")
    ttsQwen3LocalDefaultLanguage: str | None = Field(
        default="Auto",
        description="Qwen3-TTS 默认 language 参数（qwen3_local 专用）",
    )
    ttsOmniVoiceLocalRepoPath: str | None = Field(default=None, description="OmniVoice 仓库根目录（omnivoice_local 专用）")
    ttsOmniVoiceLocalPort: int = Field(default=8089, description="OmniVoice 本地 FastAPI 网关端口（omnivoice_local 专用）")
    ttsOmniVoiceLocalManaged: bool = Field(default=False, description="是否由应用托管 OmniVoice 子进程（omnivoice_local 专用）")
    ttsOmniVoiceLocalModelId: str | None = Field(
        default="k2-fsa/OmniVoice",
        description="OmniVoice 启动模型 ID 或本地路径（omnivoice_local 专用）",
    )
    ttsOmniVoiceLocalDevice: str | None = Field(default="cuda:0", description="OmniVoice 启动 device（omnivoice_local 专用）")
    ttsOmniVoiceLocalDefaultLanguage: str | None = Field(
        default=None,
        description="OmniVoice 默认 language 参数（omnivoice_local 专用）",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_tts_kind(cls, data: Any) -> Any:
        """兼容旧版 minimax 标识，统一迁移到 tts + ttsProvider。"""
        if not isinstance(data, dict):
            return data
        incoming = dict(data)
        preset_kind = incoming.get("presetKind")
        provider = incoming.get("ttsProvider")
        if preset_kind == "minimax":
            incoming["presetKind"] = "tts"
            if provider in (None, ""):
                incoming["ttsProvider"] = "minimax"
        elif preset_kind == "tts" and provider in (None, ""):
            incoming["ttsProvider"] = "minimax"
        return incoming


class ApiPresetVoice(BaseModel):
    """API 预设内缓存的可选 TTS 音色条目。"""

    model_config = ConfigDict(extra="allow")

    voiceId: str
    name: str
    voiceType: str = "system"
    promptText: str | None = Field(
        default=None,
        description="参考音频对应的转写文本（glm_local / omnivoice_local / qwen3_local 语音克隆专用）",
    )
    promptAudioPath: str | None = Field(
        default=None,
        description="参考音频本机绝对路径（glm_local / omnivoice_local / qwen3_local 语音克隆专用）",
    )
    instruction: str | None = Field(default=None, description="Qwen3 / OmniVoice 的 instruction / instruct 文本")


class UserPersona(BaseModel):
    """
    用户Persona模型
    
    用于定义用户的身份和特征，在对话中会注入到系统提示词中。
    
    主要属性：
        id: Persona唯一标识符，自动生成
        name: 用户名称
        description: 用户描述
        avatar: 头像文件名
        createdAt: 创建时间，ISO格式
        updatedAt: 更新时间，ISO格式
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新用户"
    description: str = ""
    avatar: str = ""
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class WebGpuBackgroundPreset(BaseModel):
    """
    WebGPU 背景预设元数据。

    仅保存元数据，WGSL 源文件本体存于 data/shader_presets。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新建 WebGPU 预设"
    wgslFile: str


class ShaderPresetDiagnosticItem(BaseModel):
    """WGSL 诊断条目（与前端 WgslDiagnostic 对齐；服务端无编译器时通常为空列表）。"""

    severity: Literal["error", "warning", "info"] = "error"
    message: str
    line: int | None = None
    column: int | None = None
    length: int | None = None


class ShaderPresetMutationResponse(BaseModel):
    """创建/保存着色器预设后的统一响应（含可扩展 diagnostics 占位）。"""

    ok: bool = True
    filename: str
    normalized: bool = True
    diagnostics: list[ShaderPresetDiagnosticItem] = Field(default_factory=list)
    note: str | None = Field(
        default="服务端仅做规范化与存储校验，WGSL 语法编译诊断以浏览器 WebGPU 为准。",
    )


class Settings(BaseModel):
    """
    全局设置模型
    
    应用的全局配置，包括LLM配置、API预设、生成参数默认值、提示词设置等。
    
    主要属性：
        version: 设置版本号
        llm: LLM配置
        apiPresets: API预设列表
        generationDefaults: 生成参数默认值
        prompts: 提示词设置
        streamEnabled: 是否启用流式传输
        pureAiMode: 纯AI模式，启用后不注入用户Persona，用户发言映射为system角色
        userPersonas: 用户Persona列表
        selectedPersonaId: 当前选中的Persona ID
        createdAt: 创建时间
        updatedAt: 更新时间
    """
    model_config = ConfigDict(extra="allow")

    version: int = 1
    llm: SettingsLLM = Field(default_factory=SettingsLLM)
    apiPresets: list[ApiPreset] = Field(default_factory=list)
    generationDefaults: GenerationParams = Field(default_factory=GenerationParams)
    draftHelpDefaults: DraftHelpSettings = Field(default_factory=DraftHelpSettings)
    prompts: SettingsPrompts = Field(default_factory=SettingsPrompts)
    streamEnabled: bool = True
    themeId: str | None = None
    pureAiMode: bool = False
    reasoningEffort: ReasoningEffort = "none"  # 统一思考档位，none 时关闭，其余档位开启
    userPersonas: list[UserPersona] = Field(default_factory=list)
    selectedPersonaId: str | None = None
    selectedFont: str | None = None  # 当前选中的自定义字体文件名，存于 data/fonts，不随备份导出
    pageBackgroundImage: str | None = None  # 页面背景图文件名，存于 data/page_backgrounds
    pageBackgroundOpacity: float | None = Field(default=None, ge=0.0, le=1.0)  # 背景图透明度；None 表示前端按 1 处理
    pageBackgroundBlurPx: float | None = Field(default=None, ge=0.0, le=64.0)  # 背景图模糊半径(px)；None 表示前端按 0 处理
    webgpuBackgroundEnabled: bool = False
    webgpuBackgroundPresets: list[WebGpuBackgroundPreset] = Field(default_factory=list)
    webgpuBackgroundActivePresetId: str | None = None
    webgpuBackgroundTargetFps: int = Field(default=60, ge=12, le=120)  # WebGPU 背景着色器目标帧率
    messageFontSize: int | None = None  # 聊天窗口内消息文字字号（仅作用于消息气泡内容）
    ttsEnabled: bool = False
    ttsAudioCacheLimitMb: int = Field(default=200, ge=10, le=10000)
    worldBookEntryScanDepthDefault: int = 2
    contentRegexRuleLibrary: list["ChatContentRegexRule"] = Field(default_factory=list)
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_thinking_mode(cls, data: Any) -> Any:
        """
        兼容旧版 thinkingMode 布尔配置，统一迁移到 reasoningEffort。
        """
        if not isinstance(data, dict):
            return data
        incoming = dict(data)
        if incoming.get("reasoningEffort") is None:
            legacy = bool(incoming.pop("thinkingMode", False))
            incoming["reasoningEffort"] = "medium" if legacy else "none"
        else:
            incoming["reasoningEffort"] = normalize_reasoning_effort(incoming.get("reasoningEffort"))
            incoming.pop("thinkingMode", None)
        return incoming


class AssistantSettings(BaseModel):
    """
    AI助手设置模型
    
    用于配置AI助手的行为参数。系统提示词由仓库内 app/assistant/AGENT.md 在运行时加载，
    不再使用本字段参与推理；prompt 键可仍存在于旧版 JSON 中，已废弃。
    API 的 GET/PUT 响应中不包含 prompt。
    
    主要属性：
        prompt: 已废弃（推理用 AGENT.md）；历史数据可能仍含该键
        temperature: 温度参数，范围0.0-2.0
        model: 使用的模型名称
        presetId: 关联的API预设ID
    """
    model_config = ConfigDict(extra="allow")

    prompt: str = ""
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model: str | None = None
    presetId: str | None = None
    context_size: int | None = Field(default=None, ge=0, description="上下文总长度限制(token)，0或空表示未启用；最近消息裁剪用")
    tool_read_max_messages: int | None = Field(
        default=None,
        ge=1,
        description="助手 chat_read_conversation 最多返回的消息条数；空表示仅受服务端硬上限约束",
    )
    tool_read_max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="助手 chat_read_conversation 返回消息列表的最大 token 数（估算）；空表示不启用",
    )
    maxToolTurns: int | None = Field(
        default=8,
        ge=1,
        description="助手单次请求内允许的最大工具轮次数；空时回退默认值 8",
    )
    maxToolsPerTurn: int | None = Field(
        default=None,
        ge=1,
        description="单轮 assistant.tool_calls 最大允许执行数；空表示不额外限制",
    )


class AssistantSettingsUpdate(BaseModel):
    """
    AI 助手设置部分更新（PUT 请求体）。

    未在 JSON 中出现的字段表示不修改；与已有 AssistantSettings 合并后保存。
    prompt 已废弃（系统提示见 app/assistant/AGENT.md）；若仍传入会写入 JSON 但不影响推理。
    """
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model: str | None = None
    presetId: str | None = None
    context_size: int | None = Field(default=None, ge=0, description="上下文总长度限制(token)，0或空表示未启用；最近消息裁剪用")
    tool_read_max_messages: int | None = Field(
        default=None,
        ge=1,
        description="助手 chat_read_conversation 最多返回的消息条数；空表示仅受服务端硬上限约束",
    )
    tool_read_max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="助手 chat_read_conversation 返回消息列表的最大 token 数（估算）；空表示不启用",
    )
    maxToolTurns: int | None = Field(
        default=None,
        ge=1,
        description="助手单次请求内允许的最大工具轮次数；空表示不修改",
    )
    maxToolsPerTurn: int | None = Field(
        default=None,
        ge=1,
        description="单轮 assistant.tool_calls 最大允许执行数；空表示不修改/不限制",
    )


class AssistantChat(BaseModel):
    """
    AI助手聊天记录模型
    
    用于存储AI助手的对话历史。
    
    主要属性：
        messages: 消息列表
    """
    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage] = Field(default_factory=list)


AssistantAttachmentKind = Literal["image", "text"]
AssistantAttachmentStorageScope = Literal["assistant_chat", "workspace_session"]


class AssistantAttachment(BaseModel):
    """助手消息中的附件元数据。"""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: AssistantAttachmentKind
    storageScope: AssistantAttachmentStorageScope
    storageKey: str
    filename: str
    mimeType: str
    size: int
    originalName: str | None = None


class ExtraFirstMessageEntry(BaseModel):
    """额外首句条目：chip 为 True 时在编辑界面显示为矩形 chip。"""

    model_config = ConfigDict(extra="allow")

    text: str = ""
    chip: bool = True


RegexAction = Literal["remove", "replace", "extract", "extract_and_replace"]
RegexMatchMode = Literal["global", "first"]
RegexExtractSource = Literal["whole_match", "capture_group"]

MvuStateSource = Literal["mvu_agent", "chat_assistant"]
MvuWorkLogEventType = Literal["triggered", "planning", "tool_call", "commit", "error"]


class ChatContentRegexRule(BaseModel):
    """会话正文后处理规则。"""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str | None = None
    enabled: bool = True
    order: int = 0
    pattern: str = ""
    action: RegexAction = "remove"
    replacement: str | None = None
    matchMode: RegexMatchMode = "global"
    scanDepthOverride: int | None = Field(default=None, ge=1)
    extractSource: RegexExtractSource = "whole_match"
    extractGroupIndex: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_regex_if_enabled(self):
        if not self.enabled:
            return self
        pattern = (self.pattern or "").strip()
        if not pattern:
            return self
        try:
            compile_user_regex(pattern)
        except re.error as e:
            raise ValueError(f"invalid regex: {e}") from e
        if self.extractSource == "capture_group" and self.extractGroupIndex is None:
            self.extractGroupIndex = 1
        return self


class CharacterCard(BaseModel):
    """
    角色卡片模型
    
    用于定义AI角色的完整信息，包括名称、描述、性格、场景等。
    
    主要属性：
        version: 版本号
        id: 角色唯一标识符，自动生成
        name: 角色名称
        description: 角色描述
        personality: 角色性格
        scenario: 场景设定
        firstMessage: 首条消息
        exampleDialogue: 示例对话
        systemPrompt: 系统提示词
        avatar: 头像文件名
        createdAt: 创建时间
        updatedAt: 更新时间
    """
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新角色"
    description: str = ""
    personality: str = ""
    scenario: str = ""
    firstMessage: str = ""
    exampleDialogue: str = ""
    systemPrompt: str = ""
    avatar: str = ""
    avatarFocusX: float | None = None
    avatarFocusY: float | None = None
    attachedWorldBookIds: list[str] = Field(default_factory=list)
    extraFirstMessageEntries: list[ExtraFirstMessageEntry] = Field(default_factory=list)
    mvuEnabled: bool = False
    contentRegexRules: list[ChatContentRegexRule] = Field(default_factory=list)
    initialStateTables: list[StatusTableDef] = Field(
        default_factory=list,
        description="新会话初始状态栏定义：创建会话时自动写入 chat.stateVariables.tables，source=chat_assistant",
    )
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class WorldBookEntry(BaseModel):
    """条目不再包含扫描/插入深度；深度由会话 ChatOverrides.worldBookAttachments 提供。"""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    regex: str = ""
    content: str = ""
    enabled: bool = True
    orderIndex: int = 0

    @model_validator(mode="after")
    def _validate_regex_if_needed(self):
        if not self.enabled:
            return self
        pattern = (self.regex or "").strip()
        if not pattern:
            return self
        try:
            compile_user_regex(pattern)
        except re.error as e:
            raise ValueError(f"invalid regex: {e}") from e
        return self


class WorldBook(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    entries: list[WorldBookEntry] = Field(default_factory=list)
    globalActive: bool = False
    sessionChatIds: list[str] = Field(default_factory=list)
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


ChatRole = Literal["system", "user", "assistant", "tool"]
"""
聊天消息角色类型

支持四种角色：
    - system: 系统消息
    - user: 用户消息
    - assistant: AI助手消息
    - tool: 工具返回（OpenAI Chat Completions 对齐；主会话正常对话不应写入）
"""

MainChatRole = Literal["system", "user", "assistant"]
"""主聊天、追加/更新消息等路径允许的角色（不含 tool，避免客户端伪造工具链）。"""


class ChatMessage(BaseModel):
    """
    聊天消息模型
    
    表示单条聊天消息，支持单聊和群聊场景。
    
    主要属性：
        version: 版本号
        id: 消息唯一标识符，自动生成
        role: 消息角色（system/user/assistant/tool）
        content: 消息内容
        characterId: 群聊中标识发言角色ID
        senderPersonaId: 发送者Persona ID，用于切换身份后保持历史消息显示
        senderName: 发送者名称快照
        senderAvatar: 发送者头像快照
        ts: 时间戳，ISO格式
    """
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    role: ChatRole
    content: str
    images: list["ChatImageAttachment"] = Field(default_factory=list)
    attachments: list["AssistantAttachment"] = Field(default_factory=list)
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    ts: str = Field(default_factory=_now_iso)
    greetingVariants: list[str] | None = None
    greetingVariantIndex: int | None = Field(
        default=None,
        description="当前选中的开场/候选正文变体下标（与 greetingVariants 对齐）；避免仅靠 content 反推在重复文案时错位",
    )
    greetingVariantReasoningContents: list[str] | None = Field(
        default=None,
        description="与各 greetingVariants 下标一一对应的思考/推理原文（可短于列表时视为尾部为空串）",
    )
    greetingVariantReasoningDurations: list[float | None] | None = Field(
        default=None,
        description="与各 greetingVariants 下标一一对应的思考耗时（秒）；可短于列表时视为尾部为 None",
    )
    toolTrace: bool = False
    toolRecord: dict[str, Any] | None = None
    tool_call_id: str | None = Field(
        default=None,
        description="当 role=tool 时对应 assistant.tool_calls[].id（OpenAI tool_call_id）",
    )
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None,
        description="当 role=assistant 且本轮需调用工具时，与 OpenAI 返回结构兼容（id/type/function）",
    )
    reasoningContent: str | None = Field(
        default=None,
        description="推理/思考链文本（与上游 reasoning_content 对应，持久化用）",
    )
    reasoningDurationSec: float | None = Field(
        default=None,
        description="推理/思考耗时（秒，浮点，前端展示为一位小数）；流式路径取首到末 reasoning chunk 的墙钟时间差",
    )
    ttsAudioAssetId: str | None = Field(
        default=None,
        description="已合成的 TTS 音频文件 UUID（对应 data/tts_cache/{uuid}.mp3）",
    )
    ttsAudioSourceText: str | None = Field(
        default=None,
        description="实际送入 TTS 合成的文本（含后处理/翻译后的朗读稿）",
    )
    mvuProcessed: bool = Field(
        default=False,
        description="MVU 已消费标记：该消息的提取数据已被 MVU Agent 处理；同一会话内最多一条消息持有此标记",
    )

    @model_validator(mode="after")
    def _validate_tool_fields(self) -> ChatMessage:
        if self.role == "tool":
            if not (self.tool_call_id and str(self.tool_call_id).strip()):
                raise ValueError("role=tool 时必须提供非空的 tool_call_id")
        if self.tool_calls is not None and self.role != "assistant":
            raise ValueError("仅 assistant 消息可包含 tool_calls")
        return self


class ChatImageAttachment(BaseModel):
    """聊天消息中的图片附件元数据。"""
    model_config = ConfigDict(extra="allow")

    id: str
    filename: str
    mimeType: str
    size: int | None = None
    width: int | None = None
    height: int | None = None
    originalName: str | None = None


class WorldBookAttachment(BaseModel):
    """会话内绑定的一本世界书及其扫描/插入深度（与条目内字段解耦）。"""

    model_config = ConfigDict(extra="allow")

    worldBookId: str
    scanDepth: int | None = Field(default=None, ge=0)
    insertDepth: int = Field(default=5, ge=1)


AutoReadScope = Literal["off", "assistant_only", "user_only", "all"]


class TtsSessionConfig(BaseModel):
    """会话级 TTS 配置，存于 ChatOverrides.tts。"""
    model_config = ConfigDict(extra="allow")

    autoReadScope: AutoReadScope = "off"
    readGapSeconds: float = Field(default=0.0, ge=0.0)
    model: str | None = None
    voiceByCharacterId: dict[str, str] = Field(default_factory=dict)
    voiceByPersonaId: dict[str, str] = Field(default_factory=dict)
    presetId: str | None = None
    preprocessEnabled: bool = False
    preprocessModel: str | None = None
    preprocessPresetId: str | None = None
    preprocessTargetLanguage: str | None = None
    injectEmotionTags: bool = False


class ChatOverrides(BaseModel):
    """
    聊天覆盖设置模型
    
    用于在会话级别覆盖全局设置，优先级高于全局设置。
    
    主要属性：
        prompt: 会话级提示词覆盖
        longTermMemory: 长期记忆内容
        presetId: 关联的API预设ID，None表示使用全局设置
        pureAiMode: 会话级纯AI模式，None表示使用全局设置
        params: 生成参数覆盖
    """
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    sessionSystemPromptMode: Literal["append", "override"] = "append"
    longTermMemory: str | None = None
    contextStartMessageId: str | None = None
    contextStartKeepBeforeMessages: int | None = None
    presetId: str | None = None
    pureAiMode: bool | None = None
    worldBookIds: list[str] = Field(default_factory=list)
    worldBookAttachments: list[WorldBookAttachment] = Field(default_factory=list)
    worldBookGlobalExclusions: list[str] = Field(
        default_factory=list,
        description="全局世界书从本会话顺序移除时记录其 ID，生成时不再注入该书",
    )
    contentRegexScanDepthDefault: int = Field(default=50, ge=1)
    contentRegexRules: list[ChatContentRegexRule] = Field(default_factory=list)
    contentRegexEnabledByRuleId: dict[str, bool] = Field(default_factory=dict)
    params: GenerationParams = Field(default_factory=GenerationParams)
    draftHelp: DraftHelpSettings = Field(default_factory=DraftHelpSettings)
    tts: "TtsSessionConfig | None" = Field(default=None, description="会话级 TTS 配置")
    autoMemorySummaryEveryN: int | None = Field(
        default=None,
        description="每隔若干条主会话消息后自动触发助手总结并写入长期记忆；None 或 0 表示关闭",
    )
    lastAutoMemorySummaryAfterMessageId: str | None = Field(
        default=None,
        description="上次自动总结成功时锚定的主会话最后一条消息 ID",
    )
    autoMemorySummarySilent: bool = Field(
        default=False,
        description="为 True 时不弹窗直接触发；为 False 时先 notify 确认",
    )
    autoMemorySummaryNextAskTier: int = Field(
        default=1,
        ge=1,
        description="非静默下用户拒绝确认后的倍数（下次在 n*tier 条时再问）",
    )
    mvuModel: str | None = Field(
        default=None,
        description="MVU Agent 专用模型；空值时回退到 settings.llm.defaultModel",
    )

    @model_validator(mode="after")
    def _sync_worldbook_attachments(self):
        att = list(self.worldBookAttachments or [])
        ids = list(self.worldBookIds or [])
        if not att and ids:
            self.worldBookAttachments = [
                WorldBookAttachment(worldBookId=wid, scanDepth=None, insertDepth=5)
                for wid in ids
            ]
        if self.worldBookAttachments:
            self.worldBookIds = [a.worldBookId for a in self.worldBookAttachments]
        return self


class StatusTableRow(BaseModel):
    """MVU 状态表格行。"""
    model_config = ConfigDict(extra="allow")

    field: str
    cells: dict[str, str] = Field(default_factory=dict)


class StatusTableDef(BaseModel):
    """MVU 状态表格定义。"""
    model_config = ConfigDict(extra="allow")

    name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[StatusTableRow] = Field(default_factory=list)


class StateVariables(BaseModel):
    """会话级 MVU 状态变量快照，存于 chat.json 内嵌。"""
    model_config = ConfigDict(extra="allow")

    version: int = 1
    updatedAt: str = ""
    source: "MvuStateSource" = "mvu_agent"
    tables: list[StatusTableDef] = Field(default_factory=list)


class MvuWorkLogEntry(BaseModel):
    """MVU 助手工作日志条目，存于 mvu_logs.json。"""
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    chatId: str = ""
    timestamp: str = Field(default_factory=_now_iso)
    eventType: "MvuWorkLogEventType" = "triggered"
    summary: str = ""
    detail: dict[str, Any] | None = None


class GroupMemberSettings(BaseModel):
    """
    群聊成员独立设置模型
    
    用于为群聊中的每个成员配置独立的生成参数和行为。
    
    主要属性：
        model: 绑定的模型名称
        presetId: 绑定的API预设ID
        temperature: 温度参数，范围0.0-2.0
        top_p: 核采样参数，范围0.0-1.0
        probability: 参与概率，范围0.0-1.0，控制该成员在群聊中的参与度
        includePersonality: 是否在system prompt中包含personality字段
        includeScenario: 是否在system prompt中包含scenario字段
    """
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    presetId: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    includePersonality: bool = True
    includeScenario: bool = True


class Chat(BaseModel):
    """
    聊天会话模型
    
    表示一个完整的聊天会话，支持单聊和群聊两种模式。
    
    主要属性：
        version: 版本号
        id: 会话唯一标识符，自动生成
        characterId: 主角色ID（单聊）或群聊主角色ID
        title: 会话标题
        messages: 消息列表
        overrides: 会话级覆盖设置
        userPersonaId: 当前会话绑定的用户Persona ID
        isGroup: 是否为群聊
        memberIds: 群成员角色ID列表（群聊时使用）
        memberSettings: 成员独立设置字典，key为characterId
        groupDelay: 群聊角色间延迟时间（毫秒）
        groupSystemInjectDepth: 群聊整段 system 按深度插入时，在最后 N 条消息之前插入（仅当 groupSystemAlwaysAtBottom 为 False）
        groupSystemAlwaysAtBottom: 为 True（默认）时不做深度插入，整段 system 在 messages 最前，与旧版一致
        createdAt: 创建时间
        updatedAt: 更新时间
    """
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    characterId: str
    title: str = "新对话"
    messages: list[ChatMessage] = Field(default_factory=list)
    overrides: ChatOverrides = Field(default_factory=ChatOverrides)
    userPersonaId: str | None = None
    isGroup: bool = False
    memberIds: list[str] = Field(default_factory=list)
    memberSettings: dict[str, GroupMemberSettings] = Field(default_factory=dict)
    groupDelay: int = 1500
    groupSystemInjectDepth: int = Field(default=5, ge=0)
    groupSystemAlwaysAtBottom: bool = True
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)
    stateVariables: StateVariables | None = None


class CreateChatRequest(BaseModel):
    """
    创建聊天请求模型
    
    用于创建新聊天会话的请求参数。
    
    主要属性：
        characterId: 角色ID（单聊）或群聊主角色ID
        title: 会话标题，可选
        userPersonaId: 绑定的用户Persona ID，可选
        isGroup: 是否为群聊
        memberIds: 群成员角色ID列表（群聊时使用）
        pureAiMode: 是否启用纯AI模式
        memberSettings: 群成员设置字典
        firstMessageCharacterId: 群聊时选择启用哪个成员的首条消息作为开场
        groupSystemInjectDepth: 群聊 system 深度插入（可选，默认由服务端为 5）
        groupSystemAlwaysAtBottom: 为 True 时整段 system 在首条，不启深度（可选，默认 True）
    """
    characterId: str
    title: str | None = None
    userPersonaId: str | None = None
    isGroup: bool = False
    memberIds: list[str] | None = None
    pureAiMode: bool | None = None
    memberSettings: dict[str, GroupMemberSettings] | None = None
    firstMessageCharacterId: str | None = None
    groupSystemInjectDepth: int | None = Field(default=None, ge=0)
    groupSystemAlwaysAtBottom: bool | None = None


class PromoteToGroupRequest(BaseModel):
    """将单聊复制为群聊：请求体与群聊创建类似，但不插入首句；源单聊保留。"""

    title: str | None = None
    memberIds: list[str]
    pureAiMode: bool | None = None
    userPersonaId: str | None = None
    memberSettings: dict[str, GroupMemberSettings] | None = None
    groupSystemInjectDepth: int | None = Field(default=None, ge=0)
    groupSystemAlwaysAtBottom: bool | None = None


class AppendMessageRequest(BaseModel):
    """
    追加消息请求模型
    
    用于向聊天会话追加新消息的请求参数。
    
    主要属性：
        role: 消息角色
        content: 消息内容
        characterId: 角色ID（群聊时使用）
        senderPersonaId: 发送者Persona ID
        senderName: 发送者名称
        senderAvatar: 发送者头像
    """
    role: MainChatRole
    content: str
    images: list[ChatImageAttachment] = Field(default_factory=list)
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    reasoningContent: str | None = Field(
        default=None,
        description="推理/思考链（流式中断落库等场景；通常仅 assistant）",
    )
    reasoningDurationSec: float | None = Field(
        default=None,
        description="思考耗时（秒）；可选",
    )


class UpdateMessageRequest(BaseModel):
    """
    更新消息请求模型
    
    用于更新聊天会话中已有消息的请求参数。
    
    主要属性：
        role: 消息角色
        content: 消息内容
        characterId: 角色ID（群聊时使用）
        senderPersonaId: 发送者Persona ID
        senderName: 发送者名称
        senderAvatar: 发送者头像
    """
    role: MainChatRole
    content: str
    images: list[ChatImageAttachment] | None = None
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    greetingVariantIndex: int | None = None
    greetingVariants: list[str] | None = Field(
        default=None,
        description="多候选正文列表；不发送则不修改。显式 null 或空列表则清除多版本元数据",
    )
    greetingVariantReasoningContents: list[str] | None = Field(
        default=None,
        description="与 greetingVariants 等长的每候选思考文；不发送则不修改。随 clearing 时一并可清",
    )
    greetingVariantReasoningDurations: list[float | None] | None = Field(
        default=None,
        description="与 greetingVariants 等长的每候选思考耗时（秒）",
    )
    reasoningContent: str | None = Field(
        default=None,
        description="补写或修正推理/思考链文本（如流式中断后落库）",
    )
    reasoningDurationSec: float | None = Field(
        default=None,
        description="补写思考耗时（秒）",
    )


class UpdateChatRequest(BaseModel):
    """
    更新聊天请求模型
    
    用于更新聊天会话信息的请求参数。
    
    主要属性：
        title: 会话标题
        overrides: 覆盖设置
        groupDelay: 群聊角色间延迟时间（毫秒）
        memberSettings: 成员独立设置字典
        memberIds: 群成员顺序列表（用于拖拽排序）
        userPersonaId: 用户Persona ID
        groupSystemInjectDepth: 群聊整段 system 深度插入
        groupSystemAlwaysAtBottom: 整段 system 是否固定在 messages 最前
    """
    title: str | None = None
    overrides: ChatOverrides | None = None
    groupDelay: int | None = None
    memberSettings: dict[str, GroupMemberSettings] | None = None
    memberIds: list[str] | None = None
    userPersonaId: str | None = None
    groupSystemInjectDepth: int | None = Field(default=None, ge=0)
    groupSystemAlwaysAtBottom: bool | None = None


class GenerateStreamRequest(BaseModel):
    """
    流式生成请求模型
    
    用于请求流式生成AI回复的请求参数。
    
    主要属性：
        chatId: 聊天会话ID
        userMessage: 用户消息内容
        appendUserMessage: 是否将用户消息追加到会话中
        senderPersonaId: 发送者Persona ID
        senderName: 发送者名称
        senderAvatar: 发送者头像
        userPersona: 当前用户Persona完整对象（优先用于 system prompt，避免未保存设置时丢失）
        runtimeOverrides: 运行时覆盖设置，优先级最高
    """
    chatId: str
    userMessage: str
    userImages: list[ChatImageAttachment] = Field(default_factory=list)
    imageFallbackMode: bool = False
    appendUserMessage: bool | None = True
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    userPersona: UserPersona | None = None
    runtimeOverrides: ChatOverrides | None = None
    omitMessageIds: list[str] = Field(
        default_factory=list,
        description="仅本次请求拼装 LLM 上下文时忽略的消息 id；不写盘",
    )


class DraftHelpRequest(BaseModel):
    """
    写作辅助请求模型

    mode:
        - write: 根据当前对话续写一段用户消息
        - enhance: 根据草稿润色并扩写
    """
    chatId: str
    mode: Literal["write", "enhance"]
    draft: str | None = None
    conversation: list["DraftHelpConversationMessage"] | None = None


class DraftHelpConversationMessage(BaseModel):
    """写作辅助临时上下文消息。仅用于本次请求，不写入会话。"""
    model_config = ConfigDict(extra="allow")

    id: str
    role: MainChatRole
    content: str
    characterId: str | None = None
    senderName: str | None = None


class GroupGenerateRequest(BaseModel):
    """
    群聊生成请求模型
    
    用于在群聊中指定某个角色进行回复的请求参数。
    
    主要属性：
        chatId: 聊天会话ID
        characterId: 指定回复的角色ID
        runtimeOverrides: 运行时覆盖设置
    """
    chatId: str
    characterId: str
    imageFallbackMode: bool = False
    runtimeOverrides: ChatOverrides | None = None
    omitMessageIds: list[str] = Field(
        default_factory=list,
        description="仅本次请求拼装 LLM 上下文时忽略的消息 id；不写盘",
    )


class SingleInterjectRequest(BaseModel):
    """
    单次插话请求模型
    
    用于在群聊轮次结束后让某个角色额外回复一次的请求参数。
    
    主要属性：
        chatId: 聊天会话ID
        characterId: 指定插话的角色ID
    """
    chatId: str
    characterId: str
    imageFallbackMode: bool = False
