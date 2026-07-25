from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
MIGRATED_FILES = (
    BACKEND_ROOT / "app" / "llm" / "openai_compat.py",
    BACKEND_ROOT / "app" / "fork_index.py",
    BACKEND_ROOT / "app" / "routes" / "generate.py",
    BACKEND_ROOT / "app" / "routes" / "assistant.py",
    BACKEND_ROOT / "app" / "routes" / "import_export.py",
    BACKEND_ROOT / "app" / "services" / "assistant_agent.py",
    BACKEND_ROOT / "app" / "services" / "generate_web_search_runtime.py",
    BACKEND_ROOT / "app" / "services" / "web_search.py",
    BACKEND_ROOT / "app" / "services" / "mvu_daemon.py",
    BACKEND_ROOT / "app" / "services" / "mvu_agent.py",
    BACKEND_ROOT / "app" / "group_mvu.py",
    BACKEND_ROOT / "app" / "content_regex_scanner.py",
    BACKEND_ROOT / "app" / "content_regex_queue.py",
    BACKEND_ROOT / "app" / "assistant_tools" / "executor.py",
    BACKEND_ROOT / "app" / "assistant_tools" / "handlers" / "web_search.py",
    BACKEND_ROOT / "app" / "storage.py",
)


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in {"Exception", "BaseException"}
    return False


def _is_empty_literal(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return node.value in {None, False}
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.Tuple)):
        return len(node.elts if hasattr(node, "elts") else node.keys) == 0
    return False


def _dangerous_handler_reason(handler: ast.ExceptHandler) -> str | None:
    if not _is_broad_exception(handler) or len(handler.body) != 1:
        return None
    statement = handler.body[0]
    if isinstance(statement, ast.Pass):
        return "pass"
    if isinstance(statement, ast.Continue):
        return "continue"
    if isinstance(statement, ast.Return) and _is_empty_literal(statement.value):
        return "empty return"
    return None


def test_migrated_t802_domain_has_no_broad_silent_exception_handlers() -> None:
    violations: list[str] = []
    for path in MIGRATED_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            reason = _dangerous_handler_reason(node)
            if reason:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {reason}")

    assert violations == []


def test_generate_routes_do_not_reintroduce_bare_sse_or_legacy_json_errors() -> None:
    source = (BACKEND_ROOT / "app" / "routes" / "generate.py").read_text(encoding="utf-8")

    assert 'yield _sse("error"' not in source
    assert 'JSONResponse({"ok": False, "error": str(e)}' not in source


def test_assistant_routes_do_not_reintroduce_legacy_ok_false_errors() -> None:
    source = (BACKEND_ROOT / "app" / "routes" / "assistant.py").read_text(encoding="utf-8")
    agent_source = (BACKEND_ROOT / "app" / "services" / "assistant_agent.py").read_text(encoding="utf-8")
    mvu_agent_source = (BACKEND_ROOT / "app" / "services" / "mvu_agent.py").read_text(encoding="utf-8")
    mvu_daemon_source = (BACKEND_ROOT / "app" / "services" / "mvu_daemon.py").read_text(encoding="utf-8")

    assert 'return {"ok": False, "error": "not found"' not in source
    assert '"ok": False,\n                    "error": result.error' not in source
    assert "except Exception:\n                args = {}" not in agent_source
    assert 'AssistantAgentEvent("error", {"message": str(exc)})' not in agent_source
    assert "except Exception:\n            normalized.append(m)" not in source
    assert "except json.JSONDecodeError:\n                        args = {}" not in mvu_agent_source
    assert "except asyncio.QueueFull:\n            pass" not in mvu_daemon_source


def test_storage_cleanup_and_fork_index_do_not_reintroduce_silent_fallbacks() -> None:
    storage_source = (BACKEND_ROOT / "app" / "storage.py").read_text(encoding="utf-8")
    fork_source = (BACKEND_ROOT / "app" / "fork_index.py").read_text(encoding="utf-8")

    assert "ignore_errors=True" not in storage_source
    assert "except OSError:\n            pass" not in storage_source
    assert "except Exception:\n                    continue" not in storage_source
    assert "except Exception:\n        return _empty_index()" not in fork_source


def test_content_regex_display_time_contract_is_locked() -> None:
    """F-010 semantic A: persist raw content; generate must not rewrite via pipeline."""
    generate_source = (BACKEND_ROOT / "app" / "routes" / "generate.py").read_text(encoding="utf-8")
    scanner_source = (BACKEND_ROOT / "app" / "content_regex_scanner.py").read_text(encoding="utf-8")
    inventory = (
        REPO_ROOT / "docs" / "audits" / "v0800-backend-fallback-inventory.md"
    ).read_text(encoding="utf-8")

    assert "apply_content_regex_pipeline" not in generate_source
    assert "apply_content_regex_pipeline" in scanner_source
    assert "F-010" in inventory
    assert "decided-A" in inventory
    assert "verified-gap" not in inventory.split("F-010", 1)[1].split("\n", 1)[0]
