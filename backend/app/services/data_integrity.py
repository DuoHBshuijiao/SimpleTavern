"""Background startup scan and safe repair for chat-related JSON files."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.schemas import AssistantChat, Chat
from app.storage import (
    ASSISTANT_CHAT_FILENAME,
    CHAT_MEMORY_FILENAME,
    CHAT_RECORD_FILENAME,
    assistant_chat_path,
    assistant_workspace_chat_path,
    chats_dir,
    get_repo_root,
    write_json,
)


IntegrityIssueCode = Literal["empty", "all_zero", "invalid_utf8", "invalid_json", "schema_mismatch"]
IntegrityTargetKind = Literal[
    "chat_record",
    "legacy_chat",
    "chat_memory",
    "assistant_chat_global",
    "assistant_chat_workspace",
    "assistant_chat_session",
]
RepairAction = Literal["delete", "reset_json"]

STARTUP_SCAN_DELAY_SEC = 30
SCAN_INTERVAL_SEC = 10
READ_RETRY_DELAY_SEC = 0.15
READ_RETRY_ATTEMPTS = 2

_ISSUE_MESSAGES: dict[IntegrityIssueCode, str] = {
    "empty": "文件为空",
    "all_zero": "文件内容全为 0 字节",
    "invalid_utf8": "文件不是合法 UTF-8 文本",
    "invalid_json": "JSON 解析失败",
    "schema_mismatch": "JSON 结构不符合预期",
}

_REPAIR_ACTIONS: dict[IntegrityTargetKind, RepairAction] = {
    "chat_record": "delete",
    "legacy_chat": "delete",
    "chat_memory": "delete",
    "assistant_chat_global": "reset_json",
    "assistant_chat_workspace": "reset_json",
    "assistant_chat_session": "reset_json",
}


@dataclass(frozen=True)
class FileSnapshot:
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class StableFileRead:
    snapshot: FileSnapshot
    data: bytes


@dataclass(frozen=True)
class ScanTarget:
    path: Path
    kind: IntegrityTargetKind


@dataclass(frozen=True)
class ScanIssue:
    code: IntegrityIssueCode
    message: str
    detail: str | None = None


@dataclass(frozen=True)
class RecordedIssue:
    target: ScanTarget
    snapshot: FileSnapshot
    issue: ScanIssue
    discovered_at: str


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize_detail(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    if len(text) <= 240:
        return text
    return text[:237] + "..."


def _read_bytes_once(path: Path) -> StableFileRead | None:
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except FileNotFoundError:
        return None
    except OSError:
        return None

    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        return None
    return StableFileRead(
        snapshot=FileSnapshot(size=after.st_size, mtime_ns=after.st_mtime_ns),
        data=data,
    )


class DataIntegrityService:
    """Runs a one-shot startup scan and stores issues only in process memory."""

    def __init__(self) -> None:
        self._repo_root = get_repo_root().resolve()
        self._issues: dict[str, RecordedIssue] = {}
        self._lock = asyncio.Lock()
        self._started = False

    def _relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self._repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _is_allowed_target(self, path: Path) -> bool:
        resolved = path.resolve()
        assistant_global = assistant_chat_path().resolve()
        assistant_workspace = assistant_workspace_chat_path().resolve()
        chats_root = chats_dir().resolve()

        if resolved == assistant_global or resolved == assistant_workspace:
            return True
        try:
            relative = resolved.relative_to(chats_root)
        except ValueError:
            return False

        parts = relative.parts
        if len(parts) == 3 and parts[2] in {CHAT_RECORD_FILENAME, CHAT_MEMORY_FILENAME, ASSISTANT_CHAT_FILENAME}:
            return True
        if len(parts) == 2 and resolved.suffix.lower() == ".json":
            return parts[1] not in {CHAT_MEMORY_FILENAME, ASSISTANT_CHAT_FILENAME}
        return False

    def _build_target(self, path: Path) -> ScanTarget | None:
        resolved = path.resolve()
        if resolved == assistant_chat_path().resolve():
            return ScanTarget(path=resolved, kind="assistant_chat_global")
        if resolved == assistant_workspace_chat_path().resolve():
            return ScanTarget(path=resolved, kind="assistant_chat_workspace")

        chats_root = chats_dir().resolve()
        try:
            relative = resolved.relative_to(chats_root)
        except ValueError:
            return None

        parts = relative.parts
        if len(parts) == 3:
            filename = parts[2]
            if filename == CHAT_RECORD_FILENAME:
                return ScanTarget(path=resolved, kind="chat_record")
            if filename == CHAT_MEMORY_FILENAME:
                return ScanTarget(path=resolved, kind="chat_memory")
            if filename == ASSISTANT_CHAT_FILENAME:
                return ScanTarget(path=resolved, kind="assistant_chat_session")
            return None
        if len(parts) == 2 and resolved.suffix.lower() == ".json":
            if parts[1] in {CHAT_MEMORY_FILENAME, ASSISTANT_CHAT_FILENAME}:
                return None
            return ScanTarget(path=resolved, kind="legacy_chat")
        return None

    def _enumerate_targets(self) -> list[ScanTarget]:
        targets: list[ScanTarget] = []
        global_assistant = assistant_chat_path()
        if global_assistant.exists():
            targets.append(ScanTarget(path=global_assistant.resolve(), kind="assistant_chat_global"))

        workspace_assistant = assistant_workspace_chat_path()
        if workspace_assistant.exists():
            targets.append(ScanTarget(path=workspace_assistant.resolve(), kind="assistant_chat_workspace"))

        base = chats_dir()
        if base.exists():
            for character_dir in sorted(base.iterdir(), key=lambda p: p.name):
                if not character_dir.is_dir():
                    continue
                for entry in sorted(character_dir.iterdir(), key=lambda p: p.name):
                    if entry.is_dir():
                        record = entry / CHAT_RECORD_FILENAME
                        if record.exists():
                            targets.append(ScanTarget(path=record.resolve(), kind="chat_record"))
                        memory = entry / CHAT_MEMORY_FILENAME
                        if memory.exists():
                            targets.append(ScanTarget(path=memory.resolve(), kind="chat_memory"))
                        assistant = entry / ASSISTANT_CHAT_FILENAME
                        if assistant.exists():
                            targets.append(ScanTarget(path=assistant.resolve(), kind="assistant_chat_session"))
                        continue

                    if entry.suffix.lower() != ".json":
                        continue
                    if entry.name in {CHAT_MEMORY_FILENAME, ASSISTANT_CHAT_FILENAME}:
                        continue
                    if (character_dir / entry.stem / CHAT_RECORD_FILENAME).exists():
                        continue
                    targets.append(ScanTarget(path=entry.resolve(), kind="legacy_chat"))

        targets.sort(key=lambda item: self._relative_path(item.path))
        return targets

    async def _read_stable_bytes(self, path: Path) -> StableFileRead | None:
        for attempt in range(READ_RETRY_ATTEMPTS):
            first = await asyncio.to_thread(_read_bytes_once, path)
            if first is None:
                await asyncio.sleep(READ_RETRY_DELAY_SEC)
                continue

            await asyncio.sleep(READ_RETRY_DELAY_SEC)
            second = await asyncio.to_thread(_read_bytes_once, path)
            if second is None:
                await asyncio.sleep(READ_RETRY_DELAY_SEC)
                continue

            if first.snapshot == second.snapshot and first.data == second.data:
                return second
            if attempt < READ_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(READ_RETRY_DELAY_SEC)
        return None

    def _validate_chat_memory_schema(self, raw: Any) -> str | None:
        if isinstance(raw, str):
            return None
        if not isinstance(raw, dict):
            return "长期记忆文件必须是对象或字符串"
        content = raw.get("longTermMemory")
        if content is None:
            content = raw.get("content")
        if content is None:
            return "长期记忆文件缺少 longTermMemory/content 字段"
        if not isinstance(content, str):
            return "长期记忆字段必须是字符串"
        return None

    def _validate_schema(self, target: ScanTarget, raw: Any) -> str | None:
        try:
            if target.kind in {"chat_record", "legacy_chat"}:
                Chat.model_validate(raw)
                return None
            if target.kind == "chat_memory":
                return self._validate_chat_memory_schema(raw)
            AssistantChat.model_validate(raw)
            return None
        except ValidationError as exc:
            return _normalize_detail(str(exc))
        except ValueError as exc:
            return _normalize_detail(str(exc))

    async def _scan_target(self, target: ScanTarget) -> tuple[FileSnapshot, ScanIssue] | None:
        stable = await self._read_stable_bytes(target.path)
        if stable is None:
            return None

        data = stable.data
        if not data:
            return stable.snapshot, ScanIssue(code="empty", message=_ISSUE_MESSAGES["empty"])
        if all(byte == 0 for byte in data):
            return stable.snapshot, ScanIssue(code="all_zero", message=_ISSUE_MESSAGES["all_zero"])

        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return (
                stable.snapshot,
                ScanIssue(
                    code="invalid_utf8",
                    message=_ISSUE_MESSAGES["invalid_utf8"],
                    detail=_normalize_detail(str(exc)),
                ),
            )

        if not text.strip():
            return stable.snapshot, ScanIssue(code="empty", message=_ISSUE_MESSAGES["empty"])

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            return (
                stable.snapshot,
                ScanIssue(
                    code="invalid_json",
                    message=_ISSUE_MESSAGES["invalid_json"],
                    detail=_normalize_detail(str(exc)),
                ),
            )

        schema_error = self._validate_schema(target, raw)
        if schema_error is not None:
            return (
                stable.snapshot,
                ScanIssue(
                    code="schema_mismatch",
                    message=_ISSUE_MESSAGES["schema_mismatch"],
                    detail=schema_error,
                ),
            )

        return None

    async def _upsert_issue(self, target: ScanTarget, result: tuple[FileSnapshot, ScanIssue] | None) -> None:
        key = self._relative_path(target.path)
        async with self._lock:
            if result is None:
                self._issues.pop(key, None)
                return
            snapshot, issue = result
            self._issues[key] = RecordedIssue(
                target=target,
                snapshot=snapshot,
                issue=issue,
                discovered_at=_now_iso(),
            )

    async def run_startup_scan(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._started = True
            self._issues.clear()

        await asyncio.sleep(STARTUP_SCAN_DELAY_SEC)
        targets = await asyncio.to_thread(self._enumerate_targets)
        for index, target in enumerate(targets):
            result = await self._scan_target(target)
            await self._upsert_issue(target, result)
            if index < len(targets) - 1:
                await asyncio.sleep(SCAN_INTERVAL_SEC)

    async def list_issues(self) -> dict[str, Any]:
        async with self._lock:
            items = sorted(self._issues.values(), key=lambda item: self._relative_path(item.target.path))

        issues = [
            {
                "path": self._relative_path(item.target.path),
                "kind": item.target.kind,
                "code": item.issue.code,
                "message": item.issue.message,
                "detail": item.issue.detail,
                "size": item.snapshot.size,
                "mtimeNs": item.snapshot.mtime_ns,
                "discoveredAt": item.discovered_at,
                "repairAction": _REPAIR_ACTIONS[item.target.kind],
            }
            for item in items
        ]
        return {
            "hasIssues": bool(issues),
            "issues": issues,
        }

    def _snapshot_matches(self, recorded: RecordedIssue, snapshot: FileSnapshot) -> bool:
        return recorded.snapshot == snapshot

    def _reset_target_json(self, target: ScanTarget) -> None:
        if target.kind in {"assistant_chat_global", "assistant_chat_workspace", "assistant_chat_session"}:
            write_json(target.path, AssistantChat().model_dump(mode="json"))
            return
        raise ValueError(f"unsupported reset target: {target.kind}")

    def _delete_target_file(self, target: ScanTarget) -> None:
        target.path.unlink(missing_ok=True)
        lock_path = Path(str(target.path) + ".lock")
        lock_path.unlink(missing_ok=True)

    async def _repair_recorded_issue(self, recorded: RecordedIssue) -> dict[str, Any]:
        stable = await self._read_stable_bytes(recorded.target.path)
        rel_path = self._relative_path(recorded.target.path)
        if stable is None:
            return {"path": rel_path, "status": "skipped", "reason": "文件已变化或不存在"}
        if not self._snapshot_matches(recorded, stable.snapshot):
            return {"path": rel_path, "status": "skipped", "reason": "文件自发现后已变化"}

        current_issue = await self._scan_target(recorded.target)
        if current_issue is None:
            return {"path": rel_path, "status": "skipped", "reason": "文件已恢复正常"}

        action = _REPAIR_ACTIONS[recorded.target.kind]
        if action == "delete":
            await asyncio.to_thread(self._delete_target_file, recorded.target)
        else:
            await asyncio.to_thread(self._reset_target_json, recorded.target)
        return {"path": rel_path, "status": "repaired", "action": action}

    async def repair_issues(self, requested_paths: list[str] | None = None) -> dict[str, Any]:
        normalized_requested = {path.strip() for path in (requested_paths or []) if isinstance(path, str) and path.strip()}
        async with self._lock:
            current = dict(self._issues)

        if normalized_requested:
            selected = [issue for path, issue in current.items() if path in normalized_requested]
        else:
            selected = list(current.values())

        repaired: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for recorded in selected:
            if not self._is_allowed_target(recorded.target.path):
                skipped.append({
                    "path": self._relative_path(recorded.target.path),
                    "status": "skipped",
                    "reason": "路径不在允许修复的白名单中",
                })
                continue

            result = await self._repair_recorded_issue(recorded)
            if result.get("status") == "repaired":
                repaired.append(result)
            else:
                skipped.append(result)

            refreshed_target = self._build_target(recorded.target.path)
            if refreshed_target is not None:
                refreshed_issue = await self._scan_target(refreshed_target)
                await self._upsert_issue(refreshed_target, refreshed_issue)
            else:
                await self._upsert_issue(recorded.target, None)

        remaining = await self.list_issues()
        return {
            "requested": len(selected),
            "repaired": repaired,
            "skipped": skipped,
            "hasIssues": remaining["hasIssues"],
            "remainingIssues": remaining["issues"],
        }


data_integrity_service = DataIntegrityService()