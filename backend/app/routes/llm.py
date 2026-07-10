"""
LLM模型管理路由模块

提供LLM模型列表查询和测试API端点。

主要功能：
    - GET /llm/models: 获取可用模型列表（从设置中读取配置）
    - POST /llm/test-models: 测试指定API配置的可用模型列表

主要函数：
    - get_models: 获取可用模型列表
    - test_models: 测试API配置并获取模型列表

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入llm/openai_compat.py和storage.py
    - 依赖：依赖llm/openai_compat.py和storage.py
    - 位置：路由层，处理LLM模型相关的HTTP请求
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.errors import AppError
from app.llm.openai_compat import list_models_openai_compat
from app.storage import load_settings


router = APIRouter(tags=["llm"])


class TestModelsRequest(BaseModel):
    """
    测试模型请求模型
    
    用于测试指定API配置的可用模型列表。
    
    主要属性：
        baseUrl: API基础URL
        apiKey: API密钥
    """
    baseUrl: str
    apiKey: str


def _require_models(models: list[str], *, source: str) -> list[str]:
    if models:
        return models
    raise AppError(
        code="model_list_empty",
        message="上游服务未返回任何可用模型",
        source=source,
        status_code=502,
        provider="openai_compatible",
        protocol="openai_compatible_chat",
        suggested_action="检查 API 地址与账号权限；也可在设置中手动维护候选模型",
    )


@router.get("/llm/models", response_model=list[str])
async def get_models() -> list[str]:
    """
    获取可用模型列表
    
    从全局设置中读取API配置，调用OpenAI兼容API获取模型列表。
    上游失败或返回空列表时直接返回结构化错误，不用本地候选伪装云端结果。
    
    Returns:
        list[str]: 模型ID列表
    """
    settings = load_settings()
    models = await list_models_openai_compat(settings.llm.baseUrl, settings.llm.apiKey)
    return _require_models(models, source="llm.models")


@router.post("/llm/test-models", response_model=list[str])
async def test_models(req: TestModelsRequest) -> list[str]:
    """
    测试API配置并获取可用模型列表
    
    使用提供的API配置测试连接并获取模型列表，不依赖全局设置。
    
    Args:
        req: 测试请求，包含baseUrl和apiKey
    
    Returns:
        list[str]: 可用模型ID列表
    """
    models = await list_models_openai_compat(req.baseUrl, req.apiKey)
    return _require_models(models, source="llm.test_models")
