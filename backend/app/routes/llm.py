from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.llm.openai_compat import list_models_openai_compat
from app.storage import load_settings


router = APIRouter(tags=["llm"])


class TestModelsRequest(BaseModel):
    baseUrl: str
    apiKey: str


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


@router.post("/llm/test-models", response_model=list[str])
async def test_models(req: TestModelsRequest) -> list[str]:
    return await list_models_openai_compat(req.baseUrl, req.apiKey)
