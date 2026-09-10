"""T-820-A1：供应商 / 模型目录加载与匹配。"""

from __future__ import annotations

import pytest

from app.errors import AppError
from app.llm.catalog import get_catalog, model_family_from_id, normalize_model_key


def test_catalog_loads_pi_and_overlay() -> None:
    cat = get_catalog()
    public = cat.to_public_dict()
    ids = {p["id"] for p in public["providers"]}
    assert "openai" in ids
    assert "anthropic" in ids
    assert "deepseek" in ids
    assert "zenmux" in ids
    assert "azure-openai-responses" in ids
    assert "amazon-bedrock" in ids


def test_legacy_id_and_host_match() -> None:
    cat = get_catalog()
    assert cat.find_provider("azure-openai") is not None
    assert cat.find_provider("siliconflow") is not None
    anth = cat.find_provider_by_base_url("https://api.anthropic.com")
    assert anth is not None
    assert anth.id == "anthropic"
    ds = cat.find_provider_by_base_url("https://api.deepseek.com/v1")
    assert ds is not None
    assert ds.id == "deepseek"


def test_azure_placeholder_url() -> None:
    cat = get_catalog()
    azure = cat.find_provider("azure-openai-responses")
    assert azure is not None
    assert azure.auth_style == "api-key"
    url = azure.render_base_url({"resource": "my-eastus"})
    assert url == "https://my-eastus.openai.azure.com/openai/v1"
    with pytest.raises(AppError) as exc:
        azure.render_base_url({})
    assert exc.value.code == "config_missing"


def test_deepseek_alias_and_family() -> None:
    cat = get_catalog()
    assert model_family_from_id("deepseek-v4.1-flash") == "cn_best_effort"
    caps = cat.model_capabilities("deepseek-v4.1-flash")
    assert caps.family == "cn_best_effort"
    assert normalize_model_key("openai/gpt-5.6:free") == "openai/gpt-5.6"
    assert cat.model_capabilities("claude-opus-4-6").family == "anthropic"
