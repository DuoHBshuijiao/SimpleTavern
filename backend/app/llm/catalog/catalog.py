"""供应商 / 模型目录加载与匹配（T-820-A1 / T-822）。

- 供应商：pi generated + overlay 合并；按 id / legacyId / baseUrl host 匹配。
- 模型：models.dev 快照 + OpenRouter 参数表；按模型 id 归一化后查能力（推理档位、Fast 模式、温度、成本、门槛）。
- 家族：模型 id 关键字规则（claude / gemini / openai / cn_best_effort / generic），供 T-822 协议自适应使用。

加载失败必须结构化报错（AppError），不得静默回退为空目录。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.errors import AppError

_CATALOG_DIR = Path(__file__).resolve().parent
_PROVIDERS_GENERATED = _CATALOG_DIR / "providers.generated.json"
_PROVIDERS_OVERLAY = _CATALOG_DIR / "providers.overlay.json"
_MODELS_GENERATED = _CATALOG_DIR / "models.generated.json"

# 模型家族（T-822 协议自适应用）
FAMILY_ANTHROPIC = "anthropic"
FAMILY_GEMINI = "gemini"
FAMILY_OPENAI = "openai"
FAMILY_CN_BEST_EFFORT = "cn_best_effort"
FAMILY_GENERIC = "generic"

_FAMILY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (FAMILY_ANTHROPIC, re.compile(r"(^|[/:._-])claude", re.IGNORECASE)),
    (FAMILY_GEMINI, re.compile(r"(^|[/:._-])(gemini|gemma)", re.IGNORECASE)),
    (
        FAMILY_OPENAI,
        re.compile(r"(^|[/:._-])(gpt-?\d|gpt-oss|o1|o3|o4|codex|chatgpt|davinci)", re.IGNORECASE),
    ),
    (
        FAMILY_CN_BEST_EFFORT,
        re.compile(
            r"(^|[/:._-])(deepseek|kimi|moonshot|glm|qwen|qwq|qvq|minimax|hunyuan|doubao|seed|mimo|step|ernie|yi|spark|"
            r"baichuan|internlm|intern|sensechat|abab|ling|ring|longcat|tbox)",
            re.IGNORECASE,
        ),
    ),
)

# 无元数据时的家族默认推理档位（来自各官方文档；models.dev 有值时以其为准）
_FAMILY_DEFAULT_EFFORTS: dict[str, tuple[str, ...]] = {
    FAMILY_ANTHROPIC: ("low", "medium", "high", "max"),
    FAMILY_OPENAI: ("minimal", "low", "medium", "high"),
    FAMILY_GEMINI: ("low", "medium", "high"),
    FAMILY_CN_BEST_EFFORT: (),
    FAMILY_GENERIC: (),
}

# 未提供 fastMode 声明时的家族推断
_FAMILY_FAST_MODE: dict[str, str | None] = {
    FAMILY_ANTHROPIC: "anthropic_speed",
    FAMILY_OPENAI: "service_tier",
    FAMILY_GEMINI: "gemini_service_tier",
    FAMILY_CN_BEST_EFFORT: None,
    FAMILY_GENERIC: None,
}

_STRIP_SUFFIX_RE = re.compile(r":(free|beta|extended|nitro|floor|online|exacto|thinking)$", re.IGNORECASE)
_DATE_SUFFIX_RE = re.compile(r"[-@](20\d{2}-?\d{2}-?\d{2}|20\d{6})$")

# 目录快照尚未收录的新模型 → 复用同代模型能力（正则 → 归一化 key）。
# DeepSeek 官方：deepseek-chat / deepseek-reasoner 已下线；V4.1 Flash 2026-09-10 前后发布，接口与 V4 一致。
_MODEL_ALIAS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^deepseek-v4(\.\d+)?-flash(-vision)?(-exp)?(-\d{4})?$", re.IGNORECASE), "deepseek-v4-flash"),
    (re.compile(r"^deepseek-v4(\.\d+)?-pro(-\d{4})?$", re.IGNORECASE), "deepseek-v4-pro"),
    (re.compile(r"^deepseek-(chat|reasoner)$", re.IGNORECASE), "deepseek-v4-flash"),
)


def _alias_model_key(bare: str) -> str | None:
    for pattern, target in _MODEL_ALIAS_RULES:
        if pattern.match(bare):
            return target
    return None


def model_family_from_id(model: str | None) -> str:
    """按模型 id 关键字识别家族；无法识别时返回 ``generic``。"""
    text = (model or "").strip()
    if not text:
        return FAMILY_GENERIC
    for family, pattern in _FAMILY_RULES:
        if pattern.search(text):
            return family
    return FAMILY_GENERIC


def normalize_model_key(model: str | None) -> str:
    """去 vendor 前缀、``:free`` 等后缀与 ``models/`` 前缀，小写，供模糊匹配。"""
    text = (model or "").strip()
    if text.startswith("models/"):
        text = text[len("models/") :]
    text = _STRIP_SUFFIX_RE.sub("", text)
    return text.lower()


def _model_key_without_vendor(key: str) -> str:
    if "/" in key:
        return key.rsplit("/", 1)[-1]
    return key


def _host_of(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        return (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return ""


@dataclass(frozen=True)
class ProviderEntry:
    id: str
    label: str
    name: str
    region: str = "global"
    group: str = "global"
    pi_id: str | None = None
    base_url_template: str | None = None
    placeholders: tuple[dict[str, str], ...] = ()
    auth_style: str = "bearer"
    default_protocol: str = "openai_compatible_chat"
    supported_protocols: tuple[str, ...] = ("openai_compatible_chat",)
    protocol_variant: str | None = None
    protocol_paths: dict[str, str] = field(default_factory=dict)
    cache_strategy: str = "best_effort"
    explicit_cache_markers: bool = False
    fast_mode: str | None = None
    docs_url: str | None = None
    keywords: tuple[str, ...] = ()
    legacy_ids: tuple[str, ...] = ()
    requires_oauth: bool = False
    hint: str | None = None
    models_provider_id: str | None = None
    env_keys: tuple[str, ...] = ()
    unsupported_apis: tuple[str, ...] = ()
    # overlay 人工维护的推荐模型 id（厂商目录尚未同步时兜底，如 DeepSeek V4.1）
    suggested_models: tuple[str, ...] = ()

    @property
    def requires_placeholders(self) -> bool:
        return bool(self.placeholders)

    def render_base_url(self, params: dict[str, str] | None, *, protocol: str | None = None) -> str:
        """用 providerParams 填充占位符；缺失占位符时 fast-fail。"""
        template = self.base_url_template or ""
        if protocol and protocol in self.protocol_paths:
            template = self.protocol_paths[protocol]
        if not template:
            return ""
        missing: list[str] = []

        def _sub(match: re.Match[str]) -> str:
            key = match.group(1)
            value = (params or {}).get(key, "").strip()
            if not value:
                missing.append(key)
                return match.group(0)
            return value

        rendered = re.sub(r"\{([a-zA-Z0-9_]+)\}", _sub, template)
        if missing:
            raise AppError(
                code="config_missing",
                message="供应商地址缺少必填参数",
                detail=f"provider={self.id}; missing={', '.join(missing)}",
                source="llm.catalog",
                status_code=400,
                suggested_action="在 API 预设的供应商参数中填写 " + " / ".join(missing),
            )
        return rendered

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "piId": self.pi_id,
            "label": self.label,
            "name": self.name,
            "region": self.region,
            "group": self.group,
            "baseUrlTemplate": self.base_url_template,
            "placeholders": list(self.placeholders),
            "authStyle": self.auth_style,
            "defaultProtocol": self.default_protocol,
            "supportedProtocols": list(self.supported_protocols),
            "protocolVariant": self.protocol_variant,
            "protocolPaths": dict(self.protocol_paths),
            "cacheStrategy": self.cache_strategy,
            "explicitCacheMarkers": self.explicit_cache_markers,
            "fastMode": self.fast_mode,
            "docsUrl": self.docs_url,
            "keywords": list(self.keywords),
            "legacyIds": list(self.legacy_ids),
            "requiresOAuth": self.requires_oauth,
            "hint": self.hint,
            "envKeys": list(self.env_keys),
            "unsupportedApis": list(self.unsupported_apis),
            "suggestedModels": list(self.suggested_models),
        }


@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    family: str
    provider_id: str | None = None
    name: str | None = None
    reasoning: bool = False
    efforts: tuple[str, ...] = ()
    reasoning_toggle: bool = False
    temperature: bool = True
    cost: dict[str, float] = field(default_factory=dict)
    limit: dict[str, int] = field(default_factory=dict)
    modes: dict[str, Any] = field(default_factory=dict)
    supported_parameters: tuple[str, ...] = ()
    release_date: str | None = None
    source: str = "heuristic"

    @property
    def supports_fast_mode(self) -> bool:
        return "fast" in self.modes

    @property
    def fast_mode_body(self) -> dict[str, Any]:
        fast = self.modes.get("fast")
        if isinstance(fast, dict) and isinstance(fast.get("body"), dict):
            return dict(fast["body"])
        return {}

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "modelId": self.model_id,
            "family": self.family,
            "providerId": self.provider_id,
            "name": self.name,
            "reasoning": self.reasoning,
            "efforts": list(self.efforts),
            "reasoningToggle": self.reasoning_toggle,
            "temperature": self.temperature,
            "cost": dict(self.cost),
            "limit": dict(self.limit),
            "supportsFastMode": self.supports_fast_mode,
            "fastModeCost": (self.modes.get("fast") or {}).get("cost") if isinstance(self.modes.get("fast"), dict) else None,
            "supportedParameters": list(self.supported_parameters),
            "releaseDate": self.release_date,
            "source": self.source,
        }


def _load_json(path: Path, *, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AppError(
            code="config_missing",
            message=f"LLM 目录文件缺失：{what}",
            detail=str(path),
            source="llm.catalog",
            status_code=500,
            suggested_action="运行 `python scripts/sync_llm_catalog.py` 重新生成目录",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(
            code="config_invalid",
            message=f"LLM 目录文件无法解析：{what}",
            detail=f"{path}: {exc}",
            source="llm.catalog",
            status_code=500,
            suggested_action="检查目录 JSON 是否损坏，或重新运行同步脚本",
        ) from exc
    if not isinstance(data, dict):
        raise AppError(
            code="config_invalid",
            message=f"LLM 目录文件格式无效：{what}",
            detail=f"{path}: expected object",
            source="llm.catalog",
            status_code=500,
        )
    return data


def _merge_provider(pi: dict[str, Any] | None, overlay: dict[str, Any]) -> ProviderEntry:
    pi = pi or {}
    pi_protocols = tuple(pi.get("protocols") or ())
    supported = tuple(overlay.get("supportedProtocols") or pi_protocols or ("openai_compatible_chat",))
    default_protocol = overlay.get("defaultProtocol") or (supported[0] if supported else "openai_compatible_chat")
    if default_protocol not in supported:
        supported = (default_protocol, *supported)
    placeholders = tuple(
        {str(k): str(v) for k, v in p.items()} for p in (overlay.get("placeholders") or []) if isinstance(p, dict)
    )
    return ProviderEntry(
        id=str(overlay.get("id") or pi.get("id")),
        pi_id=overlay.get("piId") or (pi.get("id") if pi else None),
        label=str(overlay.get("label") or pi.get("name") or overlay.get("id")),
        name=str(overlay.get("name") or pi.get("name") or overlay.get("id")),
        region=str(overlay.get("region") or "global"),
        group=str(overlay.get("group") or "global"),
        base_url_template=overlay.get("baseUrlTemplate") or pi.get("baseUrl"),
        placeholders=placeholders,
        auth_style=str(overlay.get("authStyle") or "bearer"),
        default_protocol=str(default_protocol),
        supported_protocols=supported,
        protocol_variant=overlay.get("protocolVariant"),
        protocol_paths=dict(overlay.get("protocolPaths") or {}),
        cache_strategy=str(overlay.get("cacheStrategy") or "best_effort"),
        explicit_cache_markers=bool(overlay.get("explicitCacheMarkers", False)),
        fast_mode=overlay.get("fastMode"),
        docs_url=overlay.get("docsUrl"),
        keywords=tuple(str(k) for k in (overlay.get("keywords") or [])),
        legacy_ids=tuple(str(k) for k in (overlay.get("legacyIds") or [])),
        requires_oauth=bool(overlay.get("requiresOAuth", False) or pi.get("oauthOnly", False)),
        hint=overlay.get("hint"),
        models_provider_id=overlay.get("modelsProviderId"),
        env_keys=tuple(str(k) for k in (pi.get("envKeys") or [])),
        unsupported_apis=tuple(str(k) for k in (pi.get("unsupportedApis") or [])),
        suggested_models=tuple(str(k) for k in (overlay.get("suggestedModels") or [])),
    )


class LlmCatalog:
    def __init__(
        self,
        *,
        providers_generated: dict[str, Any],
        providers_overlay: dict[str, Any],
        models_generated: dict[str, Any],
    ) -> None:
        pi_by_id: dict[str, dict[str, Any]] = {
            str(p["id"]): p for p in providers_generated.get("providers", []) if isinstance(p, dict) and p.get("id")
        }
        entries: list[ProviderEntry] = []
        seen_pi: set[str] = set()
        for overlay in providers_overlay.get("providers", []):
            if not isinstance(overlay, dict) or not overlay.get("id"):
                continue
            pi_id = overlay.get("piId")
            pi = pi_by_id.get(pi_id) if pi_id else None
            if pi_id:
                seen_pi.add(pi_id)
            entries.append(_merge_provider(pi, overlay))
        # pi 中有但 overlay 未登记的供应商：用默认值登记（仍可见，标 group=global）
        for pi_id, pi in pi_by_id.items():
            if pi_id in seen_pi:
                continue
            entries.append(_merge_provider(pi, {"id": pi_id, "piId": pi_id}))

        self.providers: tuple[ProviderEntry, ...] = tuple(entries)
        self._by_id: dict[str, ProviderEntry] = {p.id: p for p in entries}
        self._by_legacy: dict[str, ProviderEntry] = {}
        for p in entries:
            for legacy in p.legacy_ids:
                self._by_legacy.setdefault(legacy, p)
        # (host 正则, path 正则, path 模板长度, entry)
        self._host_index: list[tuple[re.Pattern[str], re.Pattern[str], int, ProviderEntry]] = []
        for p in entries:
            templates = [p.base_url_template, *p.protocol_paths.values()]
            for template in templates:
                if not template:
                    continue
                normalized = template if template.startswith(("http://", "https://")) else "https://" + template
                marker = "zzphzz"
                parts = urlsplit(re.sub(r"\{[a-zA-Z0-9_]+\}", marker, normalized))
                host_pattern = re.escape((parts.hostname or "").lower()).replace(marker, r"[a-z0-9.-]+")
                path_tpl = parts.path.rstrip("/").lower()
                path_pattern = re.escape(path_tpl).replace(marker, r"[^/]+")
                self._host_index.append(
                    (
                        re.compile(rf"^{host_pattern}$", re.IGNORECASE),
                        re.compile(rf"^{path_pattern}(/|$)", re.IGNORECASE),
                        len(path_tpl),
                        p,
                    )
                )

        self.generated_at: str | None = providers_generated.get("generatedAt")
        self.source: dict[str, Any] = dict(providers_generated.get("source") or {})
        self.models_generated_at: str | None = models_generated.get("generatedAt")
        self._models_by_provider: dict[str, dict[str, Any]] = {
            str(pid): (entry.get("models") or {})
            for pid, entry in (models_generated.get("providers") or {}).items()
            if isinstance(entry, dict)
        }
        self._openrouter: dict[str, Any] = dict(models_generated.get("openrouter") or {})
        # 全局模型索引：归一化 key → (provider_id, model_id, raw)
        self._model_index: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for pid, models in self._models_by_provider.items():
            for mid, raw in models.items():
                if not isinstance(raw, dict):
                    continue
                key = normalize_model_key(mid)
                self._model_index.setdefault(key, []).append((pid, mid, raw))
                bare = _model_key_without_vendor(key)
                if bare != key:
                    self._model_index.setdefault(bare, []).append((pid, mid, raw))

    # ---- providers -------------------------------------------------------

    def find_provider(self, provider_id: str | None) -> ProviderEntry | None:
        key = (provider_id or "").strip()
        if not key:
            return None
        return self._by_id.get(key) or self._by_legacy.get(key)

    def find_provider_by_base_url(self, base_url: str | None) -> ProviderEntry | None:
        """按 host（+ 尽量长的 path 前缀）匹配供应商；找不到返回 None（调用方决定是否 fast-fail）。"""
        host = _host_of(base_url)
        if not host:
            return None
        raw = (base_url or "").strip()
        if not raw.startswith(("http://", "https://")):
            raw = "https://" + raw
        path = urlsplit(raw).path.rstrip("/").lower()
        best: tuple[int, ProviderEntry] | None = None
        host_only: ProviderEntry | None = None
        for host_re, path_re, tpl_len, entry in self._host_index:
            if not host_re.match(host):
                continue
            if path_re.match(path):
                # 同 host 不同 path（如 AI Studio 原生 vs /openai）：更长的模板 path 更具体
                if best is None or tpl_len > best[0]:
                    best = (tpl_len, entry)
            elif host_only is None:
                host_only = entry
        if best is not None:
            return best[1]
        return host_only

    def providers_public(self) -> list[dict[str, Any]]:
        return [p.to_public_dict() for p in self.providers]

    # ---- models ----------------------------------------------------------

    def _lookup_model_raw(
        self, model: str, *, provider_id: str | None
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        key = normalize_model_key(model)
        bare = _model_key_without_vendor(key)
        candidates = self._model_index.get(key) or self._model_index.get(bare) or []
        if not candidates:
            # 去日期后缀再试（claude-sonnet-4-6-20260217 → claude-sonnet-4-6）
            stripped = _DATE_SUFFIX_RE.sub("", bare)
            if stripped != bare:
                candidates = self._model_index.get(stripped) or []
        if not candidates:
            alias = _alias_model_key(bare)
            if alias:
                candidates = self._model_index.get(alias) or []
        if not candidates:
            return None, None, None
        if provider_id:
            entry = self.find_provider(provider_id)
            wanted = {provider_id}
            if entry:
                wanted.add(entry.id)
                if entry.models_provider_id:
                    wanted.add(entry.models_provider_id)
                if entry.pi_id:
                    wanted.add(entry.pi_id)
            for pid, mid, raw in candidates:
                if pid in wanted:
                    return pid, mid, raw
        # 优先官方厂商条目（非网关）
        preferred_order = (
            "anthropic", "openai", "google", "xai", "deepseek", "moonshotai-cn", "moonshotai", "kimi-coding",
            "zhipuai", "zai", "minimax-cn", "minimax", "xiaomi", "alibaba-cn", "alibaba", "volcengine",
            "siliconflow-cn", "siliconflow", "mistral", "openrouter",
        )
        for pref in preferred_order:
            for pid, mid, raw in candidates:
                if pid == pref:
                    return pid, mid, raw
        pid, mid, raw = candidates[0]
        return pid, mid, raw

    def model_capabilities(
        self,
        model: str | None,
        *,
        provider_id: str | None = None,
        base_url: str | None = None,
    ) -> ModelCapabilities:
        """返回模型能力；无元数据时按家族给默认值（``source=heuristic``）。"""
        model_id = (model or "").strip()
        family = model_family_from_id(model_id)
        if provider_id is None and base_url:
            entry = self.find_provider_by_base_url(base_url)
            provider_id = entry.id if entry else None

        pid, mid, raw = (None, None, None)
        if model_id:
            pid, mid, raw = self._lookup_model_raw(model_id, provider_id=provider_id)

        or_entry = self._openrouter.get(model_id) or self._openrouter.get(normalize_model_key(model_id))
        supported_params: tuple[str, ...] = ()
        or_efforts: tuple[str, ...] = ()
        if isinstance(or_entry, dict):
            supported_params = tuple(or_entry.get("supportedParameters") or ())
            or_efforts = tuple(or_entry.get("supportedEfforts") or ())

        if raw is not None:
            efforts = tuple(raw.get("efforts") or ()) or or_efforts
            modes = dict(raw.get("modes") or {})
            provider_entry = self.find_provider(provider_id) if provider_id else None
            fast_kind = provider_entry.fast_mode if provider_entry else _FAMILY_FAST_MODE.get(family)
            if "fast" not in modes and fast_kind and _family_default_fast(family, mid or model_id):
                modes["fast"] = {"body": _fast_body_for_kind(fast_kind), "inferred": True}
            return ModelCapabilities(
                model_id=model_id,
                family=family,
                provider_id=pid,
                name=raw.get("name"),
                reasoning=bool(raw.get("reasoning")),
                efforts=efforts,
                reasoning_toggle=bool(raw.get("reasoningToggle")),
                temperature=raw.get("temperature", True) is not False,
                cost=dict(raw.get("cost") or {}),
                limit=dict(raw.get("limit") or {}),
                modes=modes,
                supported_parameters=supported_params,
                release_date=raw.get("releaseDate"),
                source="models_dev",
            )

        efforts = or_efforts or _FAMILY_DEFAULT_EFFORTS.get(family, ())
        modes: dict[str, Any] = {}
        fast_kind = _FAMILY_FAST_MODE.get(family)
        if fast_kind and _family_default_fast(family, model_id):
            modes["fast"] = {"body": _fast_body_for_kind(fast_kind), "inferred": True}
        return ModelCapabilities(
            model_id=model_id,
            family=family,
            provider_id=provider_id,
            reasoning=bool(efforts) or family in {FAMILY_ANTHROPIC, FAMILY_GEMINI, FAMILY_OPENAI},
            efforts=efforts,
            reasoning_toggle=family == FAMILY_CN_BEST_EFFORT,
            supported_parameters=supported_params,
            source="openrouter" if or_entry else "heuristic",
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "generatedAt": self.generated_at,
            "modelsGeneratedAt": self.models_generated_at,
            "source": self.source,
            "providers": self.providers_public(),
        }


def _family_default_fast(family: str, model_id: str) -> bool:
    """没有 models.dev 明确 fast 模式声明时，是否按家族推断支持 Fast。

    只有 OpenAI 家族（service_tier 对全部模型有效）与 Gemini（serviceTier）推断为支持；
    Anthropic 的 fast-mode 仅特定模型（Opus 4.8/5）支持，必须来自 models.dev 声明。
    """
    if family == FAMILY_OPENAI:
        return True
    if family == FAMILY_GEMINI:
        return "gemini" in model_id.lower()
    return False


def _fast_body_for_kind(kind: str) -> dict[str, Any]:
    # OpenAI 2026-07-30 起 "fast" 与 "priority" 同义；发送 "priority" 兼容 Azure 与旧网关。
    if kind == "service_tier":
        return {"service_tier": "priority"}
    if kind == "anthropic_speed":
        return {"speed": "fast"}
    if kind == "gemini_service_tier":
        # Gemini API 请求体顶层 service_tier（priority / flex）；Vertex 走请求头，见 resolution
        return {"service_tier": "priority"}
    return {}


@lru_cache(maxsize=1)
def _load_catalog_cached() -> LlmCatalog:
    return LlmCatalog(
        providers_generated=_load_json(_PROVIDERS_GENERATED, what="providers.generated.json"),
        providers_overlay=_load_json(_PROVIDERS_OVERLAY, what="providers.overlay.json"),
        models_generated=_load_json(_MODELS_GENERATED, what="models.generated.json"),
    )


def get_catalog() -> LlmCatalog:
    return _load_catalog_cached()


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
]
