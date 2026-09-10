"""内建 LLM 供应商 / 模型目录（T-820-A1）。

数据文件：
- ``providers.generated.json``：由 ``scripts/sync_llm_catalog.py`` 从 pi 名录生成，勿手改。
- ``providers.overlay.json``：人工维护（中文标签、authStyle、占位符、协议支持、缓存策略）。
- ``models.generated.json``：models.dev + OpenRouter 快照。
"""

from app.llm.catalog.catalog import (  # noqa: F401
    FAMILY_ANTHROPIC,
    FAMILY_CN_BEST_EFFORT,
    FAMILY_GEMINI,
    FAMILY_GENERIC,
    FAMILY_OPENAI,
    LlmCatalog,
    ModelCapabilities,
    ProviderEntry,
    get_catalog,
    model_family_from_id,
    normalize_model_key,
    reset_catalog_for_tests,
)

__all__ = [
    "FAMILY_ANTHROPIC",
    "FAMILY_CN_BEST_EFFORT",
    "FAMILY_GEMINI",
    "FAMILY_GENERIC",
    "FAMILY_OPENAI",
    "LlmCatalog",
    "ModelCapabilities",
    "ProviderEntry",
    "get_catalog",
    "model_family_from_id",
    "normalize_model_key",
    "reset_catalog_for_tests",
]
