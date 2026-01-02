from __future__ import annotations

from fastapi import APIRouter

from app.llm.openai_compat import list_models_openai_compat
from app.storage import load_settings


router = APIRouter(tags=["llm"])


@router.get("/llm/models", response_model=list[str])
async def get_models() -> list[str]:
    settings = load_settings()
    models = await list_models_openai_compat(settings.llm.baseUrl, settings.llm.apiKey)
    if models:
        return models
    # 兼容：如果拉取失败，回退到配置里的候选或默认模型
    if settings.llm.modelCandidates:
        return settings.llm.modelCandidates
    return [settings.llm.defaultModel]


