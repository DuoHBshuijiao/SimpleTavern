"""
LLM模型管理路由模块

提供LLM模型列表查询和测试API端点。

主要功能：
    - GET /llm/models: 获取可用模型列表（从设置中读取配置）
    - POST /llm/test-models: 测试指定API配置的可用模型列表
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from typing import Any

from app.errors import AppError
from app.llm.catalog import get_catalog
from app.llm.registry import get_adapter
from app.llm.resolution import preview_resolution, resolve_protocol
from app.llm.runtime import list_models
from app.llm.types import (
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    PROTOCOL_AUTO,
    normalize_protocol_id,
    provider_id_for_protocol,
)
from app.storage import load_settings


router = APIRouter(tags=["llm"])


class TestModelsRequest(BaseModel):
    """测试指定 API 配置的可用模型列表。"""

    baseUrl: str
    apiKey: str
    protocol: str | None = Field(default=None, description="LLM 协议；缺省 openai_compatible_chat；auto 时按 base_url 所属厂商推断")
    providerId: str | None = Field(default=None, description="T-820：名录厂商 id，用于 auto 协议与 URL 模板")
    providerParams: dict[str, str] | None = Field(default=None, description="URL 模板占位参数（如 Azure resource）")


class ResolvePreviewRequest(BaseModel):
    """T-822：预设编辑器 / 聊天面板预览「这次会怎么发」——不需要 api_key。"""

    baseUrl: str = ""
    model: str = ""
    protocol: str | None = Field(default=None, description="auto / openai_compatible_chat / ...")
    providerId: str | None = None
    providerParams: dict[str, str] | None = None
    promptCache: dict[str, Any] | None = None
    reasoningEffort: str | None = None
    fastMode: bool = False
    echoReasoning: bool = True


def _list_models_protocol(req: TestModelsRequest) -> str:
    """auto 协议：按厂商名录挑一个能列模型的具体协议，避免把 auto 直接交给 registry。"""
    protocol = normalize_protocol_id(req.protocol)
    if protocol != PROTOCOL_AUTO:
        return protocol
    catalog = get_catalog()
    entry = catalog.find_provider(req.providerId) or catalog.find_provider_by_base_url(req.baseUrl)
    effective, _base, _adj, _reasons = resolve_protocol(
        PROTOCOL_AUTO,
        model="",
        base_url=req.baseUrl,
        entry=entry,
        provider_params=req.providerParams,
    )
    return effective


def _require_models(models: list[str], *, source: str, protocol: str) -> list[str]:
    if models:
        return models
    raise AppError(
        code="model_list_empty",
        message="上游服务未返回任何可用模型",
        source=source,
        status_code=502,
        provider=provider_id_for_protocol(protocol),
        protocol=protocol,
        suggested_action="检查 API 地址、协议与账号权限；也可在设置中手动维护候选模型",
    )


@router.get("/llm/models", response_model=list[str])
async def get_models() -> list[str]:
    """从全局设置读取配置并拉取模型列表；失败不伪装本地候选。"""
    settings = load_settings()
    protocol = _list_models_protocol(
        TestModelsRequest(
            baseUrl=settings.llm.baseUrl,
            apiKey="",
            protocol=getattr(settings.llm, "protocol", None),
            providerId=getattr(settings.llm, "providerId", None),
            providerParams=getattr(settings.llm, "providerParams", None) or None,
        )
    )
    # 校验协议已注册（未实现原生协议会 fast-fail）
    get_adapter(protocol)
    models = await list_models(
        base_url=settings.llm.baseUrl,
        api_key=settings.llm.apiKey,
        protocol=protocol,
    )
    return _require_models(models, source="llm.models", protocol=protocol)


@router.post("/llm/test-models", response_model=list[str])
async def test_models(req: TestModelsRequest) -> list[str]:
    """使用请求内凭证测试模型列表，不依赖全局设置。"""
    protocol = _list_models_protocol(req)
    get_adapter(protocol)
    base_url = req.baseUrl
    if req.providerId and req.providerParams:
        entry = get_catalog().find_provider(req.providerId)
        if entry is not None and entry.requires_placeholders:
            base_url = entry.render_base_url(req.providerParams, protocol=protocol) or base_url
    models = await list_models(base_url=base_url, api_key=req.apiKey, protocol=protocol)
    return _require_models(models, source="llm.test_models", protocol=protocol)


@router.get("/llm/catalog")
async def get_llm_catalog() -> dict[str, Any]:
    """T-820：内置厂商名录（pi 供应商 + models.dev/OpenRouter 元数据 + ST overlay）。"""
    return get_catalog().to_public_dict()


class ModelCapabilitiesRequest(BaseModel):
    model: str
    providerId: str | None = None
    baseUrl: str | None = None


@router.post("/llm/model-capabilities")
async def get_model_capabilities(req: ModelCapabilitiesRequest) -> dict[str, Any]:
    """T-824：模型能力（可用思考深度 / Fast 模式 / 成本），供聊天面板即时渲染。"""
    caps = get_catalog().model_capabilities(req.model, provider_id=req.providerId, base_url=req.baseUrl)
    return caps.to_public_dict()


@router.post("/llm/resolve-preview")
async def resolve_preview(req: ResolvePreviewRequest) -> dict[str, Any]:
    """T-822：预览协议自适应 / 深度 clamp / Fast / 缓存计划，不发起上游请求。"""
    resolution = preview_resolution(
        protocol=req.protocol,
        base_url=req.baseUrl,
        model=req.model,
        prompt_cache=req.promptCache,
        provider_id=req.providerId,
        provider_params=req.providerParams,
        reasoning_effort=req.reasoningEffort,
        fast_mode=req.fastMode,
        echo_reasoning=req.echoReasoning,
    )
    return resolution.to_public_dict()
