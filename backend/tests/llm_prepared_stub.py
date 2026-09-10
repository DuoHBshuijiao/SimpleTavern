"""测试共用：构造一个最小的 PreparedLlmRequest，替代旧的四元组凭据 stub（T-822 之后路由改用 prepare_llm_request）。"""

from __future__ import annotations

from typing import Any

from app.llm.preset_resolve import LlmPresetCredentials
from app.llm.resolution import PreparedLlmRequest, ProtocolResolution


def stub_prepared_request(
    *,
    base_url: str = "https://provider.example/v1",
    api_key: str = "test-key",
    protocol: str = "openai_compatible_chat",
    model: str = "test-model",
    extra_body: dict[str, Any] | None = None,
    thinking_enabled: bool = False,
) -> PreparedLlmRequest:
    credentials = LlmPresetCredentials(
        base_url=base_url,
        api_key=api_key,
        preset_id=None,
        source="test",
        protocol=protocol,
    )
    resolution = ProtocolResolution(
        requested=protocol,
        effective=protocol,
        model=model,
        family="generic",
        base_url=base_url,
        thinking_enabled=thinking_enabled,
    )
    return PreparedLlmRequest(
        base_url=base_url,
        api_key=api_key,
        protocol=protocol,
        model=model,
        extra_body=dict(extra_body or {}),
        temperature=None,
        top_p=None,
        max_tokens=None,
        thinking_enabled=thinking_enabled,
        resolution=resolution,
        credentials=credentials,
    )


def prepare_stub(*_args: Any, **kwargs: Any) -> PreparedLlmRequest:
    """可直接 patch 到 `app.routes.generate.prepare_llm_request` 的替身。"""
    return stub_prepared_request(model=str(kwargs.get("model") or "test-model"))
