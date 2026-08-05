"""ProviderAdapter protocol for LLM backends (T-804)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from app.llm.types import GenerationConfig, Usage, WireRequest


@runtime_checkable
class ProviderAdapter(Protocol):
    """Unified adapter surface. Batch 1 implements OpenAI-compatible chat only."""

    provider: str
    protocol: str

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        """Raise AppError when required config is missing/invalid."""

    def build_request(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> WireRequest:
        """Assemble the upstream HTTP request (does not send)."""

    async def list_models(self, *, base_url: str, api_key: str) -> list[str]:
        ...

    async def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
        as_message: bool = False,
    ) -> Any:
        """Non-streaming completion. as_message=True returns full message struct."""

    def stream(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> AsyncIterator[Any]:
        """Streaming completion yielding StreamChunk-compatible events."""

    def decode_usage(self, raw: dict[str, Any] | None) -> Usage | None:
        """Normalize provider usage payload; None when absent."""
