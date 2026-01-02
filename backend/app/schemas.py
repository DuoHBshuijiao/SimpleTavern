from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    userPersonas: list[UserPersona] = Field(default_factory=list)  # 用户Persona列表
    selectedPersonaId: str | None = None  # 当前选中的Persona ID
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


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
    ts: str = Field(default_factory=_now_iso)


class ChatOverrides(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    presetId: str | None = None  # 关联的API预设ID
    params: GenerationParams = Field(default_factory=GenerationParams)


class Chat(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    characterId: str
    title: str = "新对话"
    messages: list[ChatMessage] = Field(default_factory=list)
    overrides: ChatOverrides = Field(default_factory=ChatOverrides)
    createdAt: str = Field(default_factory=_now_iso)
    updatedAt: str = Field(default_factory=_now_iso)


class CreateChatRequest(BaseModel):
    characterId: str
    title: str | None = None


class AppendMessageRequest(BaseModel):
    role: ChatRole
    content: str


class UpdateMessageRequest(BaseModel):
    role: ChatRole
    content: str


class UpdateChatRequest(BaseModel):
    title: str | None = None
    overrides: ChatOverrides | None = None


class GenerateStreamRequest(BaseModel):
    chatId: str
    userMessage: str
    runtimeOverrides: ChatOverrides | None = None
