"""Background startup scan and safe repair for chat-related JSON files."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.schemas import AssistantChat
from app.storage import (
    ASSISTANT_CHAT_FILENAME,
    CHAT_MEMORY_FILENAME,
    CHAT_RECORD_FILENAME,
    assistant_chat_path,
    assistant_settings_path,
    assistant_workspace_chat_path,
    characters_dir,
    chats_dir,
    get_repo_root,
    list_json_files,
    read_bytes_under_lock,
    settings_path,
    worldbooks_dir,
    write_json,
)


IntegrityIssueCode = Literal[
    "empty",
    "all_zero",
    "invalid_utf8",
    "invalid_json",
    "schema_mismatch",
    "orphan_reference",
]
IntegrityTargetKind = Literal[
    "chat_record",
    "legacy_chat",
    "chat_memory",
    "assistant_chat_global",
    "assistant_chat_workspace",
    "assistant_chat_session",
    "settings",
    "assistant_settings",
    "character_card",
    "world_book",
]
# "none" 表示仅检测、不自动修复（需人工处理），用于设置/角色/世界书/孤儿引用等高价值数据。
RepairAction = Literal["delete", "reset_json", "none"]

STARTUP_SCAN_DELAY_SEC = 60
SCAN_INTERVAL_SEC = 30
READ_RETRY_DELAY_SEC = 0.15
READ_RETRY_ATTEMPTS = 2

_ISSUE_MESSAGES: dict[IntegrityIssueCode, str] = {
    "empty": "文件为空",
    "all_zero": "文件内容全为 0 字节",
    "invalid_utf8": "文件不是合法 UTF-8 文本",
    "invalid_json": "JSON 解析失败",
    "schema_mismatch": "JSON 结构不符合预期",
    "orphan_reference": "引用的角色不存在（孤儿会话）",
}

_REPAIR_ACTIONS: dict[IntegrityTargetKind, RepairAction] = {
    "chat_record": "delete",
    "legacy_chat": "delete",
    "chat_memory": "delete",
    "assistant_chat_global": "reset_json",
    "assistant_chat_workspace": "reset_json",
    "assistant_chat_session": "reset_json",
    "settings": "none",
    "assistant_settings": "none",
    "character_card": "none",
    "world_book": "none",
}


def _effective_repair_action(kind: IntegrityTargetKind, code: IntegrityIssueCode) -> RepairAction:
    """孤儿引用所在文件本身可能完好，绝不能按 chat_record 的 delete 自动删除，统一降级为人工处理。"""
    if code == "orphan_reference":
        return "none"
    return _REPAIR_ACTIONS[kind]


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
        data = read_bytes_under_lock(path, shared=True)
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
        if resolved == settings_path().resolve():
            return ScanTarget(path=resolved, kind="settings")
        if resolved == assistant_settings_path().resolve():
            return ScanTarget(path=resolved, kind="assistant_settings")
        if resolved.suffix.lower() == ".json":
            if resolved.parent == characters_dir().resolve():
                return ScanTarget(path=resolved, kind="character_card")
            if resolved.parent == worldbooks_dir().resolve():
                return ScanTarget(path=resolved, kind="world_book")

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

        settings_file = settings_path()
        if settings_file.exists():
            targets.append(ScanTarget(path=settings_file.resolve(), kind="settings"))

        assistant_settings_file = assistant_settings_path()
        if assistant_settings_file.exists():
            targets.append(ScanTarget(path=assistant_settings_file.resolve(), kind="assistant_settings"))

        for char_file in list_json_files(characters_dir()):
            targets.append(ScanTarget(path=char_file.resolve(), kind="character_card"))

        for worldbook_file in list_json_files(worldbooks_dir()):
            targets.append(ScanTarget(path=worldbook_file.resolve(), kind="world_book"))

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

    def _validate_object_schema(self, raw: Any, label: str) -> str | None:
        if not isinstance(raw, dict):
            return f"{label}必须是 JSON 对象"
        return None

    def _validate_identified_schema(self, raw: Any, label: str) -> str | None:
        if not isinstance(raw, dict):
            return f"{label}必须是 JSON 对象"
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier:
            return f"{label}缺少非空 id 字段"
        return None

    def _validate_schema(self, target: ScanTarget, raw: Any) -> str | None:
        try:
            if target.kind in {"chat_record", "legacy_chat"}:
                return self._validate_chat_record_schema(raw)
            if target.kind == "chat_memory":
                return self._validate_chat_memory_schema(raw)
            if target.kind in {"settings", "assistant_settings"}:
                return self._validate_object_schema(raw, "设置文件")
            if target.kind == "character_card":
                return self._validate_identified_schema(raw, "角色卡")
            if target.kind == "world_book":
                return self._validate_identified_schema(raw, "世界书")
            AssistantChat.model_validate(raw)
            return None
        except ValidationError as exc:
            return _normalize_detail(str(exc))
        except ValueError as exc:
            return _normalize_detail(str(exc))

    def _collect_character_ids(self) -> set[str]:
        """有效角色 ID = characters 目录下 *.json 的文件名（即便内容损坏也视为“存在”，其损坏会单独上报）。"""
        return {p.stem for p in list_json_files(characters_dir())}

    def _check_orphan_reference(
        self, target: ScanTarget, raw: Any, valid_character_ids: set[str] | None
    ) -> ScanIssue | None:
        if valid_character_ids is None:
            return None
        if target.kind not in {"chat_record", "legacy_chat"}:
            return None
        if not isinstance(raw, dict):
            return None
        character_id = raw.get("characterId")
        if not isinstance(character_id, str) or not character_id:
            return None
        if character_id in valid_character_ids:
            return None
        return ScanIssue(
            code="orphan_reference",
            message=_ISSUE_MESSAGES["orphan_reference"],
            detail=_normalize_detail(f"characterId={character_id} 无对应角色卡"),
        )

    def _validate_chat_record_schema(self, raw: Any) -> str | None:
        """
        巡检只做轻量结构检查，避免后台扫描反复完整校验超长 messages。
        完整 Pydantic 校验仍发生在用户实际加载会话时。
        """
        if not isinstance(raw, dict):
            return "聊天记录必须是对象"
        for key in ("id", "characterId", "messages"):
            if key not in raw:
                return f"聊天记录缺少 {key} 字段"
        if not isinstance(raw.get("id"), str) or not raw.get("id"):
            return "聊天记录 id 必须是非空字符串"
        if not isinstance(raw.get("characterId"), str) or not raw.get("characterId"):
            return "聊天记录 characterId 必须是非空字符串"
        if not isinstance(raw.get("messages"), list):
            return "聊天记录 messages 必须是数组"
        return None

    async def _scan_target(
        self, target: ScanTarget, valid_character_ids: set[str] | None = None
    ) -> tuple[FileSnapshot, ScanIssue] | None:
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

        orphan = self._check_orphan_reference(target, raw, valid_character_ids)
        if orphan is not None:
            return stable.snapshot, orphan

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
        valid_character_ids = await asyncio.to_thread(self._collect_character_ids)
        for index, target in enumerate(targets):
            result = await self._scan_target(target, valid_character_ids)
            await self._upsert_issue(target, result)
            if index < len(targets) - 1:
                await asyncio.sleep(SCAN_INTERVAL_SEC)

    async def _refresh_cached_issues(self) -> None:
        """Re-scan paths currently in the in-memory cache so polling reflects manual fixes."""
        async with self._lock:
            cached = list(self._issues.values())

        if not cached:
            return

        needs_character_ids = any(
            item.target.kind in {"chat_record", "legacy_chat"} for item in cached
        )
        valid_character_ids = (
            await asyncio.to_thread(self._collect_character_ids) if needs_character_ids else None
        )

        for recorded in cached:
            refreshed_target = self._build_target(recorded.target.path) or recorded.target
            if not refreshed_target.path.exists():
                await self._upsert_issue(refreshed_target, None)
                continue
            char_ids = (
                valid_character_ids
                if refreshed_target.kind in {"chat_record", "legacy_chat"}
                else None
            )
            result = await self._scan_target(refreshed_target, char_ids)
            await self._upsert_issue(refreshed_target, result)

    async def list_issues(self) -> dict[str, Any]:
        await self._refresh_cached_issues()
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
                "repairAction": _effective_repair_action(item.target.kind, item.issue.code),
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

        current_issue = await self._scan_target(
            recorded.target,
            await asyncio.to_thread(self._collect_character_ids)
            if recorded.target.kind in {"chat_record", "legacy_chat"}
            else None,
        )
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
            action = _effective_repair_action(recorded.target.kind, recorded.issue.code)
            if action == "none":
                # 设置/角色/世界书/孤儿引用仅检测，保留在列表中等待人工处理，绝不自动删除。
                refreshed_target = self._build_target(recorded.target.path) or recorded.target
                char_ids = (
                    await asyncio.to_thread(self._collect_character_ids)
                    if refreshed_target.kind in {"chat_record", "legacy_chat"}
                    else None
                )
                refreshed_issue = await self._scan_target(refreshed_target, char_ids)
                await self._upsert_issue(refreshed_target, refreshed_issue)
                if refreshed_issue is not None:
                    skipped.append({
                        "path": self._relative_path(recorded.target.path),
                        "status": "skipped",
                        "reason": "需人工检查处理（不自动修复）",
                    })
                continue

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