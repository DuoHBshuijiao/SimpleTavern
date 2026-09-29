#!/usr/bin/env python3
"""本地 prompt cache 命中率探测（不打真实厂商）。

接收端模拟各供应商按前缀匹配记账，返回与 T-821 / BACKEND-API 接近的 usage 形状。
发送端用 ``app.llm.prompt_cache`` 组出应用会发出的断点字段，再 POST 到本机接收端。

用法见仓库外 how-to；本文件可 ``serve`` / ``send`` / ``demo``。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.prompt_cache import (  # noqa: E402
    anthropic_mark_tools,
    anthropic_system_blocks,
    anthropic_top_level_cache_control,
    build_prompt_cache_plan,
    dashscope_mark_messages,
    openai_chat_cache_fields,
    openai_responses_cache_fields,
    openai_responses_developer_item,
    openai_responses_wants_explicit_breakpoint,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_STORE = Path("/tmp/simpletavern-local-cache-hit-probe.json")
MAX_PREFIXES_PER_NS = 64
DUMMY_OUTPUT_TOKENS = 4

_GEMINI_GENERATE_RE = re.compile(
    r"^/(?:gemini/)?v1beta/models/(?P<model>[^/]+):(?:generateContent|streamGenerateContent)$"
)
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# tokens / prefix
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """本地粗算：CJK 一字一 token，其余约 4 字符一 token。不是上游 tokenizer。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            cjk += 1
        else:
            other += 1
    return cjk + (other + 3) // 4


def pad_to_tokens(label: str, min_tokens: int) -> str:
    head = f"{label}\n"
    need = max(0, min_tokens + 32 - estimate_tokens(head))
    return head + ("甲" * need)


def longest_common_prefix(a: str, b: str) -> str:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return a[:i]


def block_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "content", "input_text"):
            inner = value.get(key)
            if isinstance(inner, str):
                return inner
        parts = value.get("parts")
        if isinstance(parts, list):
            return "".join(block_text(p) for p in parts)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, list):
        return "".join(block_text(x) for x in value)
    return str(value)


def has_ephemeral_cache_control(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    cc = obj.get("cache_control")
    return isinstance(cc, dict) and str(cc.get("type") or "") == "ephemeral"


def has_openai_breakpoint(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    bp = obj.get("prompt_cache_breakpoint")
    return isinstance(bp, dict) and str(bp.get("mode") or "") == "explicit"


def min_tokens_for_model(vendor: str, model: str) -> int:
    m = (model or "").lower()
    if vendor == "anthropic":
        if re.search(r"haiku-4-5", m):
            return 4096
        if re.search(r"haiku-3", m):
            return 2048
        if re.search(r"haiku", m):
            return 2048
        if re.search(r"opus-4-[5-9]|opus-5|sonnet-4-[6-9]|sonnet-5|fable|mythos", m):
            return 4096
        return 1024
    if vendor in {"gemini", "gemini_explicit", "gemini_implicit"}:
        if "pro" in m:
            return 4096
        if "flash" in m:
            return 1024
        return 2048
    if vendor in {"dashscope", "openai", "openai_responses", "openai_chat"}:
        return 1024
    return 1024


def ledger_hit_rate(cache_read: int, uncached_input: int) -> float | None:
    denom = uncached_input + cache_read
    if denom <= 0 or cache_read <= 0:
        return None
    return cache_read / denom


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


def empty_store() -> dict[str, Any]:
    return {"prefixes": {}, "gemini_explicit": {}, "gemini_fp": {}, "next_gemini_id": 1, "last": []}


def load_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_store()
    if not isinstance(raw, dict):
        return empty_store()
    raw.setdefault("prefixes", {})
    raw.setdefault("gemini_explicit", {})
    raw.setdefault("gemini_fp", {})
    raw.setdefault("next_gemini_id", 1)
    raw.setdefault("last", [])
    return raw


def save_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class CacheStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def reset(self) -> None:
        with _LOCK:
            save_store(self.path, empty_store())

    def match_and_remember(self, namespace: str, prefix: str, *, min_tokens: int) -> dict[str, Any]:
        with _LOCK:
            data = load_store(self.path)
            prefixes: dict[str, Any] = data.setdefault("prefixes", {})
            seen = [p for p in (prefixes.get(namespace) or []) if isinstance(p, str)]
            best = ""
            for old in seen:
                common = longest_common_prefix(old, prefix)
                if len(common) > len(best):
                    best = common
            matched_tokens = estimate_tokens(best)
            prefix_tokens = estimate_tokens(prefix)
            below = prefix_tokens < min_tokens
            cache_read = 0
            cache_write = 0
            if not below:
                if matched_tokens >= min_tokens:
                    cache_read = matched_tokens
                writable = prefix_tokens - cache_read
                if writable > 0 and prefix_tokens >= min_tokens:
                    cache_write = writable
                if prefix and prefix not in seen:
                    seen.append(prefix)
                    prefixes[namespace] = seen[-MAX_PREFIXES_PER_NS:]
            save_store(self.path, data)
            return {
                "namespace": namespace,
                "prefixTokens": prefix_tokens,
                "matchedPrefixTokens": matched_tokens,
                "minTokens": min_tokens,
                "belowMinTokens": below,
                "cacheReadInputTokens": cache_read,
                "cacheWriteInputTokens": cache_write,
            }

    def create_gemini_explicit(self, *, model: str, blob: str, ttl: str | None) -> dict[str, Any]:
        fp = hashlib.sha256(f"{model}\n{blob}".encode("utf-8")).hexdigest()[:40]
        with _LOCK:
            data = load_store(self.path)
            names_by_fp = data.setdefault("gemini_fp", {})
            existing = names_by_fp.get(fp)
            table = data.setdefault("gemini_explicit", {})
            if isinstance(existing, str) and isinstance(table.get(existing), dict):
                item = table[existing]
                return {"name": existing, "tokens": int(item.get("tokens") or 0), "reused": True}
            nid = int(data.get("next_gemini_id") or 1)
            name = f"cachedContents/local-probe-{nid}"
            data["next_gemini_id"] = nid + 1
            tokens = estimate_tokens(blob)
            table[name] = {"model": model, "blob": blob, "tokens": tokens, "ttl": ttl, "fp": fp}
            names_by_fp[fp] = name
            save_store(self.path, data)
            return {"name": name, "tokens": tokens, "reused": False}

    def lookup_gemini_explicit(self, name: str) -> dict[str, Any] | None:
        with _LOCK:
            data = load_store(self.path)
            item = (data.get("gemini_explicit") or {}).get(name)
            return dict(item) if isinstance(item, dict) else None

    def remember_last(self, report: dict[str, Any]) -> None:
        with _LOCK:
            data = load_store(self.path)
            last = list(data.get("last") or [])
            last.append(report)
            data["last"] = last[-32:]
            save_store(self.path, data)

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            data = load_store(self.path)
            prefixes = data.get("prefixes") or {}
            gemini = data.get("gemini_explicit") or {}
            return {
                "storePath": str(self.path),
                "namespaces": {k: len(v) if isinstance(v, list) else 0 for k, v in prefixes.items()},
                "geminiExplicitCount": len(gemini) if isinstance(gemini, dict) else 0,
                "last": data.get("last") or [],
            }


# ---------------------------------------------------------------------------
# vendor prefix extraction
# ---------------------------------------------------------------------------


def _serialize_messages_linear(messages: list[Any]) -> str:
    chunks: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            chunks.append(block_text(msg))
            continue
        role = str(msg.get("role") or "user")
        chunks.append(f"msg:{role}\n{block_text(msg.get('content'))}\n")
    return "".join(chunks)


def anthropic_cacheable_prefix(body: dict[str, Any]) -> str:
    """按 cache_control 断点切前缀：system / 末工具 / 顶层 history_tail。"""
    parts: list[str] = []
    last_break_at = -1
    system = body.get("system")
    if isinstance(system, list):
        for block in system:
            parts.append(f"system\n{block_text(block)}\n")
            if has_ephemeral_cache_control(block):
                last_break_at = len("".join(parts))
    elif isinstance(system, str) and system:
        parts.append(f"system\n{system}\n")
        if has_ephemeral_cache_control(body):
            last_break_at = len("".join(parts))

    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        for i, tool in enumerate(tools):
            parts.append(f"tool\n{block_text(tool)}\n")
            if has_ephemeral_cache_control(tool) or (
                i == len(tools) - 1 and has_ephemeral_cache_control(tool)
            ):
                last_break_at = len("".join(parts))

    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        role = str(msg.get("role") or "user")
        if isinstance(content, list):
            for block in content:
                parts.append(f"msg:{role}\n{block_text(block)}\n")
                if has_ephemeral_cache_control(block):
                    last_break_at = len("".join(parts))
        else:
            parts.append(f"msg:{role}\n{block_text(content)}\n")
            if has_ephemeral_cache_control(msg):
                last_break_at = len("".join(parts))

    joined = "".join(parts)
    if has_ephemeral_cache_control(body.get("cache_control")) or has_ephemeral_cache_control(body):
        # 顶层 cache_control = history_tail：断点落到最后一个可缓存块
        last_break_at = len(joined)
    if last_break_at < 0:
        return ""
    return joined[:last_break_at]


def openai_linear_prompt(body: dict[str, Any]) -> tuple[str, str]:
    """返回 (全量前缀, 显式断点前缀)。断点前缀为空表示没有 prompt_cache_breakpoint。"""
    chunks: list[str] = []
    last_bp = -1
    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions:
        chunks.append(f"instructions\n{instructions}\n")

    def _walk_content(role: str, content: Any) -> None:
        nonlocal last_bp
        if isinstance(content, list):
            for part in content:
                chunks.append(f"{role}\n{block_text(part)}\n")
                if has_openai_breakpoint(part):
                    last_bp = len("".join(chunks))
            return
        chunks.append(f"{role}\n{block_text(content)}\n")

    input_items = body.get("input")
    if isinstance(input_items, list):
        for item in input_items:
            if not isinstance(item, dict):
                chunks.append(block_text(item))
                continue
            role = str(item.get("role") or item.get("type") or "item")
            _walk_content(role, item.get("content") if "content" in item else item)
            if has_openai_breakpoint(item):
                last_bp = len("".join(chunks))
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "user")
            _walk_content(f"msg:{role}", msg.get("content"))
            if has_openai_breakpoint(msg):
                last_bp = len("".join(chunks))
    full = "".join(chunks)
    explicit = full[:last_bp] if last_bp >= 0 else ""
    return full, explicit


def gemini_implicit_prefix(body: dict[str, Any]) -> str:
    parts = [f"system\n{block_text(body.get('systemInstruction'))}\n"]
    contents = body.get("contents")
    if isinstance(contents, list):
        for item in contents:
            role = str(item.get("role") if isinstance(item, dict) else "user")
            text = block_text(item.get("parts") if isinstance(item, dict) else item)
            parts.append(f"msg:{role}\n{text}\n")
    return "".join(parts)


def gemini_explicit_blob(body: dict[str, Any]) -> str:
    return (
        f"model\n{body.get('model') or ''}\n"
        f"system\n{block_text(body.get('systemInstruction'))}\n"
        f"tools\n{block_text(body.get('tools'))}\n"
    )


def dashscope_cacheable_prefix(messages: list[Any]) -> str:
    chunks: list[str] = []
    last_mark = -1
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                chunks.append(f"msg:{role}\n{block_text(part)}\n")
                if has_ephemeral_cache_control(part):
                    last_mark = len("".join(chunks))
        else:
            chunks.append(f"msg:{role}\n{block_text(content)}\n")
            if has_ephemeral_cache_control(msg):
                last_mark = len("".join(chunks))
    joined = "".join(chunks)
    if last_mark < 0:
        return ""
    return joined[:last_mark]


# ---------------------------------------------------------------------------
# accounting + vendor-shaped usage
# ---------------------------------------------------------------------------


def finish_report(
    *,
    vendor: str,
    model: str,
    accounting: dict[str, Any],
    uncached_extra: int = 0,
    output_tokens: int = DUMMY_OUTPUT_TOKENS,
) -> dict[str, Any]:
    cache_read = int(accounting.get("cacheReadInputTokens") or 0)
    cache_write = int(accounting.get("cacheWriteInputTokens") or 0)
    prefix_tokens = int(accounting.get("prefixTokens") or 0)
    # Anthropic：input_tokens 不含 cache read/write；OpenAI prompt_tokens 含 cached
    uncached = max(0, prefix_tokens - cache_read - cache_write) + uncached_extra
    if vendor in {"openai", "openai_responses", "openai_chat"}:
        input_tokens = prefix_tokens + uncached_extra
    elif vendor in {"gemini", "gemini_implicit"}:
        input_tokens = prefix_tokens + uncached_extra
    else:
        input_tokens = uncached
    prefix_hit = (cache_read / prefix_tokens) if prefix_tokens > 0 else None
    ledger_hit = ledger_hit_rate(cache_read, input_tokens)
    normalized = {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadInputTokens": cache_read,
        "cacheWriteInputTokens": cache_write,
        "cacheHitRate": prefix_hit,
        "ledgerCacheHitRate": ledger_hit,
        "totalTokens": input_tokens + output_tokens,
    }
    return {
        "vendor": vendor,
        "model": model,
        "normalized": normalized,
        "probe": {
            **accounting,
            "uncachedInputTokens": uncached,
            "tokenEstimate": "cjk=1, other=ceil(chars/4)",
        },
        "usagePublic": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadInputTokens": cache_read,
            "cacheWriteInputTokens": cache_write,
        },
    }


def wrap_anthropic(report: dict[str, Any], ttl: str | None) -> dict[str, Any]:
    n = report["normalized"]
    read = n["cacheReadInputTokens"]
    write = n["cacheWriteInputTokens"]
    creation = {
        "ephemeral_5m_input_tokens": write if ttl != "1h" else 0,
        "ephemeral_1h_input_tokens": write if ttl == "1h" else 0,
    }
    return {
        "id": "msg_local_probe",
        "type": "message",
        "role": "assistant",
        "model": report["model"],
        "content": [{"type": "text", "text": "probe-ok"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": n["inputTokens"],
            "output_tokens": n["outputTokens"],
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write,
            "cache_creation": creation,
        },
        "probe": report["probe"],
        "normalized": n,
    }


def wrap_openai_chat(report: dict[str, Any], *, best_effort: bool = False) -> dict[str, Any]:
    n = report["normalized"]
    read = n["cacheReadInputTokens"]
    write = n["cacheWriteInputTokens"]
    usage: dict[str, Any] = {
        "prompt_tokens": n["inputTokens"],
        "completion_tokens": n["outputTokens"],
        "total_tokens": n["totalTokens"],
        "prompt_tokens_details": {"cached_tokens": read},
    }
    if best_effort:
        usage["prompt_cache_hit_tokens"] = read
        usage["prompt_cache_miss_tokens"] = max(0, n["inputTokens"] - read)
    return {
        "id": "chatcmpl-local-probe",
        "object": "chat.completion",
        "model": report["model"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "probe-ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
        "probe": report["probe"],
        "normalized": n,
        "cacheWriteInputTokens": write,
    }


def wrap_openai_responses(report: dict[str, Any]) -> dict[str, Any]:
    n = report["normalized"]
    return {
        "id": "resp_local_probe",
        "object": "response",
        "model": report["model"],
        "status": "completed",
        "output_text": "probe-ok",
        "usage": {
            "input_tokens": n["inputTokens"],
            "output_tokens": n["outputTokens"],
            "total_tokens": n["totalTokens"],
            "input_tokens_details": {"cached_tokens": n["cacheReadInputTokens"]},
        },
        "probe": report["probe"],
        "normalized": n,
        "cacheWriteInputTokens": n["cacheWriteInputTokens"],
    }


def wrap_gemini(report: dict[str, Any]) -> dict[str, Any]:
    n = report["normalized"]
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": "probe-ok"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": n["inputTokens"],
            "candidatesTokenCount": n["outputTokens"],
            "totalTokenCount": n["totalTokens"],
            "cachedContentTokenCount": n["cacheReadInputTokens"],
        },
        "probe": report["probe"],
        "normalized": n,
        "cacheWriteInputTokens": n["cacheWriteInputTokens"],
    }


# ---------------------------------------------------------------------------
# HTTP receiver
# ---------------------------------------------------------------------------


def detect_chat_vendor(path: str, headers: dict[str, str], body: dict[str, Any]) -> str:
    hinted = (headers.get("X-Probe-Vendor") or headers.get("x-probe-vendor") or "").strip().lower()
    if hinted == "deepseek":
        return "best_effort"
    if hinted in {"openai", "dashscope", "best_effort"}:
        return hinted
    if "dashscope" in path or "compatible-mode" in path:
        return "dashscope"
    if "deepseek" in path or "best_effort" in path:
        return "best_effort"
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if has_ephemeral_cache_control(msg):
                return "dashscope"
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list) and any(has_ephemeral_cache_control(p) for p in content):
                return "dashscope"
    if any(k in body for k in ("prompt_cache_key", "prompt_cache_retention", "prompt_cache_options")):
        return "openai"
    if hinted:
        return hinted
    return "best_effort"


def handle_request(
    store: CacheStore,
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    route = parsed.path or "/"
    if method == "GET" and route in {"/health", "/"}:
        return 200, {"ok": True, "service": "local-cache-hit-probe", "store": str(store.path)}
    if method == "GET" and route == "/probe/state":
        return 200, store.snapshot()
    if method == "POST" and route in {"/reset", "/probe/reset"}:
        store.reset()
        return 200, {"ok": True, "reset": True}

    if body is None:
        return 400, {"error": {"message": "JSON object required"}}

    if method != "POST":
        return 405, {"error": {"message": "method not allowed"}}

    if route in {"/v1/messages", "/anthropic/v1/messages"}:
        model = str(body.get("model") or "claude-sonnet-4-5")
        prefix = anthropic_cacheable_prefix(body)
        min_tok = min_tokens_for_model("anthropic", model)
        acc = store.match_and_remember(f"anthropic|{model}", prefix, min_tokens=min_tok)
        extra = estimate_tokens(_serialize_messages_linear(body.get("messages") or [])) + estimate_tokens(
            block_text(body.get("system"))
        )
        extra = max(0, extra - int(acc["prefixTokens"]))
        ttl = None
        cc = body.get("cache_control")
        if isinstance(cc, dict):
            ttl = cc.get("ttl")
        report = finish_report(vendor="anthropic", model=model, accounting=acc, uncached_extra=extra)
        store.remember_last({"vendor": "anthropic", **report["normalized"]})
        return 200, wrap_anthropic(report, str(ttl) if ttl else None)

    if route in {"/v1/responses", "/openai/v1/responses"}:
        model = str(body.get("model") or "gpt-5.6")
        full, explicit = openai_linear_prompt(body)
        options = body.get("prompt_cache_options") if isinstance(body.get("prompt_cache_options"), dict) else {}
        mode = str(options.get("mode") or ("explicit" if explicit else "implicit"))
        cacheable = explicit if mode == "explicit" else full
        if mode == "explicit" and not explicit:
            acc = {
                "namespace": f"openai|{model}|no-breakpoint",
                "prefixTokens": estimate_tokens(full),
                "matchedPrefixTokens": 0,
                "minTokens": min_tokens_for_model("openai", model),
                "belowMinTokens": False,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": 0,
                "reason": "explicit mode without prompt_cache_breakpoint: write skipped",
            }
        else:
            key = str(body.get("prompt_cache_key") or "_")
            min_tok = min_tokens_for_model("openai", model)
            acc = store.match_and_remember(f"openai|{model}|{key}|{mode}", cacheable, min_tokens=min_tok)
        extra = max(0, estimate_tokens(full) - int(acc.get("prefixTokens") or 0))
        report = finish_report(vendor="openai_responses", model=model, accounting=acc, uncached_extra=extra)
        store.remember_last({"vendor": "openai_responses", **report["normalized"]})
        return 200, wrap_openai_responses(report)

    gemini_gen = _GEMINI_GENERATE_RE.match(route)
    if route in {"/v1beta/cachedContents", "/gemini/v1beta/cachedContents"}:
        model = str(body.get("model") or "models/gemini-2.5-flash")
        blob = gemini_explicit_blob(body)
        created = store.create_gemini_explicit(model=model, blob=blob, ttl=body.get("ttl"))
        min_tok = min_tokens_for_model("gemini", model)
        write = 0 if created.get("reused") else (created["tokens"] if created["tokens"] >= min_tok else 0)
        report = {
            "name": created["name"],
            "model": model,
            "usageMetadata": {
                "totalTokenCount": created["tokens"],
                "cachedContentTokenCount": 0,
            },
            "normalized": {
                "inputTokens": created["tokens"],
                "outputTokens": 0,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": write,
                "cacheHitRate": 1.0 if created.get("reused") else 0.0,
            },
            "probe": {
                "namespace": f"gemini_explicit|{created['name']}",
                "prefixTokens": created["tokens"],
                "minTokens": min_tok,
                "belowMinTokens": created["tokens"] < min_tok,
                "reused": bool(created.get("reused")),
            },
        }
        store.remember_last({"vendor": "gemini_explicit_create", **report["normalized"]})
        return 200, report

    if gemini_gen:
        model = gemini_gen.group("model")
        cached_name = body.get("cachedContent")
        min_tok = min_tokens_for_model("gemini", model)
        if isinstance(cached_name, str) and cached_name.strip():
            item = store.lookup_gemini_explicit(cached_name.strip())
            if item is None:
                return 404, {"error": {"message": "cachedContent not found", "status": "NOT_FOUND"}}
            contents_tokens = estimate_tokens(gemini_implicit_prefix({**body, "systemInstruction": None}))
            cache_read = int(item.get("tokens") or 0)
            acc = {
                "namespace": f"gemini_explicit|{cached_name}",
                "prefixTokens": cache_read,
                "matchedPrefixTokens": cache_read,
                "minTokens": min_tok,
                "belowMinTokens": cache_read < min_tok,
                "cacheReadInputTokens": cache_read if cache_read >= min_tok else 0,
                "cacheWriteInputTokens": 0,
            }
            report = finish_report(
                vendor="gemini",
                model=model,
                accounting=acc,
                uncached_extra=contents_tokens,
            )
            store.remember_last({"vendor": "gemini_explicit", **report["normalized"]})
            return 200, wrap_gemini(report)
        prefix = gemini_implicit_prefix(body)
        acc = store.match_and_remember(f"gemini_implicit|{model}", prefix, min_tokens=min_tok)
        report = finish_report(vendor="gemini_implicit", model=model, accounting=acc)
        store.remember_last({"vendor": "gemini_implicit", **report["normalized"]})
        return 200, wrap_gemini(report)

    if route.endswith("/chat/completions") or route in {"/v1/chat/completions", "/openai/v1/chat/completions"}:
        vendor = detect_chat_vendor(route, headers, body)
        model = str(body.get("model") or "gpt-4.1")
        messages = body.get("messages") if isinstance(body.get("messages"), list) else []
        min_tok = min_tokens_for_model(vendor, model)
        if vendor == "dashscope":
            prefix = dashscope_cacheable_prefix(messages)
            if not prefix:
                prefix = _serialize_messages_linear(messages)
            key = "dashscope"
        elif vendor == "openai":
            full, _explicit = openai_linear_prompt(body)
            prefix = full
            key = str(body.get("prompt_cache_key") or "_")
        else:
            prefix = _serialize_messages_linear(messages)
            key = "best_effort"
        ns_vendor = {"dashscope": "dashscope", "openai": "openai_chat"}.get(vendor, "best_effort")
        acc = store.match_and_remember(f"{ns_vendor}|{model}|{key}", prefix, min_tokens=min_tok)
        extra = 0
        if vendor == "dashscope":
            extra = max(0, estimate_tokens(_serialize_messages_linear(messages)) - int(acc["prefixTokens"]))
        report = finish_report(
            vendor="dashscope" if vendor == "dashscope" else ("openai_chat" if vendor == "openai" else "best_effort"),
            model=model,
            accounting=acc,
            uncached_extra=extra,
        )
        wrapped = wrap_openai_chat(report, best_effort=(vendor != "openai"))
        store.remember_last({"vendor": vendor, **report["normalized"]})
        return 200, wrapped

    return 404, {"error": {"message": f"no probe route for {route}"}}


class ProbeHandler(BaseHTTPRequestHandler):
    store: CacheStore

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("probe: " + (fmt % args) + "\n")

    def _read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:  # noqa: N802
        status, payload = handle_request(
            self.store, method="GET", path=self.path, headers={k: v for k, v in self.headers.items()}, body=None
        )
        self._send_json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        if body is None:
            self._send_json(400, {"error": {"message": "invalid JSON"}})
            return
        status, payload = handle_request(
            self.store,
            method="POST",
            path=self.path,
            headers={k: v for k, v in self.headers.items()},
            body=body,
        )
        self._send_json(status, payload)


def make_server(host: str, port: int, store: CacheStore) -> ThreadingHTTPServer:
    handler = type("BoundProbeHandler", (ProbeHandler,), {"store": store})
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd


# ---------------------------------------------------------------------------
# sender: app-shaped payloads via prompt_cache helpers
# ---------------------------------------------------------------------------

VENDORS = (
    "anthropic",
    "openai-responses",
    "openai-chat",
    "gemini-implicit",
    "gemini-explicit",
    "dashscope",
    "best-effort",
)

TOOL_SPEC = {
    "name": "lookup_lore",
    "description": "Look up a stable worldbook entry",
    "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
}

OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_lore",
        "description": "Look up a stable worldbook entry",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
}


def fixture_system(min_tokens: int) -> str:
    return pad_to_tokens("【角色卡】你是酒馆里的档案员，世界观与工具定义每轮保持不变。", min_tokens)


def fixture_messages(*, extra_turn: bool = False) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "请根据角色卡问候，并记住工具定义。"},
    ]
    if extra_turn:
        msgs.extend(
            [
                {"role": "assistant", "content": "已记住角色卡。"},
                {"role": "user", "content": "第二轮：仍用同一前缀，只追加这一句。"},
            ]
        )
    return msgs


def build_plan(
    *,
    config: dict[str, Any],
    protocol: str,
    base_url: str,
    model: str,
    family: str,
    strategy: str | None,
    explicit_markers: bool = False,
    chat_id: str = "chat-probe",
) -> Any:
    return build_prompt_cache_plan(
        config,
        protocol=protocol,
        requested_protocol=protocol,
        base_url=base_url,
        model=model,
        family=family,
        provider_cache_strategy=strategy,
        provider_explicit_markers=explicit_markers,
        preset_id="probe-preset",
        chat_id=chat_id,
        character_id="char-probe",
    )


def build_vendor_payload(vendor: str, *, extra_turn: bool = False) -> tuple[str, dict[str, str], dict[str, Any]]:
    """返回 (path, headers, json body)，字段与应用 adapter 发出的缓存断点同类。"""
    messages = fixture_messages(extra_turn=extra_turn)
    if vendor == "anthropic":
        model = "claude-sonnet-4-5"
        system = fixture_system(min_tokens_for_model("anthropic", model))
        config = {
            "mode": "explicit",
            "ttl": "5m",
            "breakpoints": ["system", "tools", "history_tail"],
            "cacheKey": "per_chat",
        }
        plan = build_plan(
            config=config,
            protocol="anthropic_messages",
            base_url="https://api.anthropic.com",
            model=model,
            family="anthropic",
            strategy="explicit",
        )
        tools = [dict(TOOL_SPEC)]
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 64,
            "system": anthropic_system_blocks(system, plan),
            "messages": messages,
            "tools": anthropic_mark_tools(tools, plan),
        }
        top = anthropic_top_level_cache_control(plan)
        if top:
            body["cache_control"] = top
        return "/v1/messages", {"X-Probe-Vendor": "anthropic"}, body

    if vendor == "openai-responses":
        model = "gpt-5.6"
        system = fixture_system(min_tokens_for_model("openai", model))
        config = {
            "mode": "explicit",
            "ttl": "30m",
            "breakpoints": ["system"],
            "cacheKey": "per_chat",
        }
        plan = build_plan(
            config=config,
            protocol="openai_responses",
            base_url="https://api.openai.com/v1",
            model=model,
            family="openai",
            strategy="explicit",
        )
        body = {
            "model": model,
            "store": False,
            "max_output_tokens": 64,
            "input": [openai_responses_developer_item(system), {"role": "user", "content": messages[0]["content"]}],
        }
        if extra_turn:
            body["input"].extend(
                [
                    {"role": "assistant", "content": "已记住角色卡。"},
                    {"role": "user", "content": messages[-1]["content"]},
                ]
            )
        if not openai_responses_wants_explicit_breakpoint(plan):
            # 仍发出断点块，便于本地对照 GPT-5.6+ 显式路径
            pass
        body.update(openai_responses_cache_fields(plan))
        return "/v1/responses", {"X-Probe-Vendor": "openai"}, body

    if vendor == "openai-chat":
        model = "gpt-4.1"
        system = fixture_system(min_tokens_for_model("openai", model))
        config = {
            "mode": "implicit",
            "ttl": "24h",
            "breakpoints": ["system"],
            "cacheKey": "per_chat",
        }
        plan = build_plan(
            config=config,
            protocol="openai_compatible_chat",
            base_url="https://api.openai.com/v1",
            model=model,
            family="openai",
            strategy="implicit",
        )
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        body.update(openai_chat_cache_fields(plan))
        return "/v1/chat/completions", {"X-Probe-Vendor": "openai"}, body

    if vendor == "gemini-implicit":
        model = "gemini-2.5-flash"
        system = fixture_system(min_tokens_for_model("gemini", model))
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages],
            "generationConfig": {"maxOutputTokens": 64},
        }
        return f"/v1beta/models/{model}:generateContent", {"X-Probe-Vendor": "gemini"}, body

    if vendor == "gemini-explicit":
        model = "gemini-2.5-flash"
        system = fixture_system(min_tokens_for_model("gemini", model))
        create_body = {
            "model": f"models/{model}",
            "ttl": "3600s",
            "systemInstruction": {"parts": [{"text": system}]},
            "tools": [{"functionDeclarations": [{"name": "lookup_lore", "description": "lore"}]}],
        }
        gen_body = {
            "contents": [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages],
            "generationConfig": {"maxOutputTokens": 64},
        }
        # 发送端对显式 Gemini 先 create 再 generate；此处返回 create，generate 由 send 第二次补
        return "/v1beta/cachedContents", {"X-Probe-Vendor": "gemini", "X-Probe-Next": "generate"}, {
            "_create": create_body,
            "_generate": gen_body,
            "_model": model,
        }

    if vendor == "dashscope":
        model = "qwen-plus"
        system = fixture_system(min_tokens_for_model("dashscope", model))
        config = {
            "mode": "explicit",
            "ttl": "5m",
            "breakpoints": ["system", "history_tail"],
            "explicitMarkers": True,
        }
        plan = build_plan(
            config=config,
            protocol="openai_compatible_chat",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=model,
            family="cn_best_effort",
            strategy="explicit",
            explicit_markers=True,
        )
        msgs = [{"role": "system", "content": system}, *messages]
        body = {"model": model, "messages": dashscope_mark_messages(msgs, plan)}
        return "/compatible-mode/v1/chat/completions", {"X-Probe-Vendor": "dashscope"}, body

    if vendor == "best-effort":
        model = "deepseek-chat"
        system = fixture_system(1024)
        body = {"model": model, "messages": [{"role": "system", "content": system}, *messages]}
        return "/v1/chat/completions", {"X-Probe-Vendor": "best_effort"}, body

    raise ValueError(f"unknown vendor {vendor}")


def http_json(
    url: str,
    *,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed if isinstance(parsed, dict) else {"raw": parsed}


def send_one(base: str, vendor: str, *, extra_turn: bool = False) -> dict[str, Any]:
    path, headers, body = build_vendor_payload(vendor, extra_turn=extra_turn)
    if vendor == "gemini-explicit":
        create_body = body["_create"]
        gen_body = dict(body["_generate"])
        model = body["_model"]
        status, created = http_json(base + "/v1beta/cachedContents", body=create_body, headers=headers)
        if status >= 400:
            return {"ok": False, "vendor": vendor, "status": status, "response": created, "stage": "cachedContents"}
        name = created.get("name")
        if isinstance(name, str) and name:
            gen_body["cachedContent"] = name
        status2, generated = http_json(
            base + f"/v1beta/models/{model}:generateContent", body=gen_body, headers=headers
        )
        return {
            "ok": status2 < 400,
            "vendor": vendor,
            "status": status2,
            "create": created,
            "response": generated,
        }
    status, payload = http_json(base + path, body=body, headers=headers)
    return {"ok": status < 400, "vendor": vendor, "status": status, "path": path, "response": payload}


def summarize_send(result: dict[str, Any]) -> dict[str, Any]:
    resp = result.get("response") if isinstance(result.get("response"), dict) else {}
    created = result.get("create") if isinstance(result.get("create"), dict) else {}
    n = resp.get("normalized") if isinstance(resp.get("normalized"), dict) else {}
    c = created.get("normalized") if isinstance(created.get("normalized"), dict) else {}
    write = n.get("cacheWriteInputTokens") or 0
    if c.get("cacheWriteInputTokens"):
        write = int(write) + int(c.get("cacheWriteInputTokens") or 0)
    return {
        "vendor": result.get("vendor"),
        "status": result.get("status"),
        "cacheReadInputTokens": n.get("cacheReadInputTokens"),
        "cacheWriteInputTokens": write,
        "inputTokens": n.get("inputTokens"),
        "cacheHitRate": n.get("cacheHitRate"),
        "createWriteInputTokens": c.get("cacheWriteInputTokens"),
        "probe": resp.get("probe"),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> int:
    store = CacheStore(Path(args.store))
    if args.reset:
        store.reset()
    httpd = make_server(args.host, args.port, store)
    print(f"local cache-hit probe on http://{args.host}:{args.port}  store={store.path}", flush=True)
    print("GET /health  POST /reset  vendor routes under /v1/*", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        httpd.server_close()
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    base = args.url.rstrip("/")
    try:
        if args.reset:
            http_json(base + "/reset", body={})
        result = send_one(base, args.vendor, extra_turn=args.extra_turn)
    except urllib.error.URLError as exc:
        print(
            f"连不上 {base}（{exc}）。先在另一终端启动：\n"
            f"  python backend/scripts/local_cache_hit_probe.py serve --host 127.0.0.1 --port 8765",
            file=sys.stderr,
        )
        return 2
    print(json.dumps({**result, "summary": summarize_send(result)}, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_demo(args: argparse.Namespace) -> int:
    store = CacheStore(Path(args.store))
    store.reset()
    httpd = make_server(args.host, args.port, store)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://{args.host}:{args.port}"
    rows: list[dict[str, Any]] = []
    failed = False
    try:
        health_status, health = http_json(base + "/health", method="GET")
        if health_status != 200 or not health.get("ok"):
            print("health check failed", health, file=sys.stderr)
            return 1
        vendors = list(VENDORS) if args.vendor == "all" else [args.vendor]
        for vendor in vendors:
            first = send_one(base, vendor, extra_turn=False)
            second = send_one(base, vendor, extra_turn=False)
            third = send_one(base, vendor, extra_turn=True)
            s1, s2, s3 = summarize_send(first), summarize_send(second), summarize_send(third)
            rows.append({"vendor": vendor, "write": s1, "identical_read": s2, "extra_turn": s3})
            if vendor == "gemini-explicit":
                # 应用路径：先 cachedContents（写）再 generateContent（读）
                write_ok = (s1.get("createWriteInputTokens") or 0) > 0
                read_ok = (s1.get("cacheReadInputTokens") or 0) > 0 and (s2.get("cacheReadInputTokens") or 0) > 0
            else:
                write_ok = (s1.get("cacheWriteInputTokens") or 0) > 0 and (s1.get("cacheReadInputTokens") or 0) == 0
                read_ok = (s2.get("cacheReadInputTokens") or 0) > 0
            if not first.get("ok") or not second.get("ok") or not write_ok or not read_ok:
                failed = True
                rows[-1]["failed"] = {
                    "write_ok": write_ok,
                    "read_ok": read_ok,
                    "first_ok": first.get("ok"),
                    "second_ok": second.get("ok"),
                    "third_ok": third.get("ok"),
                }
        report = {
            "ok": not failed,
            "base": base,
            "note": "prefix-match local probe; no real provider calls",
            "rows": rows,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not failed else 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="本地 prompt cache 前缀命中探测（不打真实厂商）")
    sub = p.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="启动本机接收端")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--store", default=str(DEFAULT_STORE))
    serve.add_argument("--reset", action="store_true")
    serve.set_defaults(func=cmd_serve)

    send = sub.add_parser("send", help="向本机接收端发一条应用形状的请求")
    send.add_argument("--url", default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    send.add_argument("--vendor", choices=VENDORS, required=True)
    send.add_argument("--extra-turn", action="store_true", help="同一 system 前缀上再追加一轮用户消息")
    send.add_argument("--reset", action="store_true", help="先 POST /reset")
    send.set_defaults(func=cmd_send)

    demo = sub.add_parser("demo", help="进程内拉起接收端，对每家厂商写一次再读一次")
    demo.add_argument("--host", default=DEFAULT_HOST)
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.add_argument("--store", default=str(DEFAULT_STORE))
    demo.add_argument("--vendor", choices=("all",) + VENDORS, default="all")
    demo.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
