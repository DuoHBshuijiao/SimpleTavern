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

from app.errors import AppError
from app.llm.registry import get_adapter
from app.llm.runtime import list_models
from app.llm.types import (
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    normalize_protocol_id,
    provider_id_for_protocol,
)
from app.storage import load_settings


router = APIRouter(tags=["llm"])


class TestModelsRequest(BaseModel):
    """测试指定 API 配置的可用模型列表。"""

    baseUrl: str
    apiKey: str
    protocol: str | None = Field(default=None, description="LLM 协议；缺省 openai_compatible_chat")


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
    protocol = normalize_protocol_id(getattr(settings.llm, "protocol", None))
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
    protocol = normalize_protocol_id(req.protocol)
    get_adapter(protocol)
    models = await list_models(base_url=req.baseUrl, api_key=req.apiKey, protocol=protocol)
    return _require_models(models, source="llm.test_models", protocol=protocol)
