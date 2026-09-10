"""统一 prompt cache 计划与各协议写法（T-821-B1）。

输入：用户配置 ``PromptCacheConfig``（mode/ttl/breakpoints/cacheKey/explicitMarkers）+ 实际协议 + 模型家族/能力 + 供应商条目。
输出：``PromptCachePlan``（已按协议归一化的 mode/ttl/断点/分组键 + 翻译记录），随 GenerationConfig 进入适配器。

各协议写法（官方文档见 docs/tasks/T-821-v0810-prompt-cache.md）：
- Anthropic：块级 ``cache_control: {type: ephemeral, ttl}``（system / tools）+ 顶层 ``cache_control``（history_tail 自动断点）
- OpenAI Responses：``prompt_cache_key``；GPT-5.6+ ``prompt_cache_options{mode, ttl:"30m"}`` + developer message ``input_text`` 块 ``prompt_cache_breakpoint``；更早模型 ``prompt_cache_retention``
- OpenAI Chat Completions：``prompt_cache_key`` / ``prompt_cache_retention``（仅 OpenAI 官方 / Azure）
- 阿里百炼 / Qwen：消息 content 数组内 ``cache_control: {type: ephemeral}``（固定 5 分钟，≤4 标记）
- Gemini：隐式缓存无操作；显式 → ``cachedContents``（见 gemini_cache_store）
- 其他中国厂商：``best_effort`` 不发送任何缓存字段
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.types import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    OPENAI_RESPONSES_PROTOCOL,
)

MODE_OFF = "off"
MODE_IMPLICIT = "implicit"
MODE_EXPLICIT = "explicit"
MODE_BEST_EFFORT = "best_effort"

# OpenAI GPT-5.6 及之后：prompt_cache_options + 显式断点；之前：prompt_cache_retention
_OPENAI_EXPLICIT_CACHE_MODEL_RE = re.compile(r"gpt-5\.([6-9]|\d{2,})|gpt-[6-9]|gpt-\d{2,}", re.IGNORECASE)
_OPENAI_GPT55_RE = re.compile(r"gpt-5\.5", re.IGNORECASE)
_OPENAI_OFFICIAL_HOSTS = ("api.openai.com", ".openai.azure.com", "chatgpt.com")

# Anthropic 最小可缓存 token（按模型家族；官方文档 2026）
_ANTHROPIC_MIN_TOKENS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"haiku-3", re.IGNORECASE), 2048),
    (re.compile(r"haiku-4-5", re.IGNORECASE), 4096),
    (re.compile(r"haiku", re.IGNORECASE), 2048),
    (re.compile(r"opus-4-[5-9]|opus-5|sonnet-4-[6-9]|sonnet-5|fable|mythos", re.IGNORECASE), 4096),
    (re.compile(r"opus|sonnet", re.IGNORECASE), 1024),
)
_GEMINI_MIN_TOKENS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"flash", re.IGNORECASE), 1024),
    (re.compile(r"pro", re.IGNORECASE), 4096),
)
_OPENAI_MIN_TOKENS = 1024
_DASHSCOPE_MIN_TOKENS = 1024

ANTHROPIC_TTL_VALUES = ("5m", "1h")
OPENAI_RETENTION_VALUES = ("in_memory", "24h")
OPENAI_OPTIONS_TTL = "30m"


@dataclass(frozen=True)
class PromptCachePlan:
    protocol: str
    mode: str = MODE_OFF
    ttl: str | int | None = None
    breakpoints: tuple[str, ...] = ("system",)
    cache_key: str | None = None
    explicit_markers: bool = False
    min_tokens: int | None = None
    # OpenAI：'options'（GPT-5.6+）| 'retention'（更早）| None
    openai_style: str | None = None
    # 是否对 OpenAI 官方 / Azure 主机发送 prompt_cache_* 字段
    openai_official: bool = False
    adjustments: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()

    @property
    def enabled(self) -> bool:
        return self.mode in {MODE_IMPLICIT, MODE_EXPLICIT, MODE_BEST_EFFORT}

    @property
    def writes_cache(self) -> bool:
        return self.mode == MODE_EXPLICIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "mode": self.mode,
            "ttl": self.ttl,
            "breakpoints": list(self.breakpoints),
            "cacheKey": self.cache_key,
            "explicitMarkers": self.explicit_markers,
            "minTokens": self.min_tokens,
            "openaiStyle": self.openai_style,
            "openaiOfficial": self.openai_official,
            "adjustments": [dict(a) for a in self.adjustments],
            "warnings": [dict(w) for w in self.warnings],
        }

    def to_meta(self) -> dict[str, Any]:
        """SSE ``meta.cache`` 用的精简形态。"""
        out: dict[str, Any] = {"mode": self.mode}
        if self.ttl is not None:
            out["ttl"] = self.ttl
        if self.enabled:
            out["breakpoints"] = list(self.breakpoints)
        if self.min_tokens:
            out["minTokens"] = self.min_tokens
        if self.cache_key:
            out["cacheKey"] = self.cache_key
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PromptCachePlan | None":
        if not isinstance(raw, dict):
            return None
        return cls(
            protocol=str(raw.get("protocol") or ""),
            mode=str(raw.get("mode") or MODE_OFF),
            ttl=raw.get("ttl"),
            breakpoints=tuple(raw.get("breakpoints") or ("system",)),
            cache_key=raw.get("cacheKey"),
            explicit_markers=bool(raw.get("explicitMarkers", False)),
            min_tokens=raw.get("minTokens"),
            openai_style=raw.get("openaiStyle"),
            openai_official=bool(raw.get("openaiOfficial", False)),
            adjustments=tuple(raw.get("adjustments") or ()),
            warnings=tuple(raw.get("warnings") or ()),
        )


def _adj(kind: str, **fields: Any) -> dict[str, Any]:
    out = {"type": kind}
    out.update({k: v for k, v in fields.items() if v is not None})
    return out


def _ttl_seconds(ttl: str | int | None) -> int | None:
    if isinstance(ttl, bool):
        return None
    if isinstance(ttl, int):
        return ttl if ttl > 0 else None
    if isinstance(ttl, float):
        return int(ttl) if ttl > 0 else None
    key = str(ttl or "").strip().lower()
    table = {"5m": 300, "30m": 1800, "1h": 3600, "24h": 86400, "in_memory": 600}
    if key in table:
        return table[key]
    m = re.fullmatch(r"(\d+)\s*(s|m|h|d)?", key)
    if m:
        n = int(m.group(1))
        unit = m.group(2) or "s"
        return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return None


def is_openai_official_host(base_url: str | None) -> bool:
    host = (base_url or "").strip().lower()
    host = re.sub(r"^https?://", "", host).split("/", 1)[0]
    return any(host == h or host.endswith(h) for h in _OPENAI_OFFICIAL_HOSTS)


def openai_supports_cache_options(model: str | None) -> bool:
    return bool(_OPENAI_EXPLICIT_CACHE_MODEL_RE.search(model or ""))


def _min_tokens_for(protocol: str, family: str, model: str, *, dashscope: bool) -> int | None:
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL or family == "anthropic":
        for pattern, n in _ANTHROPIC_MIN_TOKENS:
            if pattern.search(model or ""):
                return n
        return 1024
    if protocol == GEMINI_GENERATE_CONTENT_PROTOCOL or family == "gemini":
        for pattern, n in _GEMINI_MIN_TOKENS:
            if pattern.search(model or ""):
                return n
        return 2048
    if family == "openai" or protocol == OPENAI_RESPONSES_PROTOCOL:
        return _OPENAI_MIN_TOKENS
    if dashscope:
        return _DASHSCOPE_MIN_TOKENS
    return None


def resolve_cache_key(
    cache_key: str | None,
    *,
    preset_id: str | None,
    chat_id: str | None,
    character_id: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """把 per_chat / per_character / global / 自定义 翻译成上游可用的稳定字符串。"""
    key = (cache_key or "").strip()
    if not key:
        return None, None
    scope = preset_id or "global"

    def _h(*parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:24]
        return f"st-{digest}"

    if key == "per_chat":
        if chat_id:
            return _h("chat", scope, chat_id), None
        # 无会话（预览 / 助手 / 测试）时静默退到全局分组键——只是路由提示，不影响正确性
        return _h("global", scope), None
    if key == "per_character":
        if character_id:
            return _h("character", scope, character_id), None
        if chat_id:
            return _h("chat", scope, chat_id), _adj("cache_key_fallback", **{"from": "per_character", "to": "per_chat"}, reason="当前请求没有角色 id")
        return _h("global", scope), _adj("cache_key_fallback", **{"from": "per_character", "to": "global"}, reason="当前请求没有角色 / 会话 id")
    if key == "global":
        return _h("global", scope), None
    return key[:128], None


def build_prompt_cache_plan(
    config: Any,
    *,
    protocol: str,
    requested_protocol: str | None,
    base_url: str,
    model: str,
    family: str,
    provider_cache_strategy: str | None,
    provider_explicit_markers: bool,
    preset_id: str | None,
    chat_id: str | None,
    character_id: str | None,
) -> PromptCachePlan:
    """把用户 promptCache 配置翻译成目标协议的缓存计划。``config`` 为 ``PromptCacheConfig`` 或等价 dict。"""
    get = (lambda k, d=None: getattr(config, k, d)) if not isinstance(config, dict) else (lambda k, d=None: config.get(k, d))
    mode = str(get("mode") or "auto").lower()
    ttl_in = get("ttl")
    breakpoints_in = tuple(get("breakpoints") or ("system",))
    cache_key_in = get("cacheKey")
    markers_in = bool(get("explicitMarkers", False))
    adjustments: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    is_openai_official = is_openai_official_host(base_url)
    dashscope_like = bool(provider_explicit_markers) or "dashscope" in (base_url or "").lower() or "aliyuncs.com" in (base_url or "").lower()

    if mode == MODE_OFF:
        return PromptCachePlan(protocol=protocol, mode=MODE_OFF, openai_official=is_openai_official)

    # ---- auto：按供应商目录 / 家族推荐 ----
    if mode == "auto":
        strategy = (provider_cache_strategy or "").lower()
        if protocol == ANTHROPIC_MESSAGES_PROTOCOL and strategy != MODE_BEST_EFFORT:
            # Anthropic 线协议本身定义 cache_control；供应商目录明确「尽力缓存」（DeepSeek / Kimi / MiniMax 的 Anthropic 端点）时不发断点
            mode = MODE_EXPLICIT
        elif strategy in {MODE_EXPLICIT, MODE_IMPLICIT, MODE_BEST_EFFORT}:
            mode = strategy
        elif strategy == "none":
            return PromptCachePlan(
                protocol=protocol,
                mode=MODE_OFF,
                openai_official=is_openai_official,
                adjustments=(_adj("cache_disabled", reason="供应商不提供 prompt cache"),),
            )
        elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
            mode = MODE_IMPLICIT
        elif family == "openai" and is_openai_official:
            mode = MODE_IMPLICIT
        elif family == "cn_best_effort" or dashscope_like:
            mode = MODE_BEST_EFFORT
        else:
            mode = MODE_BEST_EFFORT
        adjustments.append(_adj("cache_mode_auto", to=mode))

    # ---- 协议合法性：不支持显式缓存 API 的路径降级为 best_effort 并说明 ----
    if protocol == OPENAI_COMPATIBLE_CHAT_PROTOCOL and mode in {MODE_EXPLICIT, MODE_IMPLICIT}:
        if not is_openai_official and not dashscope_like:
            adjustments.append(
                _adj("cache_mode_downgraded", **{"from": mode, "to": MODE_BEST_EFFORT}, reason="该 OpenAI 兼容端点没有显式缓存参数，改为依赖厂商自动前缀缓存")
            )
            mode = MODE_BEST_EFFORT
        elif dashscope_like and mode == MODE_EXPLICIT:
            markers_in = True
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL and mode == MODE_IMPLICIT:
        adjustments.append(_adj("cache_mode_downgraded", **{"from": MODE_IMPLICIT, "to": MODE_EXPLICIT}, reason="Anthropic 只有显式 cache_control 断点"))
        mode = MODE_EXPLICIT
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL and mode == MODE_BEST_EFFORT:
        # Kimi coding / MiniMax anthropic 端点：厂商自动缓存，不发送 cache_control
        pass

    # ---- TTL 翻译 ----
    ttl: str | int | None = None
    openai_style: str | None = None
    if mode in {MODE_EXPLICIT, MODE_IMPLICIT}:
        if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
            key = str(ttl_in or "").lower() if not isinstance(ttl_in, int) else None
            if key in ANTHROPIC_TTL_VALUES:
                ttl = key
            else:
                secs = _ttl_seconds(ttl_in)
                ttl = "1h" if (secs or 0) > 900 else "5m"
                if ttl_in not in (None, ""):
                    adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": ttl}, reason="Anthropic 仅支持 5m / 1h"))
        elif protocol == OPENAI_RESPONSES_PROTOCOL or (protocol == OPENAI_COMPATIBLE_CHAT_PROTOCOL and is_openai_official):
            if openai_supports_cache_options(model) and protocol == OPENAI_RESPONSES_PROTOCOL:
                openai_style = "options"
                ttl = OPENAI_OPTIONS_TTL
                if ttl_in not in (None, "", OPENAI_OPTIONS_TTL):
                    adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": ttl}, reason="GPT-5.6+ 仅支持 30m"))
            else:
                openai_style = "retention"
                if mode == MODE_EXPLICIT:
                    adjustments.append(
                        _adj("cache_mode_downgraded", **{"from": MODE_EXPLICIT, "to": MODE_IMPLICIT}, reason="该模型没有显式断点，按自动前缀缓存 + prompt_cache_retention")
                    )
                    mode = MODE_IMPLICIT
                key = str(ttl_in or "").lower() if not isinstance(ttl_in, int) else None
                if _OPENAI_GPT55_RE.search(model or ""):
                    ttl = "24h"
                    if key and key != "24h":
                        adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": ttl}, reason="GPT-5.5 仅支持 24h 保留"))
                elif key in OPENAI_RETENTION_VALUES:
                    ttl = key
                else:
                    secs = _ttl_seconds(ttl_in)
                    ttl = "24h" if (secs or 0) >= 3600 * 6 else "in_memory"
                    if ttl_in not in (None, ""):
                        adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": ttl}, reason="OpenAI 旧模型仅支持 in_memory / 24h"))
        elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
            if mode == MODE_EXPLICIT:
                secs = _ttl_seconds(ttl_in) or 3600
                ttl = secs
                if ttl_in not in (None, "") and ttl_in != secs:
                    adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": secs}, reason="Gemini cachedContents 以秒计"))
        elif dashscope_like:
            ttl = "5m"
            if ttl_in not in (None, "", "5m"):
                adjustments.append(_adj("cache_ttl_translated", **{"from": ttl_in, "to": "5m"}, reason="百炼显式缓存固定 5 分钟"))
    elif mode == MODE_BEST_EFFORT and dashscope_like and markers_in:
        ttl = "5m"

    # ---- 分组键（仅 OpenAI 家族用得上）----
    cache_key: str | None = None
    if protocol in {OPENAI_RESPONSES_PROTOCOL, OPENAI_COMPATIBLE_CHAT_PROTOCOL} and is_openai_official and mode != MODE_OFF:
        cache_key, adj = resolve_cache_key(cache_key_in, preset_id=preset_id, chat_id=chat_id, character_id=character_id)
        if adj:
            adjustments.append(adj)

    # ---- 断点 ----
    breakpoints = tuple(b for b in breakpoints_in if b in {"system", "tools", "history_tail"}) or ("system",)
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL and mode == MODE_EXPLICIT and len(breakpoints) > 4:
        breakpoints = breakpoints[:4]

    min_tokens = _min_tokens_for(protocol, family, model, dashscope=dashscope_like)
    if mode == MODE_BEST_EFFORT and not (dashscope_like and markers_in):
        min_tokens = None

    return PromptCachePlan(
        protocol=protocol,
        mode=mode,
        ttl=ttl,
        breakpoints=breakpoints,
        cache_key=cache_key,
        explicit_markers=bool(markers_in and dashscope_like),
        min_tokens=min_tokens,
        openai_style=openai_style,
        openai_official=is_openai_official,
        adjustments=tuple(adjustments),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# 各协议写法助手（供适配器调用；纯函数）
# ---------------------------------------------------------------------------


def anthropic_cache_control(plan: PromptCachePlan | None) -> dict[str, Any] | None:
    if plan is None or plan.mode != MODE_EXPLICIT:
        return None
    control: dict[str, Any] = {"type": "ephemeral"}
    if plan.ttl in ANTHROPIC_TTL_VALUES:
        control["ttl"] = plan.ttl
    return control


def anthropic_system_blocks(system: str | None, plan: PromptCachePlan | None) -> str | list[dict[str, Any]] | None:
    """system 块断点（breakpoints 含 system 时）。"""
    if not system:
        return None
    control = anthropic_cache_control(plan)
    if control is None or "system" not in (plan.breakpoints if plan else ()):
        return system
    return [{"type": "text", "text": system, "cache_control": control}]


def anthropic_mark_tools(tools: list[dict[str, Any]] | None, plan: PromptCachePlan | None) -> list[dict[str, Any]] | None:
    """tools 断点：在最后一个工具定义上打 cache_control。"""
    if not tools:
        return tools
    control = anthropic_cache_control(plan)
    if control is None or "tools" not in (plan.breakpoints if plan else ()):
        return tools
    out = [dict(t) for t in tools]
    out[-1]["cache_control"] = control
    return out


def anthropic_top_level_cache_control(plan: PromptCachePlan | None) -> dict[str, Any] | None:
    """history_tail：顶层 cache_control（Anthropic 自动把断点放到最后一个可缓存块）。"""
    if plan is None or "history_tail" not in plan.breakpoints:
        return None
    return anthropic_cache_control(plan)


def openai_chat_cache_fields(plan: PromptCachePlan | None) -> dict[str, Any]:
    """Chat Completions：仅 OpenAI 官方 / Azure 发送 prompt_cache_key / prompt_cache_retention。"""
    if plan is None or not plan.enabled or not plan.openai_official:
        return {}
    out: dict[str, Any] = {}
    if plan.cache_key:
        out["prompt_cache_key"] = plan.cache_key
    if plan.mode in {MODE_EXPLICIT, MODE_IMPLICIT} and isinstance(plan.ttl, str) and plan.ttl in OPENAI_RETENTION_VALUES:
        out["prompt_cache_retention"] = plan.ttl
    return out


def openai_responses_cache_fields(plan: PromptCachePlan | None) -> dict[str, Any]:
    if plan is None or not plan.enabled or not plan.openai_official:
        return {}
    out: dict[str, Any] = {}
    if plan.cache_key:
        out["prompt_cache_key"] = plan.cache_key
    if plan.mode in {MODE_EXPLICIT, MODE_IMPLICIT}:
        if plan.openai_style == "options":
            out["prompt_cache_options"] = {"mode": plan.mode, "ttl": OPENAI_OPTIONS_TTL}
        elif plan.openai_style == "retention" and isinstance(plan.ttl, str) and plan.ttl in OPENAI_RETENTION_VALUES:
            out["prompt_cache_retention"] = plan.ttl
    return out


def openai_responses_wants_explicit_breakpoint(plan: PromptCachePlan | None) -> bool:
    """GPT-5.6+ 显式模式：把 instructions 放进 developer message 的 input_text 块并打断点。"""
    return bool(
        plan is not None
        and plan.enabled
        and plan.openai_official
        and plan.openai_style == "options"
        and plan.mode == MODE_EXPLICIT
        and "system" in plan.breakpoints
    )


def openai_responses_developer_item(instructions: str) -> dict[str, Any]:
    return {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": instructions,
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }


def dashscope_mark_messages(messages: list[dict[str, Any]], plan: PromptCachePlan | None) -> list[dict[str, Any]]:
    """百炼 / Qwen 显式缓存：system 与最后一条 user 转 content 数组并打 cache_control（≤4 标记）。"""
    if plan is None or not plan.explicit_markers or not plan.enabled:
        return messages
    out = [dict(m) for m in messages]
    marks = 0
    control = {"type": "ephemeral"}

    def _mark(msg: dict[str, Any]) -> None:
        nonlocal marks
        if marks >= 4:
            return
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = [{"type": "text", "text": content, "cache_control": control}]
            marks += 1
        elif isinstance(content, list) and content:
            last = content[-1]
            if isinstance(last, dict) and last.get("type") == "text":
                new_last = dict(last)
                new_last["cache_control"] = control
                msg["content"] = [*content[:-1], new_last]
                marks += 1

    if "system" in plan.breakpoints:
        for msg in out:
            if msg.get("role") == "system":
                _mark(msg)
                break
    if "history_tail" in plan.breakpoints:
        for msg in reversed(out):
            if msg.get("role") == "user":
                _mark(msg)
                break
    return out


def gemini_cache_ttl_seconds(plan: PromptCachePlan | None) -> int | None:
    if plan is None or plan.mode != MODE_EXPLICIT:
        return None
    if isinstance(plan.ttl, int) and plan.ttl > 0:
        return plan.ttl
    return _ttl_seconds(plan.ttl) or 3600


__all__ = [
    "MODE_BEST_EFFORT",
    "MODE_EXPLICIT",
    "MODE_IMPLICIT",
    "MODE_OFF",
    "PromptCachePlan",
    "anthropic_cache_control",
    "anthropic_mark_tools",
    "anthropic_system_blocks",
    "anthropic_top_level_cache_control",
    "build_prompt_cache_plan",
    "dashscope_mark_messages",
    "gemini_cache_ttl_seconds",
    "is_openai_official_host",
    "openai_chat_cache_fields",
    "openai_responses_cache_fields",
    "openai_responses_developer_item",
    "openai_responses_wants_explicit_breakpoint",
    "openai_supports_cache_options",
    "resolve_cache_key",
]
