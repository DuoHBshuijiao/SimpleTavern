"""本地定价引擎（T-808）。

优先级：
1. 供应商云端 cost（调用方保留，本模块不覆盖）
2. resolvedModel 精确 ID
3. provider + 官方/用户别名（最短 3 字符，禁止单字映射）
4. 版本化正则 alias（模式有效部分最短 3 字符）
5. 未匹配：unknown，不得填 0

用户覆盖存 ``data/pricing_rules.json``；目录价格只读。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.errors import AppError
from app.llm.catalog.catalog import get_catalog
from app.storage import get_pricing_rules_path, read_json, write_json


PRICING_RULES_VERSION = 1
MIN_ALIAS_LEN = 3
_USER_RULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")

_COST_KEYS = (
    ("inputPerMillion", "input"),
    ("outputPerMillion", "output"),
    ("cacheReadPerMillion", "cache_read"),
    ("cacheWritePerMillion", "cache_write"),
)

# 生成热路径会反复 resolve；目录规则与用户文件按 mtime/目录实例缓存。
_catalog_rules_memo: tuple[int, str | None, list[dict[str, Any]]] | None = None
_user_store_memo: tuple[float | None, dict[str, Any]] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def pricing_rules_path():
    return get_pricing_rules_path()


def _as_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _alias_ok(alias: str) -> bool:
    return len(alias.strip()) >= MIN_ALIAS_LEN


def _regex_ok(pattern: str) -> bool:
    compact = re.sub(r"[\\^$.*+?()[\]{}|]", "", pattern)
    return len(compact.strip()) >= MIN_ALIAS_LEN


def _rule_id_for_catalog(provider: str, model_id: str) -> str:
    return f"catalog:{provider}:{model_id}"


def _empty_store() -> dict[str, Any]:
    return {"version": PRICING_RULES_VERSION, "updatedAt": None, "rules": []}


def _parse_effective_dt(raw: Any, *, end: bool) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    date_only = "T" not in text and " " not in text
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if end and date_only:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def _within_effective_window(rule: dict[str, Any]) -> bool:
    start = _parse_effective_dt(rule.get("effectiveFrom"), end=False)
    end = _parse_effective_dt(rule.get("effectiveTo"), end=True)
    if start is None and end is None:
        return True
    now = datetime.now(timezone.utc)
    if start is not None and now < start:
        return False
    if end is not None and now > end:
        return False
    return True


def load_user_pricing_store() -> dict[str, Any]:
    global _user_store_memo
    path = pricing_rules_path()
    if not path.exists():
        _user_store_memo = (None, _empty_store())
        return _user_store_memo[1]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    if _user_store_memo is not None and _user_store_memo[0] == mtime:
        return _user_store_memo[1]
    try:
        raw = read_json(path)
    except Exception as exc:
        raise AppError(
            code="data_corrupted",
            message="本地价格表无法读取",
            detail=str(exc),
            source="pricing.rules",
            status_code=500,
            retryable=True,
            suggested_action="检查 data/pricing_rules.json 是否损坏",
        ) from exc
    if not isinstance(raw, dict):
        store = _empty_store()
        _user_store_memo = (mtime, store)
        return store
    rules = raw.get("rules")
    if not isinstance(rules, list):
        rules = []
    store = {
        "version": int(raw.get("version") or PRICING_RULES_VERSION),
        "updatedAt": raw.get("updatedAt"),
        "rules": [r for r in rules if isinstance(r, dict)],
    }
    _user_store_memo = (mtime, store)
    return store


def save_user_pricing_store(store: dict[str, Any]) -> dict[str, Any]:
    global _user_store_memo
    payload = {
        "version": PRICING_RULES_VERSION,
        "updatedAt": _now_iso(),
        "rules": list(store.get("rules") or []),
    }
    write_json(pricing_rules_path(), payload)
    _user_store_memo = None
    return payload


def catalog_pricing_rules() -> list[dict[str, Any]]:
    global _catalog_rules_memo
    catalog = get_catalog()
    key = (id(catalog), catalog.models_generated_at)
    if (
        _catalog_rules_memo is not None
        and _catalog_rules_memo[0] == key[0]
        and _catalog_rules_memo[1] == key[1]
    ):
        return _catalog_rules_memo[2]
    out: list[dict[str, Any]] = []
    for row in catalog.iter_model_cost_rows():
        cost = row.get("cost") if isinstance(row.get("cost"), dict) else {}
        rule = {
            "id": _rule_id_for_catalog(str(row.get("provider") or ""), str(row.get("canonicalModelId") or "")),
            "provider": row.get("provider"),
            "canonicalModelId": row.get("canonicalModelId"),
            "aliases": [a for a in (row.get("aliases") or []) if isinstance(a, str) and _alias_ok(a)],
            "regexAliases": [],
            "currency": "USD",
            "source": "catalog",
            "readOnly": True,
            "enabled": True,
            "updatedAt": row.get("updatedAt"),
        }
        for public_key, catalog_key in _COST_KEYS:
            amount = _as_float(cost.get(catalog_key))
            if amount is not None:
                rule[public_key] = amount
        if any(k in rule for k, _ in _COST_KEYS):
            out.append(rule)
    _catalog_rules_memo = (key[0], key[1], out)
    return out


def _validate_user_rule(rule: dict[str, Any], *, rule_id: str) -> dict[str, Any]:
    if not _USER_RULE_ID_RE.match(rule_id) or rule_id.startswith("catalog:"):
        raise AppError(
            code="request_validation_failed",
            message="价格规则 id 非法",
            detail="用户规则 id 须为 3–128 位字母数字，且不能以 catalog: 开头",
            source="pricing.rules",
            status_code=422,
        )
    aliases: list[str] = []
    for raw in rule.get("aliases") or []:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        if not _alias_ok(text):
            raise AppError(
                code="request_validation_failed",
                message="模型别名过短，拒绝自动映射",
                detail=f"alias={text!r} 短于 {MIN_ALIAS_LEN} 个字符（禁止「克」这类单字命中）",
                source="pricing.rules",
                status_code=422,
            )
        aliases.append(text)
    regex_aliases: list[str] = []
    for raw in rule.get("regexAliases") or []:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        if not _regex_ok(text):
            raise AppError(
                code="request_validation_failed",
                message="正则别名过宽，拒绝自动映射",
                detail=f"regexAlias={text!r} 有效部分短于 {MIN_ALIAS_LEN} 个字符",
                source="pricing.rules",
                status_code=422,
            )
        try:
            re.compile(text)
        except re.error as exc:
            raise AppError(
                code="request_validation_failed",
                message="正则别名无法编译",
                detail=str(exc),
                source="pricing.rules",
                status_code=422,
            ) from exc
        regex_aliases.append(text)
    out: dict[str, Any] = {
        "id": rule_id,
        "provider": str(rule.get("provider") or "").strip() or None,
        "canonicalModelId": str(rule.get("canonicalModelId") or "").strip() or None,
        "aliases": aliases,
        "regexAliases": regex_aliases,
        "currency": str(rule.get("currency") or "USD").strip() or "USD",
        "source": "user",
        "readOnly": False,
        "enabled": bool(rule.get("enabled", True)),
        "effectiveFrom": rule.get("effectiveFrom"),
        "effectiveTo": rule.get("effectiveTo"),
        "sourceUrl": rule.get("sourceUrl"),
        "updatedAt": _now_iso(),
    }
    for public_key, _catalog_key in _COST_KEYS:
        amount = _as_float(rule.get(public_key))
        if amount is not None:
            out[public_key] = amount
    if not any(k in out for k, _ in _COST_KEYS):
        raise AppError(
            code="request_validation_failed",
            message="价格规则缺少单价",
            detail="至少提供 inputPerMillion / outputPerMillion / cacheReadPerMillion / cacheWritePerMillion 之一",
            source="pricing.rules",
            status_code=422,
        )
    return out


def upsert_user_pricing_rule(rule_id: str, body: dict[str, Any]) -> dict[str, Any]:
    rid = (rule_id or "").strip()
    rule = _validate_user_rule(body if isinstance(body, dict) else {}, rule_id=rid)
    store = load_user_pricing_store()
    rules = [r for r in store.get("rules") or [] if str(r.get("id") or "") != rid]
    rules.append(rule)
    # 不要改缓存里的 store：write 失败时否则会把未落盘规则留在内存里。
    save_user_pricing_store({"rules": rules})
    return rule


def list_pricing_rules() -> dict[str, Any]:
    catalog = catalog_pricing_rules()
    user_store = load_user_pricing_store()
    user_rules = []
    for raw in user_store.get("rules") or []:
        item = dict(raw)
        item["source"] = "user"
        item["readOnly"] = False
        user_rules.append(item)
    return {
        "version": PRICING_RULES_VERSION,
        "updatedAt": user_store.get("updatedAt"),
        "catalogCount": len(catalog),
        "userCount": len(user_rules),
        "rules": user_rules + catalog,
    }


def _provider_matches(rule: dict[str, Any], provider: str | None) -> bool:
    rule_provider = _norm(rule.get("provider"))
    if not rule_provider:
        return True
    return rule_provider == _norm(provider)


def _needles(resolved_model: str | None, requested_model: str | None) -> list[str]:
    out: list[str] = []
    for item in (resolved_model, requested_model):
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _exact_canonical(rule: dict[str, Any], needles: list[str]) -> bool:
    canonical = str(rule.get("canonicalModelId") or "").strip()
    if not canonical:
        return False
    want = _norm(canonical)
    return any(_norm(n) == want for n in needles)


def _alias_hit(rule: dict[str, Any], needles: list[str]) -> bool:
    aliases = [a for a in (rule.get("aliases") or []) if isinstance(a, str) and _alias_ok(a)]
    lowered = {_norm(a) for a in aliases}
    return any(_norm(n) in lowered for n in needles if _alias_ok(n))


def _regex_hit(rule: dict[str, Any], needles: list[str]) -> bool:
    for pattern in rule.get("regexAliases") or []:
        if not isinstance(pattern, str) or not _regex_ok(pattern):
            continue
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        if any(compiled.search(n) for n in needles):
            return True
    return False


def resolve_pricing_rule(
    *,
    provider: str | None,
    resolved_model: str | None,
    requested_model: str | None,
) -> dict[str, Any] | None:
    user_rules = [
        r
        for r in (load_user_pricing_store().get("rules") or [])
        if isinstance(r, dict) and r.get("enabled", True) and _within_effective_window(r)
    ]
    catalog_rules = [r for r in catalog_pricing_rules() if _within_effective_window(r)]
    needles = _needles(resolved_model, requested_model)
    if not needles:
        return None

    def _search(predicate) -> dict[str, Any] | None:
        for group in (user_rules, catalog_rules):
            for rule in group:
                if not _provider_matches(rule, provider):
                    continue
                if predicate(rule, needles):
                    return rule
        return None

    return (
        _search(_exact_canonical)
        or _search(_alias_hit)
        or _search(_regex_hit)
    )


def estimate_cost_from_usage(
    usage: dict[str, Any] | None,
    *,
    provider: str | None,
    resolved_model: str | None,
    requested_model: str | None,
) -> dict[str, Any] | None:
    """按本地价格表估算；无法可靠计算时返回 None（由调用方标 unknown）。"""
    if not isinstance(usage, dict) or not usage:
        return None
    rule = resolve_pricing_rule(
        provider=provider,
        resolved_model=resolved_model,
        requested_model=requested_model,
    )
    if rule is None:
        return None

    def _token(key: str, *alts: str) -> float:
        for k in (key, *alts):
            val = _as_float(usage.get(k))
            if val is not None:
                return max(0.0, val)
        return 0.0

    input_tokens = _token("inputTokens", "input_tokens")
    output_tokens = _token("outputTokens", "output_tokens")
    cache_read = _token("cacheReadInputTokens", "cache_read_input_tokens")
    cache_write = _token("cacheWriteInputTokens", "cache_write_input_tokens")
    rates = {
        "input": _as_float(rule.get("inputPerMillion")),
        "output": _as_float(rule.get("outputPerMillion")),
        "cacheRead": _as_float(rule.get("cacheReadPerMillion")),
        "cacheWrite": _as_float(rule.get("cacheWritePerMillion")),
    }
    if all(v is None for v in rates.values()):
        return None
    amount = 0.0
    used_any = False
    if rates["input"] is not None:
        amount += input_tokens * rates["input"] / 1_000_000.0
        used_any = True
    if rates["output"] is not None:
        amount += output_tokens * rates["output"] / 1_000_000.0
        used_any = True
    if rates["cacheRead"] is not None:
        amount += cache_read * rates["cacheRead"] / 1_000_000.0
        used_any = True
    if rates["cacheWrite"] is not None:
        amount += cache_write * rates["cacheWrite"] / 1_000_000.0
        used_any = True
    if not used_any:
        return None
    return {
        "amount": amount,
        "currency": str(rule.get("currency") or "USD"),
        "source": "estimated",
        "estimatedAmount": amount,
        "pricingRuleId": rule.get("id"),
    }


def merge_cost(provider_cost: dict[str, Any] | None, estimated: dict[str, Any] | None) -> dict[str, Any]:
    """云端 cost 不被本地估算覆盖；两者都没有则 unknown。"""
    if isinstance(provider_cost, dict) and provider_cost.get("source") == "provider":
        out = dict(provider_cost)
        if isinstance(estimated, dict):
            if estimated.get("estimatedAmount") is not None:
                out["estimatedAmount"] = estimated["estimatedAmount"]
            if estimated.get("pricingRuleId"):
                out["pricingRuleId"] = estimated["pricingRuleId"]
        return out
    if isinstance(estimated, dict) and estimated.get("source") == "estimated":
        return dict(estimated)
    return {"source": "unknown"}
