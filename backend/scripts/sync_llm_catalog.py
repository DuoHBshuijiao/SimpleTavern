"""同步内建 LLM 供应商目录（T-820-A1）。

唯一信源：pi ``packages/ai/src/providers/*.ts``（供应商 id/name/baseUrl/api/env/oauth）。
模型元数据：models.dev ``api.json``（reasoning_options / cost / limit / temperature / experimental.modes）
与 OpenRouter ``/api/v1/models``（supported_parameters / supported_efforts）。

产物（入库，运行期不联网）：
- ``app/llm/catalog/providers.generated.json``
- ``app/llm/catalog/models.generated.json``

用法::

    cd backend
    python scripts/sync_llm_catalog.py            # 重新生成
    python scripts/sync_llm_catalog.py --check    # 校验产物与线上源是否一致（CI 可用）

人工维护部分放 ``providers.overlay.json``（中文标签、地区、authStyle、占位符、协议支持、缓存策略），脚本不改写它。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "app" / "llm" / "catalog"
PROVIDERS_OUT = CATALOG_DIR / "providers.generated.json"
MODELS_OUT = CATALOG_DIR / "models.generated.json"
OVERLAY_PATH = CATALOG_DIR / "providers.overlay.json"

PI_REPO = "earendil-works/pi"
PI_PATH = "packages/ai/src/providers"
PI_API = f"https://api.github.com/repos/{PI_REPO}/contents/{PI_PATH}"
PI_COMMITS = f"https://api.github.com/repos/{PI_REPO}/commits?path={PI_PATH}&per_page=1"
PI_RAW = f"https://raw.githubusercontent.com/{PI_REPO}/main/{PI_PATH}/"
MODELS_DEV_URL = "https://models.dev/api.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# pi 中非供应商定义文件
_SKIP_FILES = {"all.ts", "faux.ts", "data-json.d.ts", "cloudflare-auth.ts", "cloudflare-stream.ts",
               "opencode-headers.ts", "openrouter-images.ts", "radius.ts", "radius-config.ts"}

# pi api → SimpleTavern 协议 id（None = 本版本不支持，仅登记）
PI_API_TO_PROTOCOL: dict[str, str | None] = {
    "openai-completions": "openai_compatible_chat",
    "openai-responses": "openai_responses",
    "azure-openai-responses": "openai_responses",
    "openai-codex-responses": "openai_responses",
    "anthropic-messages": "anthropic_messages",
    "google-generative-ai": "gemini_generate_content",
    "google-vertex": "gemini_generate_content",
    "bedrock-converse-stream": None,
    "mistral-conversations": None,
}

# pi provider id → models.dev provider id（不同名时）
PI_TO_MODELS_DEV: dict[str, str] = {
    "fireworks": "fireworks-ai",
    "together": "togetherai",
    "kimi-coding": "kimi-for-coding",
    "zai-coding-cn": "zai-coding-plan",
    "qwen-token-plan": "alibaba-token-plan",
    "qwen-token-plan-cn": "alibaba-token-plan-cn",
    "qwen-token-plan-individual": "alibaba-token-plan",
    "ant-ling": "bailing",
    "azure-openai-responses": "azure",
    "openai-codex": "openai",
}

# 不在 pi 名录但系统已有 / overlay 需要的 models.dev 供应商（经核查保留）
EXTRA_MODELS_DEV_PROVIDERS = [
    "alibaba", "alibaba-cn", "siliconflow", "siliconflow-cn", "zhipuai", "volcengine",
    "zenmux", "perplexity", "google-vertex-anthropic", "minimax-cn-coding-plan",
]


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "SimpleTavern-catalog-sync"})
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "SimpleTavern-catalog-sync"})
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


_RE_ID = re.compile(r'\bid:\s*"([^"]+)"')
_RE_NAME = re.compile(r'\bname:\s*"([^"]+)"')
_RE_BASE_URL = re.compile(r'\bbaseUrl:\s*"([^"]+)"')
_RE_API_IMPORT = re.compile(r'from\s+"\.\./api/([a-z0-9-]+)\.lazy\.ts"')
_RE_ENV_LIST = re.compile(r'envApiKeyAuth\([^,]+,\s*\[([^\]]*)\]')
_RE_ENV_CONST = re.compile(r'\b([A-Z][A-Z0-9_]+_ENV)\b')


def parse_pi_provider(source: str, filename: str) -> dict[str, Any] | None:
    """从 pi provider .ts 源码抽取供应商元数据。找不到 createProvider 的文件返回 None。"""
    if "createProvider" not in source:
        return None
    ids = _RE_ID.findall(source)
    if not ids:
        return None
    provider_id = ids[-1]  # createProvider 的 id 通常在文件末尾
    # name 也可能出现在 auth/oauth 描述里；只取紧跟 createProvider id 之后的那个
    block = re.search(r'\bid:\s*"' + re.escape(provider_id) + r'"\s*,\s*name:\s*"([^"]+)"', source)
    name = block.group(1) if block else provider_id
    base_urls = _RE_BASE_URL.findall(source)
    apis = sorted(set(_RE_API_IMPORT.findall(source)))
    env_keys: list[str] = []
    for group in _RE_ENV_LIST.findall(source):
        env_keys.extend(re.findall(r'"([A-Z0-9_]+)"', group))
    env_keys.extend(c for c in _RE_ENV_CONST.findall(source) if c not in env_keys)
    return {
        "id": provider_id,
        "name": name,
        "baseUrl": base_urls[-1] if base_urls else None,
        "apis": apis,
        "protocols": sorted({p for a in apis if (p := PI_API_TO_PROTOCOL.get(a))}),
        "unsupportedApis": sorted(a for a in apis if PI_API_TO_PROTOCOL.get(a) is None),
        "envKeys": env_keys,
        "hasOAuth": "lazyOAuth(" in source,
        "oauthOnly": "lazyOAuth(" in source and "envApiKeyAuth(" not in source and "ApiKeyAuth" not in source,
        "sourceFile": filename,
    }


def fetch_pi_providers() -> tuple[list[dict[str, Any]], str | None]:
    listing = _http_json(PI_API)
    files = sorted(
        item["name"]
        for item in listing
        if item.get("type") == "file"
        and item["name"].endswith(".ts")
        and not item["name"].endswith(".models.ts")
        and item["name"] not in _SKIP_FILES
    )
    providers: list[dict[str, Any]] = []
    for fname in files:
        parsed = parse_pi_provider(_http_text(PI_RAW + fname), fname)
        if parsed:
            providers.append(parsed)
    commit_sha: str | None = None
    try:
        commits = _http_json(PI_COMMITS)
        if isinstance(commits, list) and commits:
            commit_sha = commits[0].get("sha")
    except Exception:  # noqa: BLE001 - 仅用于溯源信息
        commit_sha = None
    return providers, commit_sha


def _efforts_from_reasoning_options(options: Any) -> tuple[list[str], bool]:
    efforts: list[str] = []
    toggle = False
    if isinstance(options, list):
        for opt in options:
            if not isinstance(opt, dict):
                continue
            if opt.get("type") == "effort" and isinstance(opt.get("values"), list):
                efforts = [str(v) for v in opt["values"]]
            elif opt.get("type") == "toggle":
                toggle = True
    return efforts, toggle


def compact_model(raw: dict[str, Any]) -> dict[str, Any]:
    efforts, toggle = _efforts_from_reasoning_options(raw.get("reasoning_options"))
    out: dict[str, Any] = {
        "name": raw.get("name") or raw.get("id"),
        "family": raw.get("family"),
        "reasoning": bool(raw.get("reasoning")),
        "temperature": raw.get("temperature", True) is not False,
        "toolCall": bool(raw.get("tool_call")),
    }
    if efforts:
        out["efforts"] = efforts
    if toggle:
        out["reasoningToggle"] = True
    cost = raw.get("cost")
    if isinstance(cost, dict):
        out["cost"] = {k: cost[k] for k in ("input", "output", "cache_read", "cache_write") if k in cost}
    limit = raw.get("limit")
    if isinstance(limit, dict):
        out["limit"] = {k: limit[k] for k in ("context", "output") if k in limit}
    exp = raw.get("experimental")
    if isinstance(exp, dict) and isinstance(exp.get("modes"), dict):
        modes: dict[str, Any] = {}
        for mode_name, mode in exp["modes"].items():
            if not isinstance(mode, dict):
                continue
            entry: dict[str, Any] = {}
            provider = mode.get("provider")
            if isinstance(provider, dict):
                if isinstance(provider.get("body"), dict):
                    entry["body"] = provider["body"]
                if isinstance(provider.get("headers"), dict):
                    entry["headers"] = provider["headers"]
            if isinstance(mode.get("cost"), dict):
                entry["cost"] = mode["cost"]
            modes[mode_name] = entry
        if modes:
            out["modes"] = modes
    if raw.get("release_date"):
        out["releaseDate"] = raw["release_date"]
    return out


def build_models_catalog(pi_providers: list[dict[str, Any]], models_dev: dict[str, Any], openrouter: dict[str, Any]) -> dict[str, Any]:
    wanted: dict[str, str] = {}
    for p in pi_providers:
        md_id = PI_TO_MODELS_DEV.get(p["id"], p["id"])
        if md_id in models_dev:
            wanted[p["id"]] = md_id
    for md_id in EXTRA_MODELS_DEV_PROVIDERS:
        if md_id in models_dev:
            wanted[md_id] = md_id

    providers_out: dict[str, Any] = {}
    for st_id, md_id in sorted(wanted.items()):
        src = models_dev[md_id]
        models = src.get("models") if isinstance(src, dict) else None
        if not isinstance(models, dict):
            continue
        providers_out[st_id] = {
            "modelsDevId": md_id,
            "name": src.get("name"),
            "doc": src.get("doc"),
            "api": src.get("api"),
            "models": {mid: compact_model(m) for mid, m in sorted(models.items()) if isinstance(m, dict)},
        }

    or_params: dict[str, Any] = {}
    for item in openrouter.get("data", []) if isinstance(openrouter, dict) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        entry: dict[str, Any] = {}
        params = item.get("supported_parameters")
        if isinstance(params, list):
            entry["supportedParameters"] = sorted(str(p) for p in params)
        reasoning = item.get("reasoning")
        if isinstance(reasoning, dict) and isinstance(reasoning.get("supported_efforts"), list):
            entry["supportedEfforts"] = [str(e) for e in reasoning["supported_efforts"]]
        pricing = item.get("pricing")
        if isinstance(pricing, dict):
            cache = {k: pricing[k] for k in ("input_cache_read", "input_cache_write") if k in pricing}
            if cache:
                entry["cachePricing"] = cache
        if entry:
            or_params[item["id"]] = entry

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {"modelsDev": MODELS_DEV_URL, "openrouter": OPENROUTER_URL},
        "providers": providers_out,
        "openrouter": or_params,
    }


def build_providers_catalog(pi_providers: list[dict[str, Any]], commit_sha: str | None) -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "repo": PI_REPO,
            "path": PI_PATH,
            "commit": commit_sha,
            "url": f"https://github.com/{PI_REPO}/tree/main/{PI_PATH}",
        },
        "providers": pi_providers,
    }


def _strip_volatile(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("generatedAt", None)
    return out


def _dump(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="仅校验产物是否与线上源一致（不写文件）")
    args = parser.parse_args(argv)

    print("[sync] fetching pi providers ...", file=sys.stderr)
    pi_providers, commit_sha = fetch_pi_providers()
    print(f"[sync] {len(pi_providers)} providers (pi@{commit_sha or 'unknown'})", file=sys.stderr)
    print("[sync] fetching models.dev ...", file=sys.stderr)
    models_dev = _http_json(MODELS_DEV_URL)
    print("[sync] fetching openrouter ...", file=sys.stderr)
    openrouter = _http_json(OPENROUTER_URL)

    providers_doc = build_providers_catalog(pi_providers, commit_sha)
    models_doc = build_models_catalog(pi_providers, models_dev, openrouter)

    if not OVERLAY_PATH.exists():
        print(f"[sync] WARNING overlay missing: {OVERLAY_PATH}", file=sys.stderr)
    else:
        overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
        known = {p["id"] for p in pi_providers}
        for entry in overlay.get("providers", []):
            pi_id = entry.get("piId")
            if pi_id and pi_id not in known:
                print(f"[sync] WARNING overlay piId not in pi catalog: {pi_id}", file=sys.stderr)
        missing_overlay = [p["id"] for p in pi_providers if not any(e.get("piId") == p["id"] for e in overlay.get("providers", []))]
        if missing_overlay:
            print(f"[sync] NOTE pi providers without overlay (will use defaults): {', '.join(missing_overlay)}", file=sys.stderr)

    if args.check:
        ok = True
        for path, doc in ((PROVIDERS_OUT, providers_doc), (MODELS_OUT, models_doc)):
            if not path.exists():
                print(f"[check] missing {path}", file=sys.stderr)
                ok = False
                continue
            current = json.loads(path.read_text(encoding="utf-8"))
            if _strip_volatile(current) != _strip_volatile(doc):
                print(f"[check] OUTDATED {path.name}", file=sys.stderr)
                ok = False
        return 0 if ok else 1

    _dump(PROVIDERS_OUT, providers_doc)
    _dump(MODELS_OUT, models_doc)
    total_models = sum(len(p["models"]) for p in models_doc["providers"].values())
    print(f"[sync] wrote {PROVIDERS_OUT.name} ({len(pi_providers)} providers)", file=sys.stderr)
    print(f"[sync] wrote {MODELS_OUT.name} ({len(models_doc['providers'])} providers, {total_models} models, "
          f"{len(models_doc['openrouter'])} openrouter entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
