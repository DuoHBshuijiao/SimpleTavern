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
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


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
    """
    model_config = ConfigDict(extra="allow")

    globalSystem: str = ""


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
    thinkingMode: bool = False  # 思考模式：True 时 extra_body 传 {"thinking": {"type": "enabled"}}，否则传 disabled
    userPersonas: list[UserPersona] = Field(default_factory=list)
    selectedPersonaId: str | None = None
    selectedFont: str | None = None  # 当前选中的自定义字体文件名，存于 data/fonts，不随备份导出
    messageFontSize: int | None = None  # 聊天窗口内消息文字字号（仅作用于消息气泡内容）
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class AssistantSettings(BaseModel):
    """
    AI助手设置模型
    
    用于配置AI助手的行为参数。
    
    主要属性：
        prompt: 助手系统提示词
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


class AssistantChat(BaseModel):
    """
    AI助手聊天记录模型
    
    用于存储AI助手的对话历史。
    
    主要属性：
        messages: 消息列表
    """
    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage] = Field(default_factory=list)


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
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


ChatRole = Literal["system", "user", "assistant"]
"""
聊天消息角色类型

支持三种角色：
    - system: 系统消息
    - user: 用户消息
    - assistant: AI助手消息
"""


class ChatMessage(BaseModel):
    """
    聊天消息模型
    
    表示单条聊天消息，支持单聊和群聊场景。
    
    主要属性：
        version: 版本号
        id: 消息唯一标识符，自动生成
        role: 消息角色（system/user/assistant）
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
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    ts: str = Field(default_factory=_now_iso)


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
    longTermMemory: str | None = None
    contextStartMessageId: str | None = None
    presetId: str | None = None
    pureAiMode: bool | None = None
    params: GenerationParams = Field(default_factory=GenerationParams)
    draftHelp: DraftHelpSettings = Field(default_factory=DraftHelpSettings)


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
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


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
    """
    characterId: str
    title: str | None = None
    userPersonaId: str | None = None
    isGroup: bool = False
    memberIds: list[str] | None = None
    pureAiMode: bool | None = None
    memberSettings: dict[str, GroupMemberSettings] | None = None
    firstMessageCharacterId: str | None = None


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
    role: ChatRole
    content: str
    images: list[ChatImageAttachment] = Field(default_factory=list)
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None


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
    role: ChatRole
    content: str
    images: list[ChatImageAttachment] | None = None
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None


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
    """
    title: str | None = None
    overrides: ChatOverrides | None = None
    groupDelay: int | None = None
    memberSettings: dict[str, GroupMemberSettings] | None = None
    memberIds: list[str] | None = None
    userPersonaId: str | None = None


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
    role: ChatRole
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
