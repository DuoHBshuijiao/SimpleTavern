"""模型自适应协议解析（T-822）+ 请求准备（T-821/T-824 汇合点）。

职责：
1. ``resolve_protocol``：预设协议为 ``auto`` 时按模型家族 + 供应商声明选实际协议；用户钉住协议时永不改写。
2. ``clamp_reasoning_effort``：按模型可用档位把思考深度向下取最近可用档（``none`` 不可用时取最低档）。
3. ``build_request_extras``：把 深度 / Fast / 温度 等翻译成目标协议写法（extra_body + extra_headers）。
4. ``prepare_llm_request``：路由层统一入口——凭据 → 目录 → 协议 → 深度 → 缓存计划 → extra_body 控制块。

所有改写都记录在 ``ProtocolResolution.adjustments``（``{type, from, to, reason}``），
随 SSE ``meta.protocolResolution`` 与 ``POST /api/llm/resolve-preview`` 返回，绝不静默。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.llm.catalog import (
    FAMILY_ANTHROPIC,
    FAMILY_CN_BEST_EFFORT,
    FAMILY_GEMINI,
    FAMILY_OPENAI,
    LlmCatalog,
    ModelCapabilities,
    ProviderEntry,
    get_catalog,
    model_family_from_id,
)
from app.llm.preset_resolve import LlmPresetCredentials, resolve_llm_preset_credentials
from app.llm.prompt_cache import PromptCachePlan, build_prompt_cache_plan, is_openai_official_host
from app.llm.types import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    OPENAI_RESPONSES_PROTOCOL,
    PROTOCOL_AUTO,
    attach_control_block,
    is_auto_protocol,
    normalize_protocol_id,
    provider_id_for_protocol,
)

EFFORT_ORDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
_EFFORT_INDEX = {name: i for i, name in enumerate(EFFORT_ORDER)}

PROTOCOL_LABELS: dict[str, str] = {
    OPENAI_COMPATIBLE_CHAT_PROTOCOL: "OpenAI Chat Completions",
    OPENAI_RESPONSES_PROTOCOL: "OpenAI Responses",
    ANTHROPIC_MESSAGES_PROTOCOL: "Anthropic Messages",
    GEMINI_GENERATE_CONTENT_PROTOCOL: "Gemini generateContent",
    PROTOCOL_AUTO: "自动（按模型识别）",
}

_ANTHROPIC_HOSTS = ("api.anthropic.com",)
_GEMINI_HOSTS = ("generativelanguage.googleapis.com", "aiplatform.googleapis.com")
_OPENAI_RESPONSES_HOSTS = ("api.openai.com", ".openai.azure.com")

# Anthropic：adaptive thinking + output_config.effort（Opus 4.6+ / Sonnet 4.6+ / Claude 5 系）
_ANTHROPIC_ADAPTIVE_RE = re.compile(
    r"opus-4[-.][6-9]|sonnet-4[-.][6-9]|haiku-4[-.][6-9]|opus-5|sonnet-5|haiku-5|claude-5|fable|mythos",
    re.IGNORECASE,
)
# Anthropic：仅 output_config.effort（Opus 4.5 / Sonnet 4.5，仍需 thinking.enabled + budget）
_ANTHROPIC_EFFORT_ONLY_RE = re.compile(r"opus-4[-.]5|sonnet-4[-.]5", re.IGNORECASE)
# DeepSeek V4/V4.1（api-docs.deepseek.com/zh-cn/guides/thinking_mode）：
# Chat thinking.type + reasoning_effort low/high/max（medium/xhigh 服务端映射 high）；Responses reasoning.effort none/low/high/max；
# Anthropic 格式 output_config.effort。思考默认开启，所以 none 必须显式发 disabled。
_DEEPSEEK_MODEL_RE = re.compile(r"(^|/)deepseek-v4", re.IGNORECASE)
_DEEPSEEK_HOST = "api.deepseek.com"
_DEEPSEEK_EFFORTS: tuple[str, ...] = ("none", "low", "medium", "high", "xhigh", "max")
# Gemini 3 起用 thinkingLevel；2.5 用 thinkingBudget
_GEMINI_LEVEL_RE = re.compile(r"gemini-([3-9]|\d{2})", re.IGNORECASE)
_GEMINI_PRO_RE = re.compile(r"gemini-[\d.]+-pro", re.IGNORECASE)
_GEMINI_25_BUDGET: dict[str, int] = {"minimal": 512, "low": 1024, "medium": 8192, "high": 24576}
_GEMINI_3_LEVEL_MAP: dict[str, str] = {"minimal": "minimal", "low": "low", "medium": "medium", "high": "high"}


def protocol_label(protocol: str | None) -> str:
    return PROTOCOL_LABELS.get(str(protocol or ""), str(protocol or ""))


def _adj(kind: str, **fields: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"type": kind}
    out.update({k: v for k, v in fields.items() if v is not None})
    return out


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


def _host_matches(host: str, candidates: tuple[str, ...]) -> bool:
    return any(host == c or (c.startswith(".") and host.endswith(c)) or host.endswith("." + c) for c in candidates)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProtocolResolution:
    requested: str
    effective: str
    model: str
    family: str
    provider_id: str | None = None
    provider_label: str | None = None
    base_url: str = ""
    requested_effort: str = "none"
    effort: str = "none"
    thinking_enabled: bool = False
    fast_mode_requested: bool = False
    fast_mode: bool = False
    available_efforts: tuple[str, ...] = ()
    supports_fast_mode: bool = False
    capabilities_source: str = "heuristic"
    cache: PromptCachePlan | None = None
    # 历史思考内容回传（DeepSeek 带 tools 请求强制要求；其余厂商可关）
    echo_reasoning: bool = True
    echo_reasoning_source: str = "preset"  # global_on / global_off / preset
    adjustments: tuple[dict[str, Any], ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def switched(self) -> bool:
        return self.requested != self.effective

    def to_public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "requested": self.requested,
            "effective": self.effective,
            "effectiveLabel": protocol_label(self.effective),
            "model": self.model,
            "family": self.family,
            "providerId": self.provider_id,
            "providerLabel": self.provider_label,
            "requestedEffort": self.requested_effort,
            "effort": self.effort,
            "thinkingEnabled": self.thinking_enabled,
            "fastModeRequested": self.fast_mode_requested,
            "fastMode": self.fast_mode,
            "availableEfforts": list(self.available_efforts),
            "supportsFastMode": self.supports_fast_mode,
            "capabilitiesSource": self.capabilities_source,
            "echoReasoning": self.echo_reasoning,
            "echoReasoningSource": self.echo_reasoning_source,
            "adjustments": [dict(a) for a in self.adjustments],
            "reasons": list(self.reasons),
        }
        if self.cache is not None:
            out["cache"] = self.cache.to_meta()
        return out


@dataclass(frozen=True)
class PreparedLlmRequest:
    base_url: str
    api_key: str
    protocol: str
    model: str
    extra_body: dict[str, Any]
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    thinking_enabled: bool
    resolution: ProtocolResolution
    credentials: LlmPresetCredentials
    extra_headers: dict[str, str] = field(default_factory=dict)

    @property
    def llm_provider(self) -> str:
        return provider_id_for_protocol(self.protocol)

    @property
    def echo_reasoning(self) -> bool:
        return self.resolution.echo_reasoning

    def apply_echo_policy(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按回传开关处理历史 assistant 消息的 reasoning_content。"""
        return messages if self.echo_reasoning else strip_reasoning_echo(messages)

    def enrich_error(self, error: Any) -> Any:
        """给上游错误补「打开预设思考回传开关」动作（DeepSeek 且已关闭回传）。"""
        return enrich_error_for_echo_reasoning(error, prepared=self)

    @property
    def anthropic_prompt_cache(self) -> str:
        """兼容旧调用方的 TTL 字符串（off / 5m / 1h）。"""
        plan = self.resolution.cache
        if plan is None or self.protocol != ANTHROPIC_MESSAGES_PROTOCOL or not plan.writes_cache:
            return "off"
        return plan.ttl if plan.ttl in {"5m", "1h"} else "5m"


# ---------------------------------------------------------------------------
# 1. 协议选择
# ---------------------------------------------------------------------------


def _target_protocol_for_family(family: str) -> str | None:
    if family == FAMILY_ANTHROPIC:
        return ANTHROPIC_MESSAGES_PROTOCOL
    if family == FAMILY_GEMINI:
        return GEMINI_GENERATE_CONTENT_PROTOCOL
    if family == FAMILY_OPENAI:
        return OPENAI_RESPONSES_PROTOCOL
    return None


def _provider_supports(entry: ProviderEntry | None, base_url: str, protocol: str) -> bool:
    if entry is not None and protocol in entry.supported_protocols:
        return True
    host = _host_of(base_url)
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        return _host_matches(host, _ANTHROPIC_HOSTS)
    if protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        return _host_matches(host, _GEMINI_HOSTS)
    if protocol == OPENAI_RESPONSES_PROTOCOL:
        return _host_matches(host, _OPENAI_RESPONSES_HOSTS)
    if protocol == OPENAI_COMPATIBLE_CHAT_PROTOCOL:
        return True
    return False


def _rewrite_base_url_for_protocol(
    base_url: str,
    *,
    entry: ProviderEntry | None,
    provider_params: dict[str, str] | None,
    from_protocol: str,
    to_protocol: str,
) -> tuple[str, dict[str, Any] | None]:
    """切协议时按供应商 protocolPaths 重写 base_url；无声明时做最小修正（去 ``/openai`` 后缀等）。"""
    if entry is not None and to_protocol in entry.protocol_paths:
        try:
            rendered = entry.render_base_url(provider_params, protocol=to_protocol)
        except Exception:  # noqa: BLE001 - 缺占位符时保持原地址，让后续 fast-fail 更贴近实际调用
            rendered = ""
        if rendered and rendered.rstrip("/") != base_url.rstrip("/"):
            return rendered, _adj("base_url_rewritten", **{"from": base_url, "to": rendered}, reason="按供应商目录中该协议的地址模板")
    raw = base_url.rstrip("/")
    lower = raw.lower()
    if to_protocol == GEMINI_GENERATE_CONTENT_PROTOCOL and lower.endswith("/openai"):
        new = raw[: -len("/openai")]
        return new, _adj("base_url_rewritten", **{"from": base_url, "to": new}, reason="Gemini 原生协议不走 /openai 兼容层")
    if to_protocol == ANTHROPIC_MESSAGES_PROTOCOL and lower.endswith("/chat/completions"):
        new = raw[: -len("/chat/completions")]
        return new, _adj("base_url_rewritten", **{"from": base_url, "to": new}, reason="Anthropic Messages 端点由适配器拼接")
    return base_url, None


def resolve_protocol(
    requested: str | None,
    *,
    model: str,
    base_url: str,
    entry: ProviderEntry | None,
    provider_params: dict[str, str] | None = None,
) -> tuple[str, str, tuple[dict[str, Any], ...], tuple[str, ...]]:
    """返回 (effective_protocol, base_url, adjustments, reasons)。"""
    family = model_family_from_id(model)
    requested_key = str(requested or "").strip().lower() or OPENAI_COMPATIBLE_CHAT_PROTOCOL
    adjustments: list[dict[str, Any]] = []
    reasons: list[str] = []

    if not is_auto_protocol(requested_key):
        effective = normalize_protocol_id(requested_key)
        target = _target_protocol_for_family(family)
        if target and target != effective and _provider_supports(entry, base_url, target):
            reasons.append(f"已钉住 {protocol_label(effective)}；该供应商也支持 {protocol_label(target)}，可把协议改为「自动」以按模型切换")
        return effective, base_url, tuple(adjustments), tuple(reasons)

    default_protocol = entry.default_protocol if entry is not None else OPENAI_COMPATIBLE_CHAT_PROTOCOL
    if default_protocol == PROTOCOL_AUTO or not default_protocol:
        default_protocol = OPENAI_COMPATIBLE_CHAT_PROTOCOL
    target = _target_protocol_for_family(family)

    if target is None:
        effective = default_protocol
        reasons.append(f"模型家族 {family}：沿用供应商默认协议 {protocol_label(effective)}")
        return effective, base_url, tuple(adjustments), tuple(reasons)

    if _provider_supports(entry, base_url, target):
        effective = target
        new_base, adj = _rewrite_base_url_for_protocol(
            base_url, entry=entry, provider_params=provider_params, from_protocol=default_protocol, to_protocol=target
        )
        if adj:
            adjustments.append(adj)
        if effective != default_protocol:
            adjustments.append(
                _adj(
                    "protocol_switched",
                    **{"from": default_protocol, "to": effective},
                    reason=f"模型 {model} 属于 {family} 家族，供应商支持 {protocol_label(effective)}",
                )
            )
        else:
            reasons.append(f"模型家族 {family} 与供应商默认协议一致：{protocol_label(effective)}")
        return effective, new_base, tuple(adjustments), tuple(reasons)

    effective = default_protocol
    adjustments.append(
        _adj(
            "protocol_kept",
            **{"from": target, "to": effective},
            reason=f"供应商未声明支持 {protocol_label(target)}，保持 {protocol_label(effective)}",
        )
    )
    return effective, base_url, tuple(adjustments), tuple(reasons)


# ---------------------------------------------------------------------------
# 2. 推理深度
# ---------------------------------------------------------------------------


def available_efforts(caps: ModelCapabilities, *, protocol: str) -> tuple[str, ...]:
    """模型可用档位（含 none 的判定）。"""
    family = caps.family
    if _DEEPSEEK_MODEL_RE.search(caps.model_id):
        return _DEEPSEEK_EFFORTS
    efforts = tuple(e for e in caps.efforts if e in _EFFORT_INDEX)
    if not efforts:
        if family == FAMILY_ANTHROPIC:
            efforts = ("low", "medium", "high") + (("max",) if _ANTHROPIC_ADAPTIVE_RE.search(caps.model_id) else ())
        elif family == FAMILY_OPENAI:
            efforts = ("minimal", "low", "medium", "high") if caps.reasoning else ()
        elif family == FAMILY_GEMINI:
            efforts = ("minimal", "low", "medium", "high") if _GEMINI_LEVEL_RE.search(caps.model_id) else ("low", "medium", "high")
        else:
            # 中国厂商 / 通用：目录数据不可靠，按「开关 + 透传档位」处理，xhigh/max 收敛到 high
            efforts = ("low", "medium", "high")

    none_ok = "none" in efforts
    if not none_ok:
        if family == FAMILY_ANTHROPIC:
            none_ok = True  # 省略 thinking 即不思考
        elif family == FAMILY_GEMINI:
            none_ok = not _GEMINI_PRO_RE.search(caps.model_id)  # Pro 不能关闭思考
        elif family == FAMILY_OPENAI:
            none_ok = (not caps.reasoning) or bool(re.search(r"gpt-5\.[1-9]|gpt-5\.\d{2}|gpt-[6-9]", caps.model_id, re.IGNORECASE))
        else:
            none_ok = True  # 中国厂商 / 通用：thinking.type=disabled / enable_thinking=false
    ordered = sorted({*efforts, *(("none",) if none_ok else ())}, key=lambda e: _EFFORT_INDEX[e])
    return tuple(ordered)


def clamp_reasoning_effort(effort: str, available: tuple[str, ...]) -> tuple[str, dict[str, Any] | None]:
    """把请求档位收敛到最近可用档：优先向下，`none` 不可用时向上取最低档。"""
    key = str(effort or "none").lower()
    if key not in _EFFORT_INDEX:
        key = "none"
    if not available:
        return key, None
    if key in available:
        return key, None
    idx = _EFFORT_INDEX[key]
    lower = [e for e in available if _EFFORT_INDEX[e] < idx]
    higher = [e for e in available if _EFFORT_INDEX[e] > idx]
    if key != "none" and lower:
        target = lower[-1]
        if target == "none" and higher:
            target = higher[0]
        reason = f"模型不支持 {key}，取最近可用档 {target}"
    elif higher:
        target = higher[0]
        reason = "模型不能关闭思考，取最低档 " + target if key == "none" else f"模型不支持 {key}，取最低可用档 {target}"
    else:
        target = lower[-1] if lower else key
        reason = f"模型不支持 {key}，取 {target}"
    if target == key:
        return key, None
    return target, _adj("reasoning_effort_clamped", **{"from": key, "to": target}, reason=reason)


# ---------------------------------------------------------------------------
# 3. 请求参数翻译（extra_body / headers）
# ---------------------------------------------------------------------------


def _shared_reasoning_keys(effort: str) -> dict[str, Any]:
    """中国厂商 / 通用 Chat Completions：关思考发 thinking.disabled + enable_thinking=false，不发 reasoning_effort。"""
    enabled = effort != "none"
    out: dict[str, Any] = {
        "thinking": {"type": "enabled" if enabled else "disabled"},
        "enable_thinking": enabled,
    }
    if enabled:
        out["reasoning"] = {"effort": effort}
        out["reasoning_effort"] = effort
    return out


def build_request_extras(
    *,
    protocol: str,
    model: str,
    base_url: str,
    caps: ModelCapabilities,
    effort: str,
    fast_mode: bool,
    entry: ProviderEntry | None,
    temperature: float | None,
    top_p: float | None,
) -> tuple[dict[str, Any], dict[str, str], float | None, float | None, bool, tuple[dict[str, Any], ...]]:
    """返回 (extra_body, extra_headers, temperature, top_p, fast_applied, adjustments)。"""
    family = caps.family
    host = _host_of(base_url)
    openai_official = is_openai_official_host(base_url)
    adjustments: list[dict[str, Any]] = []
    extra: dict[str, Any] = {}
    headers: dict[str, str] = {}
    enabled = effort != "none"

    is_deepseek = bool(_DEEPSEEK_MODEL_RE.search(model)) or host == _DEEPSEEK_HOST

    # ---- 推理写法 ----
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        if not enabled:
            extra["thinking"] = {"type": "disabled"}
        elif is_deepseek:
            extra["thinking"] = {"type": "enabled"}
            extra["output_config"] = {"effort": "max" if effort == "max" else ("low" if effort in {"minimal", "low"} else "high")}
        elif _ANTHROPIC_ADAPTIVE_RE.search(model):
            extra["thinking"] = {"type": "adaptive"}
            extra["output_config"] = {"effort": effort}
        elif _ANTHROPIC_EFFORT_ONLY_RE.search(model):
            extra["thinking"] = {"type": "enabled"}
            extra["reasoning"] = {"effort": effort}
            extra["output_config"] = {"effort": "high" if effort == "max" else effort}
        else:
            extra["thinking"] = {"type": "enabled"}
            extra["reasoning"] = {"effort": "high" if effort in {"xhigh", "max"} else effort}
    elif protocol == OPENAI_RESPONSES_PROTOCOL:
        if enabled:
            extra["reasoning"] = {"effort": effort}
        elif is_deepseek:
            # DeepSeek 默认开思考，关必须显式 none；GPT-6 Astra 等不接受 none，由省略 reasoning 关闭。
            extra["thinking"] = {"type": "disabled"}
            extra["reasoning"] = {"effort": "none"}
    elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        thinking_cfg: dict[str, Any]
        if _GEMINI_LEVEL_RE.search(model):
            level = _GEMINI_3_LEVEL_MAP.get(effort, "high" if effort in {"xhigh", "max"} else "minimal")
            thinking_cfg = {"thinkingLevel": level, "includeThoughts": enabled}
        else:
            budget = 0 if not enabled else _GEMINI_25_BUDGET.get(effort, 24576)
            thinking_cfg = {"thinkingBudget": budget, "includeThoughts": enabled}
        extra["thinking"] = {"type": "enabled" if enabled else "disabled"}
        extra["generationConfig"] = {"thinkingConfig": thinking_cfg}
    else:  # OpenAI 兼容 Chat Completions
        if openai_official:
            if caps.reasoning:
                extra["reasoning_effort"] = effort
                # 推理模型只接受 max_completion_tokens
                extra["max_tokens"] = None
        elif is_deepseek:
            extra["thinking"] = {"type": "enabled" if enabled else "disabled"}
            if enabled:
                extra["reasoning_effort"] = "max" if effort == "max" else ("low" if effort in {"minimal", "low"} else "high")
        elif family == FAMILY_GEMINI and _host_matches(host, _GEMINI_HOSTS):
            if enabled:
                extra["reasoning_effort"] = effort if effort in {"low", "medium", "high"} else "high"
            extra["enable_thinking"] = enabled
        else:
            extra.update(_shared_reasoning_keys(effort))
            if "qwen" in model.lower():
                extra["enable_thinking"] = enabled

    # ---- Fast 模式 ----
    fast_applied = False
    if fast_mode:
        fast_body = caps.fast_mode_body
        if not caps.supports_fast_mode or not fast_body:
            adjustments.append(_adj("fast_mode_unsupported", reason=f"模型 {model} 未声明 Fast / Priority 档位，已忽略"))
        elif protocol == ANTHROPIC_MESSAGES_PROTOCOL:
            extra["speed"] = "fast"
            headers["anthropic-beta"] = "fast-mode-2026-02-01"
            fast_applied = True
        elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
            if "aiplatform.googleapis.com" in host:
                headers["X-Vertex-AI-LLM-Request-Type"] = "shared"
                headers["X-Vertex-AI-LLM-Shared-Request-Type"] = "priority"
            else:
                extra["service_tier"] = "priority"
            fast_applied = True
        elif protocol in {OPENAI_RESPONSES_PROTOCOL, OPENAI_COMPATIBLE_CHAT_PROTOCOL}:
            if openai_official or (entry is not None and entry.fast_mode == "service_tier"):
                extra.update(fast_body)
                fast_applied = True
            else:
                adjustments.append(_adj("fast_mode_unsupported", reason="该端点不是 OpenAI 官方 / Azure，service_tier 不生效，已忽略"))
        else:
            adjustments.append(_adj("fast_mode_unsupported", reason="该协议没有 Fast 档位"))

    # ---- 温度 ----
    out_temperature, out_top_p = temperature, top_p
    if not caps.temperature and (temperature is not None or top_p is not None):
        adjustments.append(_adj("sampling_dropped", reason=f"模型 {model} 不接受 temperature / top_p"))
        out_temperature, out_top_p = None, None
    if protocol == OPENAI_COMPATIBLE_CHAT_PROTOCOL and openai_official and caps.reasoning and (temperature is not None or top_p is not None):
        adjustments.append(_adj("sampling_dropped", reason="OpenAI 推理模型不接受 temperature / top_p"))
        out_temperature, out_top_p = None, None

    return extra, headers, out_temperature, out_top_p, fast_applied, tuple(adjustments)


# ---------------------------------------------------------------------------
# 4. 统一入口
# ---------------------------------------------------------------------------


def _is_deepseek(model: str, base_url: str) -> bool:
    return _host_of(base_url) == _DEEPSEEK_HOST or (model or "").lower().startswith("deepseek-")


def resolve_echo_reasoning(settings: Any, credentials: LlmPresetCredentials) -> tuple[bool, str]:
    """全局三态（on / off / preset）+ 预设开关 → (是否回传, 来源)。"""
    mode = str(getattr(settings, "reasoningEchoBack", "preset") or "preset").lower()
    if mode == "on":
        return True, "global_on"
    if mode == "off":
        return False, "global_off"
    return bool(credentials.echo_reasoning), "preset"


def strip_reasoning_echo(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """移除历史 assistant 消息上的 reasoning_content（关闭回传时）。纯 reasoning 占位消息整条移除。"""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant" or "reasoning_content" not in msg:
            out.append(msg)
            continue
        cleaned = {k: v for k, v in msg.items() if k != "reasoning_content"}
        content = cleaned.get("content")
        has_content = bool(content) if not isinstance(content, str) else bool(content.strip())
        if not has_content and not cleaned.get("tool_calls"):
            continue
        out.append(cleaned)
    return out


def echo_reasoning_action(credentials: LlmPresetCredentials, *, source: str) -> dict[str, Any]:
    """前端错误卡片按钮：跳到 API 预设（或全局连接）的「回传思考内容」开关。"""
    if source == "global_off":
        return {
            "type": "open_settings",
            "tab": "global",
            "field": "reasoningEchoBack",
            "label": "打开全局「思考内容回传」设置",
        }
    if credentials.preset_id:
        return {
            "type": "open_settings",
            "tab": "presets",
            "presetId": credentials.preset_id,
            "field": "echoReasoning",
            "label": f"打开预设「{credentials.preset_name or credentials.preset_id}」的思考回传开关",
        }
    return {
        "type": "open_settings",
        "tab": "presets",
        "field": "echoReasoning",
        "label": "打开全局连接的思考回传开关",
    }


def enrich_error_for_echo_reasoning(error: Any, *, prepared: "PreparedLlmRequest") -> Any:
    """DeepSeek 且关闭了思考回传时，上游 4xx 极可能是缺 reasoning_content；补动作按钮。"""
    if prepared.echo_reasoning or not _is_deepseek(prepared.model, prepared.base_url):
        return error
    detail = " ".join(str(x or "") for x in (getattr(error, "detail", None), getattr(error, "message", None))).lower()
    upstream_status = getattr(error, "upstream_status", None)
    looks_related = "reasoning_content" in detail or "reasoning" in detail or upstream_status == 400
    if not looks_related:
        return error
    action = echo_reasoning_action(prepared.credentials, source=prepared.resolution.echo_reasoning_source)
    hint = "DeepSeek 携带 tools 的请求要求回传历史 reasoning_content；当前已关闭思考回传，请开启后重试"
    if hasattr(error, "with_action"):
        return error.with_action(action, suggested_action=hint)
    return error


def _vendor_notices(model: str, base_url: str) -> list[str]:
    """厂商公告类提示（只进 reasons，不改写请求）。"""
    out: list[str] = []
    key = (model or "").lower()
    if _host_of(base_url) == _DEEPSEEK_HOST or key.startswith("deepseek-"):
        if key in {"deepseek-chat", "deepseek-reasoner"}:
            out.append("DeepSeek 已下线 deepseek-chat / deepseek-reasoner，请改用 deepseek-v4-flash 或 deepseek-v4-pro")
        elif re.fullmatch(r"deepseek-v4-pro(-\d{4})?", key):
            out.append(
                "DeepSeek 公告：V4.1 Flash 预计 2026-09-10 前后发布；其上线后至 V4.1 Pro 发布前，V4 Pro 请求会被路由到 V4.1 Flash 并按 V4.1 Flash 单价计费"
            )
    return out


def _effort_from_settings(settings: Any, override: Any) -> tuple[str, str]:
    """返回 (requested_effort, source)。"""
    from app.schemas import normalize_reasoning_effort, normalize_reasoning_effort_or_none

    ov = normalize_reasoning_effort_or_none(override)
    if ov is not None:
        return ov, "session"
    return normalize_reasoning_effort(getattr(settings, "reasoningEffort", "none")), "global"


def resolve_request(
    *,
    credentials: LlmPresetCredentials,
    model: str,
    requested_effort: str,
    fast_mode: bool,
    temperature: float | None = None,
    top_p: float | None = None,
    chat_id: str | None = None,
    character_id: str | None = None,
    catalog: LlmCatalog | None = None,
    echo_reasoning: bool = True,
    echo_reasoning_source: str = "preset",
) -> tuple[ProtocolResolution, dict[str, Any], dict[str, str], float | None, float | None]:
    """纯解析（不读 settings）：返回 (resolution, extra_body_without_control, headers, temperature, top_p)。"""
    cat = catalog or get_catalog()
    entry = cat.find_provider(credentials.provider_id) if credentials.provider_id else None
    if entry is None:
        entry = cat.find_provider_by_base_url(credentials.base_url)
    base_url = credentials.base_url
    if entry is not None and entry.requires_placeholders and credentials.provider_params:
        try:
            base_url = entry.render_base_url(credentials.provider_params)
        except Exception:  # noqa: BLE001
            base_url = credentials.base_url

    effective, base_url, proto_adjustments, reasons = resolve_protocol(
        credentials.protocol,
        model=model,
        base_url=base_url,
        entry=entry,
        provider_params=credentials.provider_params,
    )
    caps = cat.model_capabilities(model, provider_id=entry.id if entry else None, base_url=base_url)
    efforts = available_efforts(caps, protocol=effective)
    effort, clamp_adj = clamp_reasoning_effort(requested_effort, efforts)

    extra, headers, out_temperature, out_top_p, fast_applied, extra_adjustments = build_request_extras(
        protocol=effective,
        model=model,
        base_url=base_url,
        caps=caps,
        effort=effort,
        fast_mode=fast_mode,
        entry=entry,
        temperature=temperature,
        top_p=top_p,
    )

    cache_plan = build_prompt_cache_plan(
        credentials.prompt_cache,
        protocol=effective,
        requested_protocol=credentials.protocol,
        base_url=base_url,
        model=model,
        family=caps.family,
        provider_cache_strategy=entry.cache_strategy if entry else None,
        provider_explicit_markers=bool(entry.explicit_cache_markers) if entry else False,
        preset_id=credentials.preset_id,
        chat_id=chat_id,
        character_id=character_id,
    )

    adjustments = list(proto_adjustments)
    if clamp_adj:
        adjustments.append(clamp_adj)
    adjustments.extend(extra_adjustments)
    adjustments.extend(cache_plan.adjustments)
    reasons = tuple(reasons) + tuple(_vendor_notices(model, base_url))
    if not echo_reasoning and _is_deepseek(model, base_url):
        reasons = reasons + ("已关闭思考内容回传：DeepSeek 带 tools 的请求会要求 reasoning_content，可能返回 400",)

    resolution = ProtocolResolution(
        requested=str(credentials.protocol or OPENAI_COMPATIBLE_CHAT_PROTOCOL),
        effective=effective,
        model=model,
        family=caps.family,
        provider_id=entry.id if entry else None,
        provider_label=entry.label if entry else None,
        base_url=base_url,
        requested_effort=requested_effort,
        effort=effort,
        thinking_enabled=effort != "none",
        fast_mode_requested=fast_mode,
        fast_mode=fast_applied,
        available_efforts=efforts,
        supports_fast_mode=caps.supports_fast_mode,
        capabilities_source=caps.source,
        cache=cache_plan,
        echo_reasoning=echo_reasoning,
        echo_reasoning_source=echo_reasoning_source,
        adjustments=tuple(adjustments),
        reasons=tuple(reasons),
    )
    return resolution, extra, headers, out_temperature, out_top_p


def prepare_llm_request(
    settings: Any,
    *,
    model: str,
    preset_id: str | None = None,
    reasoning_override: Any = None,
    fast_mode: bool | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    chat_id: str | None = None,
    character_id: str | None = None,
    extra_body: dict[str, Any] | None = None,
    catalog: LlmCatalog | None = None,
) -> PreparedLlmRequest:
    """路由层统一入口：凭据 → 协议 → 深度 → Fast → 缓存计划 → extra_body（含控制块）。

    抛 ``LlmPresetResolveError``（凭据缺失等），调用方按既有方式转 HTTP 错误。
    """
    credentials = resolve_llm_preset_credentials(settings, model=model, explicit_preset_id=preset_id)
    requested_effort, _source = _effort_from_settings(settings, reasoning_override)
    echo, echo_source = resolve_echo_reasoning(settings, credentials)
    resolution, extra, headers, out_temperature, out_top_p = resolve_request(
        credentials=credentials,
        model=model,
        requested_effort=requested_effort,
        fast_mode=bool(fast_mode),
        temperature=temperature,
        top_p=top_p,
        chat_id=chat_id,
        character_id=character_id,
        catalog=catalog,
        echo_reasoning=echo,
        echo_reasoning_source=echo_source,
    )
    merged_extra: dict[str, Any] = dict(extra_body or {})
    merged_extra.update(extra)
    cat = catalog or get_catalog()
    entry = cat.find_provider(credentials.provider_id) if credentials.provider_id else None
    if entry is None:
        entry = cat.find_provider_by_base_url(resolution.base_url or credentials.base_url)
    merged_extra = attach_control_block(
        merged_extra,
        prompt_cache=resolution.cache.to_dict() if resolution.cache is not None else None,
        extra_headers=headers or None,
        auth_style=credentials.auth_style or (entry.auth_style if entry else None),
        protocol_variant=entry.protocol_variant if entry else None,
        provider_params=dict(credentials.provider_params) if credentials.provider_params else None,
    )
    if resolution.thinking_enabled and out_temperature is not None and resolution.effective == ANTHROPIC_MESSAGES_PROTOCOL:
        # Anthropic 开思考时 temperature 必须为 1 / 省略；适配器已处理，这里只为 SSE 一致性
        pass
    if resolution.fast_mode_requested and not resolution.fast_mode:
        from app.errors import AppError

        raise AppError(
            code="provider_capability_unsupported",
            message="当前模型或供应商不支持 Fast 模式",
            detail=f"model={model}; protocol={resolution.effective}",
            source="llm.resolution",
            status_code=400,
            suggested_action="关闭 Fast 模式，或换成支持 Fast / Priority 的官方模型",
            provider=resolution.provider_id,
            protocol=resolution.effective,
        )
    return PreparedLlmRequest(
        base_url=resolution.base_url or credentials.base_url,
        api_key=credentials.api_key,
        protocol=resolution.effective,
        model=model,
        extra_body=merged_extra,
        temperature=out_temperature,
        top_p=out_top_p,
        max_tokens=max_tokens,
        thinking_enabled=resolution.thinking_enabled,
        resolution=resolution,
        credentials=credentials,
        extra_headers=headers,
    )


def preview_resolution(
    *,
    protocol: str | None,
    base_url: str,
    model: str,
    prompt_cache: Any,
    provider_id: str | None = None,
    provider_params: dict[str, str] | None = None,
    reasoning_effort: str | None = None,
    fast_mode: bool = False,
    echo_reasoning: bool = True,
    catalog: LlmCatalog | None = None,
) -> ProtocolResolution:
    """预设编辑器预览：不需要 api_key。"""
    from app.schemas import normalize_reasoning_effort

    from app.schemas import PromptCacheConfig

    if isinstance(prompt_cache, dict):
        prompt_cache = PromptCacheConfig.model_validate(prompt_cache)
    elif prompt_cache is None:
        prompt_cache = PromptCacheConfig()
    creds = LlmPresetCredentials(
        base_url=base_url or "",
        api_key="",
        preset_id=None,
        source="preview",
        protocol=str(protocol or PROTOCOL_AUTO),
        anthropic_prompt_cache="off",
        prompt_cache=prompt_cache,
        provider_id=provider_id,
        provider_params=dict(provider_params or {}),
        auth_style=None,
        preset_name=None,
        echo_reasoning=echo_reasoning,
    )
    resolution, _extra, _headers, _t, _p = resolve_request(
        credentials=creds,
        model=model,
        requested_effort=normalize_reasoning_effort(reasoning_effort or "none"),
        fast_mode=fast_mode,
        catalog=catalog,
        echo_reasoning=echo_reasoning,
    )
    return resolution


def with_cache(resolution: ProtocolResolution, plan: PromptCachePlan) -> ProtocolResolution:
    return replace(resolution, cache=plan)


__all__ = [
    "EFFORT_ORDER",
    "PROTOCOL_LABELS",
    "PreparedLlmRequest",
    "ProtocolResolution",
    "available_efforts",
    "build_request_extras",
    "clamp_reasoning_effort",
    "echo_reasoning_action",
    "enrich_error_for_echo_reasoning",
    "prepare_llm_request",
    "preview_resolution",
    "protocol_label",
    "resolve_echo_reasoning",
    "resolve_protocol",
    "resolve_request",
    "strip_reasoning_echo",
]
