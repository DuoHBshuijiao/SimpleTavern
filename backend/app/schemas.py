from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


class GenerationParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)


class SettingsPrompts(BaseModel):
    model_config = ConfigDict(extra="allow")

    globalSystem: str = ""


class SettingsLLM(BaseModel):
    model_config = ConfigDict(extra="allow")

    baseUrl: str = "https://api.openai.com"
    apiKey: str = ""
    defaultModel: str = ""
    modelCandidates: list[str] = Field(default_factory=list)
    usedModels: list[str] = Field(default_factory=list)


class ApiPreset(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新预设"
    baseUrl: str = "https://api.openai.com"
    apiKey: str = ""
    models: list[str] = Field(default_factory=list)


class UserPersona(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = "新用户"
    description: str = ""
    avatar: str = ""  # 头像文件名
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    llm: SettingsLLM = Field(default_factory=SettingsLLM)
    apiPresets: list[ApiPreset] = Field(default_factory=list)  # API预设列表
    generationDefaults: GenerationParams = Field(default_factory=GenerationParams)
    prompts: SettingsPrompts = Field(default_factory=SettingsPrompts)
    streamEnabled: bool = True  # 是否启用流式传输
    # 纯 AI 模式：
    # - 不注入用户 Persona
    # - 将用户发言在发送给模型时映射为 system（用于“影响世界/规则”）
    pureAiMode: bool = False
    userPersonas: list[UserPersona] = Field(default_factory=list)  # 用户Persona列表
    selectedPersonaId: str | None = None  # 当前选中的Persona ID
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class AssistantSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str = ""
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model: str | None = None
    presetId: str | None = None  # 关联的API预设ID


class AssistantChat(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage] = Field(default_factory=list)


class CharacterCard(BaseModel):
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
    avatar: str = ""  # 头像文件名
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    role: ChatRole
    content: str
    characterId: str | None = None  # 群聊中标识发言角色ID
    # 发送者快照（用于“切换我的身份”后，历史消息仍显示原发言者）
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    ts: str = Field(default_factory=_now_iso)


class ChatOverrides(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    longTermMemory: str | None = None
    presetId: str | None = None  # 关联的API预设ID
    # 会话级纯 AI 模式（None 表示使用全局 settings.pureAiMode）
    pureAiMode: bool | None = None
    params: GenerationParams = Field(default_factory=GenerationParams)


class GroupMemberSettings(BaseModel):
    """群聊成员独立设置"""
    model_config = ConfigDict(extra="allow")

    model: str | None = None  # 绑定的模型
    presetId: str | None = None  # 绑定的API预设
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)  # 参与概率 0-1
    # system prompt 组装时是否插入该成员的字段（用于避免重复/重叠设定）
    includePersonality: bool = True
    includeScenario: bool = True


class Chat(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    characterId: str
    title: str = "新对话"
    messages: list[ChatMessage] = Field(default_factory=list)
    overrides: ChatOverrides = Field(default_factory=ChatOverrides)
    # 群聊相关字段
    isGroup: bool = False  # 是否为群聊
    memberIds: list[str] = Field(default_factory=list)  # 群成员角色ID列表 (用户始终是成员)
    memberSettings: dict[str, GroupMemberSettings] = Field(default_factory=dict)  # 成员独立设置 {characterId: settings}
    groupDelay: int = 1500  # 群聊角色间延迟时间（毫秒）
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class CreateChatRequest(BaseModel):
    characterId: str
    title: str | None = None
    # 群聊创建参数
    isGroup: bool = False
    memberIds: list[str] | None = None  # 群成员角色ID列表
    # 本次会话是否启用纯 AI 模式（会写入 chat.overrides.pureAiMode）
    pureAiMode: bool | None = None
    # 创建时可一次性写入群成员设置（含参与概率、system prompt 插入字段开关等）
    memberSettings: dict[str, GroupMemberSettings] | None = None
    # 群聊：选择启用谁的 firstMessage 作为开场背景（写入 messages 的第一条 assistant 消息）
    firstMessageCharacterId: str | None = None


class AppendMessageRequest(BaseModel):
    role: ChatRole
    content: str
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None


class UpdateMessageRequest(BaseModel):
    role: ChatRole
    content: str
    characterId: str | None = None
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None


class UpdateChatRequest(BaseModel):
    title: str | None = None
    overrides: ChatOverrides | None = None
    groupDelay: int | None = None  # 群聊角色间延迟时间（毫秒）
    memberSettings: dict[str, GroupMemberSettings] | None = None  # 成员独立设置
    memberIds: list[str] | None = None  # 群成员顺序（用于拖拽排序）


class GenerateStreamRequest(BaseModel):
    chatId: str
    userMessage: str
    appendUserMessage: bool | None = True
    senderPersonaId: str | None = None
    senderName: str | None = None
    senderAvatar: str | None = None
    runtimeOverrides: ChatOverrides | None = None


class GroupGenerateRequest(BaseModel):
    """群聊生成请求 - 指定角色回复"""
    chatId: str
    characterId: str  # 指定回复的角色ID
    runtimeOverrides: ChatOverrides | None = None


class SingleInterjectRequest(BaseModel):
    """单次插话请求 - 轮次结束后让某角色额外回复一次"""
    chatId: str
    characterId: str  # 指定插话的角色ID
