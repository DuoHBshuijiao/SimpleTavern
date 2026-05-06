"""
导入导出路由模块

提供数据导入导出功能，支持聊天、角色、设置以及 SillyTavern 角色卡的导出和导入。

主要功能：
    - GET /chats/{chat_id}/export: 导出聊天会话（支持txt和json格式）
    - GET /settings/backup: 备份设置（支持basic/with_characters/with_chats三种范围）
    - POST /import: 导入数据（支持zip/json/txt以及ST png/json角色卡）
    - POST /import/janitor/pending: 暂存Janitor捕获的聊天数据（独立字典，与角色 HTML 导入无关）
    - GET /import/janitor/pending/{pending_id}: 获取Janitor待导入预览
    - POST /import/janitor/confirm: 确认导入Janitor聊天到本地会话
    - POST /import/janitor/character-html: 从JAI角色页HTML导入角色卡（multipart 文件或 JSON 体 {"html": "..."}）
    - POST /import/janitor/character-json: 从 JAI window.mbxM 中的角色对象导入（JSON 体 {"charJson": {...}, "avatarUrl"?: "..."}）

主要函数：
    - export_chat: 导出聊天会话
    - backup_settings: 备份设置
    - import_data: 导入数据

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入schemas.py的数据模型和storage.py的存储函数
    - 依赖：依赖schemas.py和storage.py
    - 位置：路由层，处理数据导入导出相关的HTTP请求
"""

from __future__ import annotations

import io
import json
import re
import base64
import zipfile
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse
from typing import Any
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrllibRequest, urlopen

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.chat_transcript import (
    build_jsonl_header_dict,
    build_transcript_rows_from_messages,
    format_chat_as_jsonl_string,
)
from app.placeholders import replace_placeholders_in_text
from app.prompt_xml import (
    wrap_acting_as,
    wrap_after_placeholders,
    wrap_char_name,
    wrap_group_roster,
    wrap_user_name,
)
from app.schemas import Chat, ChatContentRegexRule, ChatMessage, CharacterCard, ExtraFirstMessageEntry, MvuMode, Settings, StatusTableDef, WorldBook
from app.services.st_mvu_compat import (
    run_st_mvu_compat_agent,
    run_st_mvu_regex_compat_agent,
    validate_st_mvu_compat_result,
    validate_st_mvu_regex_compat_result,
)
from app.storage import (
    avatar_path,
    avatars_dir,
    characters_dir,
    chats_dir,
    list_characters,
    load_character,
    load_chat,
    load_settings,
    save_avatar,
    save_character,
    save_chat,
    save_chat_memory,
    save_settings,
    load_worldbook,
    save_worldbook,
    worldbooks_dir,
)

router = APIRouter(tags=["import_export"])
JANITOR_CHAT_PENDING_TTL_SECONDS = 10 * 60
SILLYTAVERN_IMPORT_PENDING_TTL_SECONDS = 10 * 60
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 仅暂存 Janitor「聊天」捕获；角色 HTML 导入走独立接口，不写入此字典。
_janitor_chat_pending_store: dict[str, tuple[datetime, dict[str, Any]]] = {}
_sillytavern_pending_store: dict[str, tuple[datetime, dict[str, Any]]] = {}


class JanitorConfirmRequest(BaseModel):
    pendingId: str
    characterId: str
    userPersonaId: str | None = None


class SillyTavernConfirmRequest(BaseModel):
    pendingId: str
    enableMvuCompatibility: bool = False
    mvuMode: MvuMode = "regex"


def _sanitize_filename(name: str, fallback: str) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        name: 原始文件名
        fallback: 如果清理后为空则使用的后备名称
    
    Returns:
        str: 清理后的文件名
    """
    if not name:
        return fallback
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return safe or fallback


def _cleanup_expired_janitor_chat_pending() -> None:
    now = datetime.now().astimezone()
    expired = [pid for pid, (expire_at, _) in _janitor_chat_pending_store.items() if expire_at <= now]
    for pid in expired:
        _janitor_chat_pending_store.pop(pid, None)


def _cleanup_expired_sillytavern_pending() -> None:
    now = datetime.now().astimezone()
    expired = [pid for pid, (expire_at, _) in _sillytavern_pending_store.items() if expire_at <= now]
    for pid in expired:
        _sillytavern_pending_store.pop(pid, None)


def _validate_janitor_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="janitor payload must be a json object")
    messages = raw.get("chatMessages")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="janitor payload missing chatMessages list")
    if not messages:
        raise HTTPException(status_code=400, detail="janitor chatMessages is empty")
    return raw


def _coalesce_janitor_character_name(raw: dict[str, Any]) -> str:
    character = raw.get("character")
    if not isinstance(character, dict):
        return "Bot"
    for key in ("chat_name", "name", "character_name", "displayName"):
        value = character.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Bot"


def _extract_message_text(raw_msg: dict[str, Any]) -> str:
    message = raw_msg.get("message")
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, list):
        for item in reversed(message):
            if isinstance(item, str) and item.strip():
                return item.strip()
    content = raw_msg.get("content")
    if isinstance(content, str):
        return content.strip()
    text = raw_msg.get("text")
    if isinstance(text, str):
        return text.strip()
    return ""


def _sorted_janitor_messages(raw: dict[str, Any]) -> list[dict[str, Any]]:
    messages = [m for m in raw.get("chatMessages", []) if isinstance(m, dict)]
    return sorted(messages, key=lambda m: str(m.get("created_at") or ""))


def _janitor_preview_from_payload(raw: dict[str, Any]) -> dict[str, Any]:
    sorted_messages = _sorted_janitor_messages(raw)
    sample: list[dict[str, Any]] = []
    for message in sorted_messages[:5]:
        sample.append({
            "role": "assistant" if bool(message.get("is_bot")) else "user",
            "content": _extract_message_text(message),
            "ts": message.get("created_at"),
        })
    return {
        "botName": _coalesce_janitor_character_name(raw),
        "messageCount": len(sorted_messages),
        "sampleMessages": sample,
    }


def _resolve_persona_snapshot(settings: Settings, persona_id: str | None) -> tuple[str | None, str | None]:
    if not persona_id:
        return None, None
    persona = next((p for p in settings.userPersonas if p.id == persona_id), None)
    if not persona:
        return None, None
    return (persona.name or "用户"), (persona.avatar or None)


def _janitor_title(raw: dict[str, Any]) -> str:
    bot_name = _coalesce_janitor_character_name(raw)
    return f"导入 - {bot_name}"


def _janitor_messages_to_chat_messages(raw: dict[str, Any], character_id: str, persona_id: str | None, settings: Settings) -> list[ChatMessage]:
    persona_name, persona_avatar = _resolve_persona_snapshot(settings, persona_id)
    mapped: list[ChatMessage] = []
    for raw_msg in _sorted_janitor_messages(raw):
        content = _extract_message_text(raw_msg)
        role = "assistant" if bool(raw_msg.get("is_bot")) else "user"
        msg = ChatMessage(
            role=role,  # type: ignore[arg-type]
            content=content,
            ts=str(raw_msg.get("created_at") or datetime.now().astimezone().isoformat()),
            characterId=character_id if role == "assistant" else None,
        )
        if role == "user":
            msg.senderPersonaId = persona_id
            msg.senderName = persona_name
            msg.senderAvatar = persona_avatar
        mapped.append(msg)
    return mapped


def _strip_html(html: str) -> str:
    cleaned = re.sub(r"<script[\s\S]*?</script>", "\n", html, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"</(p|div|h1|h2|h3|h4|li|section|article)>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_meta_content(html: str, keys: list[str]) -> str:
    for key in keys:
        patterns = [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.I)
            if match and match.group(1).strip():
                return match.group(1).strip()
    return ""


def _extract_labeled_block(text: str, labels: list[str], stop_labels: list[str]) -> str:
    for label in labels:
        stop = "|".join(re.escape(item) for item in stop_labels if item != label)
        pattern = rf"{re.escape(label)}\s*[:：]?\s*(.+?)(?=\n(?:{stop})\s*[:：]?|\Z)"
        match = re.search(pattern, text, flags=re.I | re.S)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return ""


def _guess_image_ext(url: str, content_type: str | None) -> str:
    suffix = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        if suffix.endswith(ext):
            return ext.lstrip(".")
    if content_type:
        c = content_type.lower()
        if "png" in c:
            return "png"
        if "gif" in c:
            return "gif"
        if "webp" in c:
            return "webp"
    return "jpg"


def _bytes_look_like_image(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data[:4] == b"\x89PNG":
        return True
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return False


# 部分 CDN 对非浏览器 UA/无 Referer 会返回非图片体或错误页，导致「下载失败」
_JANITOR_AVATAR_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://janitorai.com/",
}


def _download_avatar_from_url(image_url: str) -> str:
    req = UrllibRequest(image_url, headers=_JANITOR_AVATAR_FETCH_HEADERS)
    try:
        with urlopen(req, timeout=45) as resp:
            payload = resp.read()
            ct = resp.headers.get("Content-Type")
            ext = _guess_image_ext(image_url, ct)
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from e
    except URLError as e:
        raise RuntimeError(f"网络错误: {e.reason!s}") from e
    if not payload:
        raise RuntimeError("空响应")
    if not _bytes_look_like_image(payload):
        head = payload[:80].decode("utf-8", errors="replace").strip()
        if head.startswith("<") or head.startswith("{"):
            raise RuntimeError("响应不是图片（可能为错误页）")
        raise RuntimeError("响应不是已知图片格式")
    filename = f"{uuid4().hex}.{ext}"
    save_avatar(filename, payload)
    return filename


def _normalize_avatar_url_hint(raw: str | None) -> str:
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s.startswith(("http://", "https://")):
        return ""
    return s


def _is_janitor_ui_avatar_noise(url: str) -> bool:
    u = url.lower()
    if "logopink" in u:
        return True
    if "favicon" in u or "apple-touch-icon" in u or "mask-icon" in u:
        return True
    if "assets.janitorai.com" in u and ("logo" in u or u.endswith(".svg")):
        return True
    return False


def _extract_avatar_image_from_html(html: str) -> str:
    patterns = [
        r'<img[^>]+class=["\'][^"\']*\bavatar-image\b[^"\']*["\'][^>]*src=["\'](https?://[^"\']+)["\']',
        r'<img[^>]+src=["\'](https?://[^"\']+)["\'][^>]+class=["\'][^"\']*\bavatar-image\b[^"\']*["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I)
        if m:
            candidate = m.group(1).strip()
            if candidate and not _is_janitor_ui_avatar_noise(candidate):
                return candidate
    for m in re.finditer(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html, flags=re.I):
        candidate = m.group(1).strip()
        if candidate and not _is_janitor_ui_avatar_noise(candidate):
            return candidate
    return ""


def _resolve_character_avatar_url(html: str, avatar_url_hint: str | None) -> str:
    hint = _normalize_avatar_url_hint(avatar_url_hint)
    if hint:
        return hint
    meta_url = _extract_meta_content(html, ["og:image", "og:image:secure_url", "twitter:image"])
    if meta_url and not _is_janitor_ui_avatar_noise(meta_url):
        return meta_url
    from_img = _extract_avatar_image_from_html(html)
    if from_img:
        return from_img
    if meta_url:
        return meta_url
    return ""


def _janitor_jai_avatar_cdn_url(avatar: str) -> str:
    a = (avatar or "").strip()
    if not a:
        return ""
    if a.startswith(("http://", "https://")):
        return a
    return f"https://ella.janitorai.com/bot-avatars/{a.lstrip('/')}"


_JANITOR_TOKEN_TITLE_SUFFIX = re.compile(r"\s*\(\s*\d+\s*tokens?\s*\)\s*$", re.I)
_JANITOR_MSG_NAV = re.compile(
    r'<div[^>]*\bclass="[^"]*messageNavigation[^"]*"[^>]*>[\s\S]*?</div>',
    re.I,
)
_JANITOR_MSG_COUNTER = re.compile(
    r'class="[^"]*messageCounter[^"]*"[^>]*>\s*(\d+)\s*/\s*(\d+)',
    re.I,
)


def _janitor_char_json_has_greetings(char: dict[str, Any]) -> bool:
    fms = char.get("first_messages")
    if isinstance(fms, list) and any(str(x).strip() for x in fms):
        return True
    fm = char.get("first_message")
    return isinstance(fm, str) and fm.strip() != ""


def _janitor_js_decode_double_quoted_string_body(html: str, start: int) -> tuple[str, int | None]:
    out: list[str] = []
    i = start
    n = len(html)
    while i < n:
        c = html[i]
        if c == '"':
            return ("".join(out), i + 1)
        if c == "\\" and i + 1 < n:
            esc = html[i + 1]
            if esc == "n":
                out.append("\n")
            elif esc == "r":
                out.append("\r")
            elif esc == "t":
                out.append("\t")
            elif esc in '"\\/':
                out.append(esc)
            elif esc == "u" and i + 5 < n:
                try:
                    out.append(chr(int(html[i + 2 : i + 6], 16)))
                except (ValueError, OverflowError):
                    out.append(esc)
                i += 4
            else:
                out.append(esc)
            i += 2
            continue
        out.append(c)
        i += 1
    return ("".join(out), None)


def _extract_janitor_character_from_mbxm_html(html: str) -> dict[str, Any] | None:
    marker = "window.mbxM.push(JSON.parse("
    idx = html.find(marker)
    if idx < 0:
        return None
    j = idx + len(marker)
    while j < len(html) and html[j] in " \t\n\r":
        j += 1
    if j >= len(html) or html[j] != '"':
        return None
    j += 1
    body, end = _janitor_js_decode_double_quoted_string_body(html, j)
    if end is None:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for k, v in payload.items():
        if isinstance(k, str) and k.endswith("characterStore") and isinstance(v, dict):
            ch = v.get("character")
            if isinstance(ch, dict):
                return ch
    return None


def _strip_janitor_token_label_suffix(raw: str) -> str:
    t = (raw or "").strip()
    return _JANITOR_TOKEN_TITLE_SUFFIX.sub("", t).strip()


def _janitor_map_accordion_field(norm: str) -> str | None:
    t = norm.lower()
    if "example" in t and "dialog" in t:
        return "example_dialogs"
    if "personality" in t or t.strip() in ("性格",):
        return "personality"
    if "scenario" in t or "场景" in t:
        return "scenario"
    if (
        ("first" in t and "message" in t)
        or ("initial" in t and "message" in t)
        or "开场" in t
    ):
        return "first_message"
    if "description" in t or "bio" in t or "简介" in t or ("character" in t and "bio" in t):
        return "description"
    if "name" in t and "character" in t:
        return "name"
    return None


def _extract_inner_html_of_div_with_id_panel(html: str, panel_n: int) -> str:
    panel_id = f"panel-info-{panel_n}"
    m2 = re.search(
        r'<div[^>]*\bid=(["\'])' + re.escape(panel_id) + r'\1[^>]*>',
        html,
        flags=re.I,
    )
    if not m2:
        return ""
    open_end = m2.end()
    # depth: inside panel div, count <div> / </div> until this panel closes
    depth = 1
    for tm in re.finditer(r"</?div\b[^>]*>", html[open_end:], flags=re.I):
        tag = tm.group(0)
        if tag.lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return html[open_end : open_end + tm.start()]
        else:
            depth += 1
    return ""


def _janitor_find_accordion_title_for_panel_n(html: str, panel_n: int) -> str:
    pat = re.compile(
        r'id="info-' + str(int(panel_n)) + r'"[^>]*>[\s\S]*?'
        r'<span[^>]*\b[^"]*characterInfoAccordionTitleText[^>]*>([^<]+)</span>',
        re.I,
    )
    m = pat.search(html)
    return m.group(1).strip() if m else ""


def _janitor_list_panel_info_indices(html: str) -> list[int]:
    found = re.findall(r'\bid="panel-info-(\d+)"', html, flags=re.I)
    if not found:
        return []
    return sorted({int(x) for x in found}, key=int)


def _parse_character_from_janitor_accordion(
    html: str, avatar_url_hint: str | None, warnings: list[str]
) -> CharacterCard:
    all_labels = [
        "Character Name",
        "Character Bio",
        "Bio",
        "Personality",
        "Scenario",
        "First Message",
        "First message",
    ]
    name = _extract_meta_content(html, ["og:title"]) or ""
    if not name:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        if title_match:
            name = re.sub(r"\s+", " ", title_match.group(1)).strip()
    if not name:
        text_probe = _strip_html(html)
        name = _extract_labeled_block(text_probe, ["Character Name", "Name", "角色名称"], all_labels)
    if not name:
        name = "新角色"
        warnings.append("未识别到角色名称，已使用默认名称")

    fields: dict[str, str] = {
        "description": "",
        "personality": "",
        "scenario": "",
        "first_message": "",
        "example_dialogs": "",
    }
    for n in _janitor_list_panel_info_indices(html):
        title_raw = _janitor_find_accordion_title_for_panel_n(html, n)
        norm = _strip_janitor_token_label_suffix(title_raw)
        fkey = _janitor_map_accordion_field(norm) if norm else None
        if not fkey or fkey == "name":
            continue
        panel_h = _extract_inner_html_of_div_with_id_panel(html, n)
        if not panel_h and fkey:
            continue
        pnav = _JANITOR_MSG_NAV.sub("\n", panel_h)
        msg_warn = _JANITOR_MSG_COUNTER.search(panel_h)
        if fkey == "first_message" and msg_warn and int(msg_warn.group(2)) > 1:
            warnings.append(
                f"Initial Messages：共 {msg_warn.group(2)} 条，"
                f"当前 DOM 仅第 {msg_warn.group(1)} 条，已只导入该条；"
                f"完整多条请用扩展 mbxM 路径或含 window.mbxM.push 的 HTML。"
            )
        text_content = _strip_html(pnav).strip()
        if fkey in fields:
            if fields[fkey] and text_content and fields[fkey] != text_content:
                warnings.append(
                    f"JAI 手风琴中「{fkey}」出现多块，已使用最后一次块内容。",
                )
            fields[fkey] = text_content

    if not any(fields.values()):
        raise ValueError("accordion_empty")
    return CharacterCard(
        name=name,
        description=fields["description"],
        personality=fields["personality"],
        scenario=fields["scenario"],
        firstMessage=fields["first_message"],
        exampleDialogue=fields["example_dialogs"],
    )


def _parse_character_from_html_flat_legacy(html: str, avatar_url_hint: str | None) -> tuple[CharacterCard, list[str]]:
    warnings: list[str] = []
    text = _strip_html(html)
    all_labels = [
        "Character Name",
        "Character Bio",
        "Bio",
        "Personality",
        "Scenario",
        "First Message",
        "First message",
    ]

    name = _extract_meta_content(html, ["og:title"]) or ""
    if not name:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        if title_match:
            name = re.sub(r"\s+", " ", title_match.group(1)).strip()
    if not name:
        name = _extract_labeled_block(text, ["Character Name", "Name", "角色名称"], all_labels)
    if not name:
        name = "新角色"
        warnings.append("未识别到角色名称，已使用默认名称")

    description = _extract_labeled_block(text, ["Character Bio", "Bio", "简介"], all_labels)
    personality = _extract_labeled_block(text, ["Personality"], all_labels)
    scenario = _extract_labeled_block(text, ["Scenario"], all_labels)
    first_message = _extract_labeled_block(text, ["First Message", "First message", "首句"], all_labels)

    avatar_url = _resolve_character_avatar_url(html, avatar_url_hint)

    card = CharacterCard(
        name=name,
        description=description,
        personality=personality,
        scenario=scenario,
        firstMessage=first_message,
    )

    if avatar_url:
        try:
            card.avatar = _download_avatar_from_url(avatar_url)
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            if len(detail) > 120:
                detail = detail[:117] + "..."
            warnings.append(f"角色图片下载失败，已跳过头像（{detail}）")
    else:
        warnings.append("未识别到角色图片链接")
    return card, warnings


def _parse_character_from_json(char: dict[str, Any], avatar_url_hint: str | None = None) -> tuple[CharacterCard, list[str]]:
    warnings: list[str] = []
    name = (str(char.get("name") or char.get("chat_name") or "")).strip() or "新角色"
    personality = (str(char.get("personality") or "")).strip()
    scenario = (str(char.get("scenario") or "")).strip()
    example_dial = (str(char.get("example_dialogs") or "")).strip()
    description = _strip_html(str(char.get("description") or ""))

    fms = char.get("first_messages")
    all_messages: list[str] = []
    if isinstance(fms, list):
        all_messages = [str(x).strip() for x in fms if str(x).strip()]
    if not all_messages and isinstance(char.get("first_message"), str) and (char.get("first_message") or "").strip():
        all_messages = [str(char.get("first_message") or "").strip()]

    first_msg = all_messages[0] if all_messages else ""
    extras: list[ExtraFirstMessageEntry] = [
        ExtraFirstMessageEntry(text=m, chip=True) for m in all_messages[1:]
    ]

    avatar_url = _normalize_avatar_url_hint(avatar_url_hint)
    if not avatar_url:
        raw_av = (str(char.get("raw_avatar") or char.get("avatar") or "")).strip()
        if raw_av:
            avatar_url = _janitor_jai_avatar_cdn_url(raw_av)

    card = CharacterCard(
        name=name,
        description=description,
        personality=personality,
        scenario=scenario,
        firstMessage=first_msg,
        exampleDialogue=example_dial,
        extraFirstMessageEntries=extras,
    )
    if avatar_url:
        try:
            card.avatar = _download_avatar_from_url(avatar_url)
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            if len(detail) > 120:
                detail = detail[:117] + "..."
            warnings.append(f"角色图片下载失败，已跳过头像（{detail}）")
    else:
        warnings.append("未识别到角色图片链接")
    return card, warnings


def _parse_character_from_html(html: str, avatar_url_hint: str | None = None) -> tuple[CharacterCard, list[str]]:
    ch = _extract_janitor_character_from_mbxm_html(html)
    if ch and _janitor_char_json_has_greetings(ch):
        return _parse_character_from_json(ch, avatar_url_hint=avatar_url_hint)
    if re.search(r'characterInfoAccordionItem_|\bid="info-\d+"', html):
        w_acc: list[str] = []
        try:
            card = _parse_character_from_janitor_accordion(html, avatar_url_hint, w_acc)
            avatar_url = _resolve_character_avatar_url(html, avatar_url_hint)
            if avatar_url:
                try:
                    card.avatar = _download_avatar_from_url(avatar_url)
                except Exception as e:
                    detail = str(e).strip() or type(e).__name__
                    if len(detail) > 120:
                        detail = detail[:117] + "..."
                    w_acc.append(f"角色图片下载失败，已跳过头像（{detail}）")
            else:
                w_acc.append("未识别到角色图片链接")
            return card, w_acc
        except ValueError as e:
            if str(e) == "accordion_empty":
                pass
            else:
                raise
    return _parse_character_from_html_flat_legacy(html, avatar_url_hint)


def _content_disposition(filename: str) -> str:
    """
    生成Content-Disposition头，支持UTF-8编码的文件名
    
    Args:
        filename: 文件名
    
    Returns:
        str: Content-Disposition头字符串
    """
    ascii_fallback = re.sub(r"[^\x20-\x7E]+", "_", filename).strip() or "download"
    encoded = quote(filename)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _strip_character_worldbook_fields(card: CharacterCard) -> dict[str, Any]:
    payload = card.model_dump(mode="json")
    payload.pop("attachedWorldBookIds", None)
    return payload


def _resolve_pure_ai_mode(settings: Settings, chat: Chat) -> bool:
    """
    解析纯AI模式（优先级：chat.overrides > settings）
    
    Args:
        settings: 全局设置
        chat: 聊天对象
    
    Returns:
        bool: 是否启用纯AI模式
    """
    if getattr(chat, "overrides", None) is not None and getattr(chat.overrides, "pureAiMode", None) is not None:
        return bool(chat.overrides.pureAiMode)
    return bool(getattr(settings, "pureAiMode", False))


def _resolve_selected_persona(settings: Settings, chat: Chat) -> Any | None:
    """
    解析选中的用户Persona
    
    Args:
        settings: 全局设置
        chat: 聊天对象
    
    Returns:
        UserPersona | None: 选中的Persona对象
    """
    persona_id = getattr(chat, "userPersonaId", None) or settings.selectedPersonaId
    if not persona_id or not settings.userPersonas:
        return None
    return next((p for p in settings.userPersonas if p.id == persona_id), None)


def _build_user_persona_prompt(settings: Settings, chat: Chat, *, char_name: str) -> str | None:
    """
    构建用户Persona提示词
    
    Args:
        settings: 全局设置
        chat: 聊天对象
        char_name: 用于替换 {{char}} 的角色名
    
    Returns:
        str | None: Persona提示词，不存在返回None
    """
    selected = _resolve_selected_persona(settings, chat)
    if not selected:
        return None
    runtime_user_name = (selected.name or "").strip() or "用户"
    parts: list[str] = []
    if selected.name and selected.name.strip():
        parts.append(
            wrap_user_name(
                raw=selected.name.strip(),
                char_name=char_name,
                user_name=runtime_user_name,
            )
        )
    if selected.description and selected.description.strip():
        parts.append(
            wrap_after_placeholders(
                "UserBio",
                selected.description.strip(),
                char_name=char_name,
                user_name=runtime_user_name,
            )
        )
    return "\n".join(parts) if parts else None


def _resolve_session_system_prompt_mode(chat: Chat) -> str:
    return "override" if getattr(chat.overrides, "sessionSystemPromptMode", None) == "override" else "append"


def _should_include_global_system_prompt(chat: Chat, settings: Settings) -> bool:
    if not settings.prompts.globalSystem or not settings.prompts.globalSystem.strip():
        return False
    if _resolve_session_system_prompt_mode(chat) != "override":
        return True
    return not bool((chat.overrides.prompt or "").strip())


def _build_single_system_prompt(chat: Chat, settings: Settings) -> str:
    """
    构建单聊系统提示词
    
    Args:
        chat: 聊天对象
        settings: 全局设置
    
    Returns:
        str: 系统提示词
    """
    pure = _resolve_pure_ai_mode(settings, chat)
    character = None
    try:
        character = load_character(chat.characterId)
    except FileNotFoundError:
        pass

    ph_char = (character.name or "角色") if character else "角色"
    selected = None if pure else _resolve_selected_persona(settings, chat)
    ph_user = selected.name.strip() if selected and selected.name else "用户"

    prompt_parts: list[str] = []
    if _should_include_global_system_prompt(chat, settings):
        gs = settings.prompts.globalSystem
        if isinstance(gs, str) and gs.strip():
            prompt_parts.append(replace_placeholders_in_text(gs.strip(), char_name=ph_char, user_name=ph_user))

    if not pure:
        persona_prompt = _build_user_persona_prompt(settings, chat, char_name=ph_char)
        if persona_prompt:
            prompt_parts.append(persona_prompt)

    if character:
        character_parts: list[str] = []
        if character.name and character.name.strip():
            character_parts.append(wrap_char_name(raw=character.name.strip()))
        if character.personality and character.personality.strip():
            character_parts.append(
                wrap_after_placeholders("Personality", character.personality.strip(), char_name=ph_char, user_name=ph_user)
            )
        if character.scenario and character.scenario.strip():
            character_parts.append(
                wrap_after_placeholders("Scenario", character.scenario.strip(), char_name=ph_char, user_name=ph_user)
            )
        if character.systemPrompt and character.systemPrompt.strip():
            character_parts.append(
                replace_placeholders_in_text(
                    character.systemPrompt.strip(),
                    char_name=ph_char,
                    user_name=ph_user,
                )
            )
        if character_parts:
            prompt_parts.append("\n\n".join(character_parts))

    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if long_term_memory and long_term_memory.strip():
        prompt_parts.append(
            wrap_after_placeholders("LongTermMemory", long_term_memory.strip(), char_name=ph_char, user_name=ph_user)
        )

    if chat.overrides.prompt and str(chat.overrides.prompt).strip():
        prompt_parts.append(
            replace_placeholders_in_text(str(chat.overrides.prompt).strip(), char_name=ph_char, user_name=ph_user)
        )

    return "\n\n".join([p for p in prompt_parts if p.strip()])


def _pick_group_export_character(chat: Chat) -> str:
    """
    选择群聊导出时的主角色ID（用于构建system prompt）
    
    优先选择最后发言的assistant角色，其次选择最后有characterId的消息，最后选择成员列表最后一个。
    
    Args:
        chat: 聊天对象
    
    Returns:
        str: 角色ID
    """
    for m in reversed(chat.messages):
        if m.role == "assistant" and m.characterId:
            return m.characterId
    for m in reversed(chat.messages):
        if m.characterId:
            return m.characterId
    if chat.memberIds:
        return chat.memberIds[-1]
    return chat.characterId


def _build_group_system_prompt(chat: Chat, settings: Settings, character_id: str) -> str:
    """
    构建群聊系统提示词
    
    Args:
        chat: 聊天对象
        settings: 全局设置
        character_id: 主角色ID
    
    Returns:
        str: 系统提示词
    """
    pure = _resolve_pure_ai_mode(settings, chat)
    character = None
    try:
        character = load_character(character_id)
    except FileNotFoundError:
        pass

    ph_char = (character.name or "角色") if character else "角色"
    selected = None if pure else _resolve_selected_persona(settings, chat)
    ph_user = selected.name.strip() if selected and selected.name else "用户"

    prompt_parts: list[str] = []
    if _should_include_global_system_prompt(chat, settings):
        gs = settings.prompts.globalSystem
        if isinstance(gs, str) and gs.strip():
            prompt_parts.append(replace_placeholders_in_text(gs.strip(), char_name=ph_char, user_name=ph_user))

    if not pure:
        persona_prompt = _build_user_persona_prompt(settings, chat, char_name=ph_char)
        if persona_prompt:
            prompt_parts.append(persona_prompt)

    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue

    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append(
        wrap_group_roster(
            lines=group_context_parts,
            char_name=ph_char,
            user_name=ph_user,
        )
    )

    member_settings = chat.memberSettings.get(character_id)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    if character:
        character_parts: list[str] = []
        if character.name and str(character.name).strip():
            character_parts.append(
                wrap_acting_as(
                    raw=str(character.name).strip(),
                    char_name=ph_char,
                    user_name=ph_user,
                )
            )
        if include_personality and character.personality and character.personality.strip():
            character_parts.append(
                wrap_after_placeholders(
                    "Personality",
                    character.personality.strip(),
                    char_name=ph_char,
                    user_name=ph_user,
                )
            )
        if include_scenario and character.scenario and character.scenario.strip():
            character_parts.append(
                wrap_after_placeholders(
                    "Scenario",
                    character.scenario.strip(),
                    char_name=ph_char,
                    user_name=ph_user,
                )
            )
        if character.systemPrompt and character.systemPrompt.strip():
            character_parts.append(
                replace_placeholders_in_text(
                    character.systemPrompt.strip(),
                    char_name=ph_char,
                    user_name=ph_user,
                )
            )
        if character_parts:
            prompt_parts.append("\n\n".join(character_parts))

    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if long_term_memory and long_term_memory.strip():
        prompt_parts.append(
            wrap_after_placeholders("LongTermMemory", long_term_memory.strip(), char_name=ph_char, user_name=ph_user)
        )

    if chat.overrides.prompt and str(chat.overrides.prompt).strip():
        prompt_parts.append(
            replace_placeholders_in_text(str(chat.overrides.prompt).strip(), char_name=ph_char, user_name=ph_user)
        )

    return "\n\n".join([p for p in prompt_parts if p.strip()])


def _build_system_prompt_for_chat(chat: Chat, settings: Settings) -> tuple[str, str | None]:
    """
    为聊天构建系统提示词
    
    Args:
        chat: 聊天对象
        settings: 全局设置
    
    Returns:
        tuple[str, str | None]: (系统提示词, 群聊时的主角色ID)
    """
    if not chat.isGroup:
        return _build_single_system_prompt(chat, settings), None
    last_speaker_id = _pick_group_export_character(chat)
    return _build_group_system_prompt(chat, settings, last_speaker_id), last_speaker_id


def _chat_export_participants(chat: Chat) -> str:
    """
    获取聊天参与者名称（用于导出文件名）
    
    Args:
        chat: 聊天对象
    
    Returns:
        str: 参与者名称字符串
    """
    if not chat.isGroup:
        try:
            character = load_character(chat.characterId)
            return character.name or "角色"
        except FileNotFoundError:
            return "角色"
    names: list[str] = []
    for member_id in chat.memberIds:
        try:
            member = load_character(member_id)
            if member.name:
                names.append(member.name)
        except FileNotFoundError:
            continue
    return "、".join(names) or "群聊"


def _build_chat_from_transcript_rows(
    *,
    chat_id: str | None,
    title: str,
    is_group: bool,
    participants: list[str],
    rows: list[tuple[str, str, str]],
    settings: Settings,
) -> tuple[Chat, list[str]]:
    """
    由「会话头参与者名 + (role, name, content) 行」构建 Chat，与 JSONL 导入同源。
    """
    name_to_char_id: dict[str, str] = {}
    for card in list_characters():
        if card.name and card.id:
            name_to_char_id[card.name] = card.id

    primary_char_id: str | None = None
    member_ids: list[str] = []
    if participants:
        for pname in participants:
            cid = name_to_char_id.get(pname)
            if cid:
                member_ids.append(cid)
        if member_ids:
            primary_char_id = member_ids[0]

    if not primary_char_id:
        raise HTTPException(
            status_code=400,
            detail=f"none of the participants {participants!r} matched a local character card",
        )

    name_to_persona: dict[str, Any] = {}
    for p in settings.userPersonas or []:
        if p.name:
            name_to_persona[p.name] = p

    warnings: list[str] = []
    messages: list[ChatMessage] = []
    for i, (role, name, content) in enumerate(rows, start=1):
        if role not in ("user", "assistant", "system"):
            warnings.append(f"row {i}: skipped (unknown role {role!r})")
            continue
        msg_kwargs: dict[str, Any] = {"role": role, "content": content}
        if role == "assistant":
            cid = name_to_char_id.get(name) if name else None
            msg_kwargs["characterId"] = cid or (primary_char_id if not is_group else None)
            msg_kwargs["senderName"] = name or None
        elif role == "user":
            persona = name_to_persona.get(name) if name else None
            if persona:
                msg_kwargs["senderPersonaId"] = persona.id
                msg_kwargs["senderName"] = persona.name or name or None
            else:
                msg_kwargs["senderName"] = name or None
        try:
            messages.append(ChatMessage.model_validate(msg_kwargs))
        except Exception as exc:
            warnings.append(f"row {i}: skipped ({exc})")
            continue

    resolved_id = chat_id or uuid4().hex
    chat = Chat(
        id=resolved_id,
        characterId=primary_char_id,
        title=title or "导入会话",
        isGroup=is_group,
        memberIds=member_ids if is_group else [],
        messages=messages,
    )
    return chat, warnings


def _export_chat_text(chat: Chat, system_prompt: str, settings: Settings) -> str:
    """
    导出聊天为文本格式（Version 2）：头部 Participants 为角色显示名（与 JSONL 同源），
    每条消息仅 role / name / content；跳过 tool 与 toolTrace，正文内联图已替换为 [image]。
    """
    hdr = build_jsonl_header_dict(chat)
    participants = hdr.get("participants") or []
    lines: list[str] = [
        "SimpleTavern Chat Export",
        "Version: 2",
        f"ChatId: {hdr['chatId']}",
        f"Title: {hdr['title']}",
        f"IsGroup: {'true' if hdr['isGroup'] else 'false'}",
        f"Participants: {','.join(participants)}",
        "SystemPrompt:",
        "<<<",
    ]
    lines.extend(system_prompt.splitlines() or [""])
    lines.extend([">>>", ""])
    for row in build_transcript_rows_from_messages(chat.messages, settings):
        lines.append("[Message]")
        lines.append(f"role={row['role']}")
        if row.get("name"):
            lines.append(f"name={row['name']}")
        lines.append("content:")
        lines.append("<<<")
        lines.extend((row["content"] or "").splitlines() or [""])
        lines.append(">>>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _export_chat_jsonl(chat: Chat, settings: Settings) -> str:
    """
    将聊天会话序列化为精简 JSONL 格式。

    第 1 行：会话头（type/version/chatId/title/isGroup/participants/ts）
    第 2 行起：每条消息仅含 role/name/content，跳过 tool 消息，清除内联 base64 图片。
    与 app.chat_transcript 同源。
    """
    return format_chat_as_jsonl_string(chat, settings)


def _import_from_jsonl(text: str) -> dict[str, Any]:
    """
    从精简 JSONL 格式导入聊天会话。

    第 1 行须含 type="simpletavern_chat_jsonl"；后续每行含 role/name/content。
    按 name 反查本地角色卡 / persona 映射以还原 characterId / senderPersonaId。
    """
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    if not raw_lines:
        raise HTTPException(status_code=400, detail="empty jsonl file")

    try:
        header = json.loads(raw_lines[0])
    except Exception:
        raise HTTPException(status_code=400, detail="jsonl: first line is not valid json")

    if not isinstance(header, dict) or header.get("type") != "simpletavern_chat_jsonl":
        raise HTTPException(status_code=400, detail="jsonl: unrecognized type in first line")

    participants: list[str] = header.get("participants") or []
    is_group: bool = bool(header.get("isGroup", False))
    settings = load_settings()
    rows: list[tuple[str, str, str]] = []
    warnings: list[str] = []
    for i, ln in enumerate(raw_lines[1:], start=2):
        try:
            obj = json.loads(ln)
        except Exception:
            warnings.append(f"line {i}: skipped (invalid json)")
            continue
        if not isinstance(obj, dict):
            warnings.append(f"line {i}: skipped (not an object)")
            continue
        role = str(obj.get("role", ""))
        name: str = obj.get("name") or ""
        content: str = obj.get("content") or ""
        rows.append((role, name, content))

    chat, map_warnings = _build_chat_from_transcript_rows(
        chat_id=header.get("chatId"),
        title=str(header.get("title") or "导入会话"),
        is_group=is_group,
        participants=participants,
        rows=rows,
        settings=settings,
    )
    warnings.extend(map_warnings)
    save_chat(chat)
    return {"imported": ["chat"], "warnings": warnings}


@router.get("/chats/{chat_id}/export")
def export_chat(chat_id: str, format: str = Query("txt")) -> Response:
    """
    导出聊天会话
    
    支持 txt、json、jsonl 三种格式。
    - txt: 系统提示词 + 精简消息（Version 2：头部 Participants 为角色名，消息仅 role/name/content，与 JSONL 名映射一致）
    - json: 完整聊天对象（indent=2）
    - jsonl: 精简 NDJSON，每条消息一行，仅含 role/name/content，体积最小
    
    Args:
        chat_id: 聊天会话ID
        format: 导出格式（txt/json/jsonl），默认为txt
    
    Returns:
        Response: 文件下载响应
    
    Raises:
        HTTPException: 聊天不存在或格式不支持时抛出错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    settings = load_settings()
    participants = _chat_export_participants(chat)
    export_date = datetime.now().astimezone()
    date_str = f"{export_date.year}/{export_date.month}/{export_date.day}"
    base_name = _sanitize_filename(f"{participants} - {date_str}", "chat")

    if format.lower() == "jsonl":
        content = _export_chat_jsonl(chat, settings)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.jsonl")},
        )

    system_prompt, last_speaker_id = _build_system_prompt_for_chat(chat, settings)

    if format.lower() == "json":
        export_obj = {
            "type": "chat_export",
            "version": 1,
            "systemPrompt": system_prompt,
            "lastSpeakerCharacterId": last_speaker_id,
            "chat": chat.model_dump(mode="json"),
        }
        content = json.dumps(export_obj, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.json")},
        )

    if format.lower() != "txt":
        raise HTTPException(status_code=400, detail="unsupported format")

    content = _export_chat_text(chat, system_prompt, settings)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(f"{base_name}.txt")},
    )


@router.get("/characters/{character_id}/export")
def export_character(
    character_id: str,
    include_world_books: bool = Query(False),
) -> Response:
    try:
        card = load_character(character_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")

    safe_name = _sanitize_filename(card.name or "character", "character")
    if not include_world_books:
        content = json.dumps(_strip_character_worldbook_fields(card), ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": _content_disposition(f"{safe_name}.json")},
        )

    buffer = io.BytesIO()
    attached_ids = list(dict.fromkeys(getattr(card, "attachedWorldBookIds", []) or []))
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"characters/{card.id}.json", json.dumps(card.model_dump(mode="json"), ensure_ascii=False, indent=2))
        for worldbook_id in attached_ids:
            try:
                book = load_worldbook(worldbook_id)
            except FileNotFoundError:
                continue
            # 角色便携包只包含会话激活世界书，不包含仅全局激活书
            if bool(getattr(book, "globalActive", False)):
                continue
            zf.writestr(f"worldbooks/{book.id}.json", json.dumps(book.model_dump(mode="json"), ensure_ascii=False, indent=2))
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "type": "character_export_with_worldbooks",
                    "version": 1,
                    "characterId": card.id,
                    "exportedAt": datetime.now().astimezone().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    buffer.seek(0)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(f"{safe_name}.zip")},
    )


@router.get("/settings/backup")
def backup_settings(scope: str = Query("basic")) -> Response:
    """
    备份设置
    
    将设置、角色、聊天等数据打包为zip文件。支持三种范围：
    - basic: 仅设置和Persona头像
    - with_characters: 包含角色和角色头像
    - with_chats: 包含所有聊天记录
    
    Args:
        scope: 备份范围（basic/with_characters/with_chats），默认为basic
    
    Returns:
        Response: zip文件下载响应
    
    Raises:
        HTTPException: 范围不支持时抛出400错误
    """
    settings = load_settings()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("settings.json", json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2))
        for persona in settings.userPersonas:
            if not persona.avatar:
                continue
            p = avatar_path(persona.avatar)
            if p.exists():
                zf.write(p, arcname=f"avatars/{p.name}")
        if scope not in ("basic", "with_characters", "with_chats"):
            raise HTTPException(status_code=400, detail="unsupported scope")
        if scope in ("with_characters", "with_chats"):
            for p in characters_dir().glob("*.json"):
                zf.write(p, arcname=f"characters/{p.name}")
            for p in characters_dir().glob("*.json"):
                try:
                    card = CharacterCard.model_validate(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
                if card.avatar:
                    avatar_file = avatar_path(card.avatar)
                    if avatar_file.exists():
                        zf.write(avatar_file, arcname=f"avatars/{avatar_file.name}")
            for p in worldbooks_dir().glob("*.json"):
                zf.write(p, arcname=f"worldbooks/{p.name}")
        if scope == "with_chats":
            for p in chats_dir().rglob("*.json"):
                rel = p.relative_to(chats_dir())
                zf.write(p, arcname=f"chats/{rel.as_posix()}")
    buffer.seek(0)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition("settings-backup.zip")},
    )


def _parse_character_text(content: str) -> CharacterCard:
    """
    解析文本格式的角色卡片
    
    支持中文格式的角色卡片文本，使用【标签】格式。
    
    Args:
        content: 角色卡片文本内容
    
    Returns:
        CharacterCard: 解析后的角色卡片对象
    """
    def pick_section(label: str) -> str:
        pattern = rf"【{re.escape(label)}】\n(.*?)(?:\n【|$)"
        match = re.search(pattern, content, re.S)
        if not match:
            return ""
        return match.group(1).strip()

    name_match = re.search(r"角色名称:\s*(.+)", content)
    name = name_match.group(1).strip() if name_match else "新角色"
    now = None
    try:
        created_match = re.search(r"创建时间:\s*(.+)", content)
        if created_match:
            now = created_match.group(1).strip()
    except Exception:
        now = None

    card = CharacterCard(
        name=name,
        description=pick_section("简介"),
        personality=pick_section("Personality（性格/外貌）"),
        scenario=pick_section("Scenario（情景/世界观）"),
        systemPrompt=pick_section("系统提示词"),
        firstMessage=pick_section("首句"),
        exampleDialogue=pick_section("示例对话"),
    )
    if now:
        card.createdAt = now
    return card


def _parse_chat_text(content: str) -> Chat:
    """
    解析 SimpleTavern Chat Export 文本。

    - Version 2：头部含 Participants（角色显示名），消息为 role/name/content；按名匹配本地角色卡与 persona（与 JSONL 同源）。
    - Version 1 或未标 Version：保留 CharacterId、MemberIds 等，消息为旧版 k=v 字段。
    """
    lines = content.splitlines()
    idx = 0
    header: dict[str, Any] = {}
    messages: list[ChatMessage] = []
    transcript_rows: list[tuple[str, str, str]] = []
    system_prompt = ""

    def read_block(start_index: int) -> tuple[str, int]:
        if start_index >= len(lines) or lines[start_index].strip() != "<<<":
            return "", start_index
        buf: list[str] = []
        i = start_index + 1
        while i < len(lines):
            if lines[i].strip() == ">>>":
                return "\n".join(buf).strip(), i + 1
            buf.append(lines[i])
            i += 1
        return "\n".join(buf).strip(), i

    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith("SystemPrompt:"):
            system_prompt, idx = read_block(idx + 1)
            header["systemPrompt"] = system_prompt
            continue
        if line == "[Message]":
            msg_data: dict[str, str] = {}
            idx += 1
            while idx < len(lines):
                msg_line = lines[idx].strip()
                if msg_line == "content:":
                    content_block, idx = read_block(idx + 1)
                    msg_data["content"] = content_block
                    break
                if "=" in msg_line:
                    k, v = msg_line.split("=", 1)
                    msg_data[k.strip()] = v.strip()
                idx += 1
            if header.get("Version") == "2":
                transcript_rows.append(
                    (
                        msg_data.get("role", ""),
                        msg_data.get("name", ""),
                        msg_data.get("content", ""),
                    )
                )
            else:
                messages.append(ChatMessage.model_validate(msg_data))
            idx += 1
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            header[k.strip()] = v.strip()
        idx += 1

    if header.get("Version") == "2":
        participants_str = header.get("Participants") or ""
        participants = [p.strip() for p in participants_str.split(",") if p.strip()]
        settings = load_settings()
        chat, _warnings = _build_chat_from_transcript_rows(
            chat_id=header.get("ChatId"),
            title=header.get("Title") or "新对话",
            is_group=header.get("IsGroup", "false").lower() == "true",
            participants=participants,
            rows=transcript_rows,
            settings=settings,
        )
        return chat

    if not header.get("CharacterId"):
        raise HTTPException(status_code=400, detail="missing CharacterId in text import")

    gsd_h = header.get("GroupSystemInjectDepth")
    gsb_h = header.get("GroupSystemAlwaysAtBottom")
    chat_data: dict[str, Any] = {
        "title": header.get("Title") or "新对话",
        "characterId": header.get("CharacterId"),
        "isGroup": header.get("IsGroup", "false").lower() == "true",
        "memberIds": [m for m in (header.get("MemberIds") or "").split(",") if m],
        "groupDelay": int(header.get("GroupDelay") or 1500),
        "messages": [m.model_dump(mode="json") for m in messages],
    }
    if gsd_h is not None and str(gsd_h).strip() != "":
        chat_data["groupSystemInjectDepth"] = max(0, int(gsd_h))
    if gsb_h is not None and str(gsb_h).strip() != "":
        chat_data["groupSystemAlwaysAtBottom"] = str(gsb_h).lower() == "true"
    if header.get("ChatId"):
        chat_data["id"] = header.get("ChatId")
    return Chat.model_validate(chat_data)


def _extract_png_text_map(payload: bytes) -> dict[str, list[str]]:
    """
    解析 PNG tEXt chunks，返回 key -> 文本值列表。
    """
    if len(payload) < 8 or payload[:8] != PNG_SIGNATURE:
        raise ValueError("not a png")
    cursor = 8
    text_map: dict[str, list[str]] = {}
    while cursor + 8 <= len(payload):
        chunk_len = int.from_bytes(payload[cursor:cursor + 4], "big")
        chunk_type = payload[cursor + 4:cursor + 8]
        data_start = cursor + 8
        data_end = data_start + chunk_len
        crc_end = data_end + 4
        if data_end > len(payload) or crc_end > len(payload):
            break
        if chunk_type == b"tEXt":
            raw = payload[data_start:data_end]
            null_idx = raw.find(b"\x00")
            if null_idx > 0:
                key = raw[:null_idx].decode("latin-1", errors="ignore").strip()
                val = raw[null_idx + 1:].decode("latin-1", errors="ignore")
                if key:
                    text_map.setdefault(key, []).append(val)
        if chunk_type == b"IEND":
            break
        cursor = crc_end
    return text_map


def _decode_st_blob_to_json(raw_text: str) -> dict[str, Any]:
    """
    解码 ST PNG 文本块中的 JSON：支持直接 JSON 或 Base64(JSON)。
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty st payload")
    if text.startswith("{"):
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("st payload is not object")
        return parsed
    compact = "".join(text.split())
    padded = compact + ("=" * (-len(compact) % 4))
    decoded = base64.b64decode(padded.encode("ascii"), validate=False)
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("st payload is not object")
    return parsed


def _extract_st_json_from_png(payload: bytes) -> dict[str, Any]:
    """
    从 PNG 中提取 SillyTavern 卡片 JSON（ccv3 优先，其次 chara）。
    """
    text_map = _extract_png_text_map(payload)
    values_ccv3 = text_map.get("ccv3", [])
    values_chara = text_map.get("chara", [])
    for candidate in values_ccv3 + values_chara:
        try:
            return _decode_st_blob_to_json(candidate)
        except Exception:
            continue
    raise ValueError("png does not contain valid ccv3/chara data")


def _coalesce_st_text(*values: Any) -> str:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _looks_like_st_card(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    data = raw.get("data")
    if isinstance(data, dict) and (
        isinstance(raw.get("spec"), str)
        or "first_mes" in data
        or "mes_example" in data
        or "alternate_greetings" in data
        or "character_book" in data
    ):
        return True
    st_like_keys = {"first_mes", "mes_example", "alternate_greetings", "character_book", "spec", "spec_version"}
    return any(k in raw for k in st_like_keys)


def _build_extra_first_entries(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    source = raw_data.get("alternate_greetings")
    if not isinstance(source, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in source:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if not text:
            continue
        entries.append({"text": text, "chip": True})
    return entries


def _st_entry_regex(raw_entry: dict[str, Any]) -> str:
    if bool(raw_entry.get("constant")):
        return ".*"
    keys_raw = raw_entry.get("keys")
    keys: list[str] = []
    if isinstance(keys_raw, list):
        for item in keys_raw:
            s = str(item or "").strip()
            if s:
                keys.append(s)
    if not keys:
        return ""
    if bool(raw_entry.get("use_regex")):
        return "|".join(keys)
    return "|".join(re.escape(k) for k in keys)


def _build_worldbook_from_st(card_name: str, raw_data: dict[str, Any]) -> WorldBook | None:
    character_book = raw_data.get("character_book")
    if not isinstance(character_book, dict):
        return None
    entries_raw = character_book.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        return None
    entries: list[dict[str, Any]] = []
    for idx, raw in enumerate(entries_raw):
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "").strip()
        title = str(raw.get("comment") or "").strip()
        enabled = bool(raw.get("enabled", True))
        try:
            order_index = int(raw.get("insertion_order", idx))
        except Exception:
            order_index = idx
        entries.append({
            "title": title or f"条目 {idx + 1}",
            "content": content,
            "enabled": enabled,
            "orderIndex": order_index,
            "regex": _st_entry_regex(raw),
        })
    if not entries:
        return None
    wb_name = _coalesce_st_text(character_book.get("name"), f"{card_name or '角色'} 世界书")
    return WorldBook(name=wb_name, entries=entries)


def _merged_st_card_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    merged = dict(raw)
    if isinstance(data, dict):
        merged.update(data)
    return merged


_MVU_CANDIDATE_KEYWORDS = (
    "mvu",
    "tavern_helper",
    "regex_scripts",
    "状态",
    "变量",
    "状态栏",
    "status",
    "variable",
)


def _st_extensions_value(merged: dict[str, Any], key: str) -> Any:
    extensions = merged.get("extensions")
    if isinstance(extensions, dict) and key in extensions:
        return extensions.get(key)
    return merged.get(key)


def _count_regex_scripts(raw_scripts: Any) -> int:
    if isinstance(raw_scripts, list):
        return len([item for item in raw_scripts if item is not None])
    if isinstance(raw_scripts, dict):
        return len(raw_scripts)
    return 1 if raw_scripts else 0


def _character_book_mvu_candidates(character_book: Any) -> list[dict[str, Any]]:
    if not isinstance(character_book, dict):
        return []
    entries = character_book.get("entries")
    if not isinstance(entries, list):
        return []
    candidates: list[dict[str, Any]] = []
    for idx, raw in enumerate(entries):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("comment") or raw.get("name") or f"条目 {idx + 1}").strip()
        keys = raw.get("keys") if isinstance(raw.get("keys"), list) else []
        probe = "\n".join(
            [
                title,
                str(raw.get("content") or ""),
                " ".join(str(k or "") for k in keys),
            ],
        ).lower()
        if not any(keyword.lower() in probe for keyword in _MVU_CANDIDATE_KEYWORDS):
            continue
        candidates.append(
            {
                "title": title or f"条目 {idx + 1}",
                "enabled": bool(raw.get("enabled", True)),
                "keys": [str(k) for k in keys if str(k).strip()][:8],
            },
        )
    return candidates


def _build_sillytavern_preview(raw: dict[str, Any]) -> dict[str, Any]:
    merged = _merged_st_card_data(raw)
    character_name = _coalesce_st_text(merged.get("name"), "新角色")
    character_book = merged.get("character_book")
    entries = character_book.get("entries") if isinstance(character_book, dict) else []
    entry_count = len(entries) if isinstance(entries, list) else 0
    tavern_helper = _st_extensions_value(merged, "tavern_helper")
    regex_scripts = _st_extensions_value(merged, "regex_scripts")
    regex_script_count = _count_regex_scripts(regex_scripts)
    candidates = _character_book_mvu_candidates(character_book)
    return {
        "characterName": character_name,
        "worldBookName": _coalesce_st_text(
            character_book.get("name") if isinstance(character_book, dict) else None,
            f"{character_name} 世界书" if entry_count else "",
        ),
        "worldBookEntryCount": entry_count,
        "mvu": {
            "hasTavernHelper": bool(tavern_helper),
            "hasRegexScripts": regex_script_count > 0,
            "regexScriptCount": regex_script_count,
            "characterBookCandidateCount": len(candidates),
            "characterBookCandidates": candidates[:8],
            "suggestedMode": "regex" if regex_script_count > 0 else "directive",
        },
    }


def _map_st_to_character_and_worldbook(raw: dict[str, Any]) -> tuple[CharacterCard, WorldBook | None]:
    merged = _merged_st_card_data(raw)
    description = _coalesce_st_text(merged.get("description"))
    personality = _coalesce_st_text(merged.get("personality"))
    scenario = _coalesce_st_text(merged.get("scenario"))
    if not personality and not scenario and description:
        personality = description
    card = CharacterCard(
        name=_coalesce_st_text(merged.get("name"), "新角色"),
        description=description,
        personality=personality,
        scenario=scenario,
        firstMessage=_coalesce_st_text(merged.get("first_mes"), merged.get("firstMessage")),
        exampleDialogue=_coalesce_st_text(merged.get("mes_example"), merged.get("exampleDialogue")),
        systemPrompt=_coalesce_st_text(merged.get("system_prompt"), merged.get("systemPrompt")),
        extraFirstMessageEntries=_build_extra_first_entries(merged),
    )
    worldbook = _build_worldbook_from_st(card.name, merged)
    return card, worldbook


def _import_sillytavern_card(
    raw: dict[str, Any],
    avatar_filename: str | None = None,
    *,
    enable_mvu_compatibility: bool = False,
    mvu_mode: MvuMode = "regex",
) -> dict[str, Any]:
    card, worldbook = _map_st_to_character_and_worldbook(raw)
    if isinstance(avatar_filename, str) and avatar_filename.strip():
        card.avatar = avatar_filename.strip()
    if enable_mvu_compatibility:
        card.mvuEnabled = True
        card.mvuMode = mvu_mode
    imported = ["character"]
    warnings: list[str] = []
    saved_worldbook: WorldBook | None = None
    if worldbook is not None:
        saved_worldbook = save_worldbook(worldbook)
        card.attachedWorldBookIds = [saved_worldbook.id]
        imported.append("worldbook")
    saved_card = save_character(card)
    mvu_compat: dict[str, Any] = {
        "mode": mvu_mode,
        "applied": False,
        "summary": "",
        "warnings": [],
        "worldbookMarks": [],
    }
    if enable_mvu_compatibility and mvu_mode == "directive":
        try:
            compat_result = validate_st_mvu_compat_result(run_st_mvu_compat_agent(raw))
            saved_card.mvuEnabled = True
            saved_card.mvuMode = "directive"
            saved_card.mvuDirective = compat_result["directive"] or None
            saved_card.initialStateTables = [
                StatusTableDef.model_validate(item)
                for item in compat_result.get("initialStateTables", [])
            ]
            saved_card = save_character(saved_card)
            mvu_compat = {
                "mode": "directive",
                "applied": bool(compat_result.get("applied")),
                "summary": compat_result.get("summary") or "",
                "warnings": list(compat_result.get("warnings") or []),
                "worldbookMarks": list(compat_result.get("worldbookMarks") or []),
                "confidence": compat_result.get("confidence", 0.0),
            }
            warnings.extend(mvu_compat["warnings"])
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            if len(detail) > 160:
                detail = detail[:157] + "..."
            warning = f"MVU directive 兼容生成失败，已保留普通角色导入（{detail}）"
            warnings.append(warning)
            mvu_compat = {
                "mode": "directive",
                "applied": False,
                "summary": "MVU directive 兼容生成失败，普通导入已保留。",
                "warnings": [warning],
                "worldbookMarks": [],
            }
    elif enable_mvu_compatibility and mvu_mode == "regex":
        try:
            compat_result = validate_st_mvu_regex_compat_result(run_st_mvu_regex_compat_agent(raw))
            saved_card.mvuEnabled = True
            saved_card.mvuMode = "regex"
            saved_card.mvuDirective = None
            existing_rules = list(getattr(saved_card, "contentRegexRules", []) or [])
            generated_rules = [
                ChatContentRegexRule.model_validate(item)
                for item in compat_result.get("regexRules", [])
            ]
            saved_card.contentRegexRules = (existing_rules + generated_rules)[:100]
            saved_card = save_character(saved_card)
            mvu_compat = {
                "mode": "regex",
                "applied": bool(compat_result.get("applied")),
                "summary": compat_result.get("summary") or "",
                "warnings": list(compat_result.get("warnings") or []),
                "worldbookMarks": list(compat_result.get("worldbookMarks") or []),
                "confidence": compat_result.get("confidence", 0.0),
                "rules": len(generated_rules),
            }
            warnings.extend(mvu_compat["warnings"])
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            if len(detail) > 160:
                detail = detail[:157] + "..."
            warning = f"MVU regex 兼容生成失败，已保留普通角色导入（{detail}）"
            warnings.append(warning)
            mvu_compat = {
                "mode": "regex",
                "applied": False,
                "summary": "MVU regex 兼容生成失败，普通导入已保留。",
                "warnings": [warning],
                "worldbookMarks": [],
                "rules": 0,
            }
    out: dict[str, Any] = {
        "imported": imported,
        "warnings": warnings,
        "character": saved_card.model_dump(mode="json"),
    }
    if saved_worldbook is not None:
        out["worldbook"] = saved_worldbook.model_dump(mode="json")
    out["mvu"] = {
        "enabled": bool(enable_mvu_compatibility),
        "requestedMode": mvu_mode,
        "detected": _build_sillytavern_preview(raw)["mvu"],
    }
    out["mvuCompat"] = mvu_compat
    return out


def _import_from_json(raw: Any) -> dict[str, Any]:
    """
    从JSON数据导入
    
    自动识别并导入设置、聊天或角色。
    
    Args:
        raw: JSON数据（dict或已解析的对象）
    
    Returns:
        dict[str, Any]: 导入结果 {"imported": [...], "warnings": [...]}
    
    Raises:
        HTTPException: JSON格式无法识别时抛出400错误
    """
    imported: list[str] = []
    warnings: list[str] = []

    if isinstance(raw, dict) and raw.get("type") == "chat_export":
        raw = raw.get("chat")

    if _looks_like_st_card(raw):
        return _import_sillytavern_card(raw)

    if isinstance(raw, dict) and ("name" in raw and ("personality" in raw or "systemPrompt" in raw)):
        card = CharacterCard.model_validate(raw)
        save_character(card)
        imported.append("character")
        return {"imported": imported, "warnings": warnings}

    if isinstance(raw, dict) and ("llm" in raw or "prompts" in raw or "apiPresets" in raw):
        settings = Settings.model_validate(raw)
        save_settings(settings)
        imported.append("settings")
        return {"imported": imported, "warnings": warnings}

    if isinstance(raw, dict) and ("messages" in raw and "characterId" in raw):
        raw.pop("systemPrompt", None)
        raw.pop("lastSpeakerCharacterId", None)
        chat = Chat.model_validate(raw)
        save_chat(chat)
        imported.append("chat")
        return {"imported": imported, "warnings": warnings}

    raise HTTPException(status_code=400, detail="unrecognized json format")


def _import_from_zip(payload: bytes) -> dict[str, Any]:
    """
    从ZIP文件导入
    
    导入设置、角色、聊天和头像文件。
    
    Args:
        payload: ZIP文件二进制数据
    
    Returns:
        dict[str, Any]: 导入结果 {"imported": [...], "warnings": [...]}
    """
    imported: list[str] = []
    warnings: list[str] = []
    worldbook_id_map: dict[str, str] = {}
    existing_worldbook_ids = {p.stem for p in worldbooks_dir().glob("*.json")}
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        if "settings.json" in zf.namelist():
            raw_settings = json.loads(zf.read("settings.json").decode("utf-8"))
            settings = Settings.model_validate(raw_settings)
            save_settings(settings)
            imported.append("settings")

        for name in zf.namelist():
            if not name.startswith("avatars/"):
                continue
            filename = name.split("/", 1)[-1]
            if not filename:
                continue
            data = zf.read(name)
            avatars_dir().mkdir(parents=True, exist_ok=True)
            avatar_path(filename).write_bytes(data)
        for name in zf.namelist():
            if name.startswith("worldbooks/") and name.endswith(".json"):
                raw = json.loads(zf.read(name).decode("utf-8"))
                original_id = str(raw.get("id") or "").strip()
                if not original_id:
                    original_id = name.split("/")[-1].replace(".json", "")
                    raw["id"] = original_id
                target_id = original_id
                if target_id in existing_worldbook_ids:
                    target_id = uuid4().hex
                    raw["id"] = target_id
                    worldbook_id_map[original_id] = target_id
                else:
                    worldbook_id_map[original_id] = original_id
                parsed_book = save_worldbook(WorldBook.model_validate(raw))
                existing_worldbook_ids.add(parsed_book.id)
                if "worldbook" not in imported:
                    imported.append("worldbook")
        for name in zf.namelist():
            if name.startswith("characters/") and name.endswith(".json"):
                raw = json.loads(zf.read(name).decode("utf-8"))
                attached = list(raw.get("attachedWorldBookIds") or [])
                if attached:
                    raw["attachedWorldBookIds"] = [worldbook_id_map.get(wid, wid) for wid in attached]
                card = CharacterCard.model_validate(raw)
                save_character(card)
                if "character" not in imported:
                    imported.append("character")
        for name in zf.namelist():
            # 只处理聊天记录文件 chat.json
            if not name.startswith("chats/") or not name.endswith("/chat.json"):
                continue
            parts = name.split("/")
            # 路径格式: chats/{character_id}/{chat_id}/chat.json
            if len(parts) != 4:
                continue
            character_id_from_path = parts[1]
            raw = json.loads(zf.read(name).decode("utf-8"))
            raw.pop("systemPrompt", None)
            raw.pop("lastSpeakerCharacterId", None)
            # 若 JSON 中缺少 characterId（历史/导出兼容），从路径补全
            if not raw.get("characterId"):
                raw["characterId"] = character_id_from_path
            chat = Chat.model_validate(raw)
            save_chat(chat)
            if "chat" not in imported:
                imported.append("chat")
        # 恢复长期记忆：处理 zip 中的 chat_memory.json（与 load_chat_memory 格式兼容）
        for name in zf.namelist():
            if not name.startswith("chats/") or not name.endswith("/chat_memory.json"):
                continue
            parts = name.split("/")
            # 路径格式: chats/{character_id}/{chat_id}/chat_memory.json
            if len(parts) != 4:
                continue
            character_id_from_path = parts[1]
            chat_id_from_path = parts[2]
            try:
                raw = json.loads(zf.read(name).decode("utf-8"))
                content = raw.get("longTermMemory") if isinstance(raw, dict) else None
                if content is None and isinstance(raw, dict):
                    content = raw.get("content")
                content = (content or "").strip()
                if content:
                    save_chat_memory(character_id_from_path, chat_id_from_path, content)
            except Exception:
                continue
    return {"imported": imported, "warnings": warnings}


@router.post("/import/janitor/pending")
def import_janitor_pending(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _cleanup_expired_janitor_chat_pending()
    raw = _validate_janitor_payload(payload)
    pending_id = uuid4().hex
    expires_at = datetime.now().astimezone() + timedelta(seconds=JANITOR_CHAT_PENDING_TTL_SECONDS)
    expires_at = expires_at.replace(microsecond=0)
    _janitor_chat_pending_store[pending_id] = (expires_at, raw)
    return {
        "ok": True,
        "pendingId": pending_id,
        "expiresAt": expires_at.isoformat(),
    }


@router.get("/import/janitor/pending/{pending_id}")
def get_janitor_pending_preview(pending_id: str) -> dict[str, Any]:
    _cleanup_expired_janitor_chat_pending()
    item = _janitor_chat_pending_store.get(pending_id)
    if not item:
        raise HTTPException(status_code=404, detail="janitor pending not found or expired")
    _, raw = item
    return {"ok": True, "preview": _janitor_preview_from_payload(raw)}


@router.post("/import/janitor/confirm")
def confirm_janitor_import(req: JanitorConfirmRequest) -> dict[str, Any]:
    _cleanup_expired_janitor_chat_pending()
    item = _janitor_chat_pending_store.get(req.pendingId)
    if not item:
        raise HTTPException(status_code=404, detail="janitor pending not found or expired")
    _, raw = item
    if not req.characterId.strip():
        raise HTTPException(status_code=400, detail="characterId is required")
    settings = load_settings()
    chat = Chat(
        characterId=req.characterId,
        title=_janitor_title(raw),
        userPersonaId=req.userPersonaId,
        messages=_janitor_messages_to_chat_messages(raw, req.characterId, req.userPersonaId, settings),
    )
    saved = save_chat(chat)
    _janitor_chat_pending_store.pop(req.pendingId, None)
    return {
        "ok": True,
        "imported": ["chat"],
        "warnings": [],
        "chat": saved.model_dump(mode="json"),
    }


def _parse_sillytavern_upload(payload: bytes, filename: str, content_type: str | None) -> tuple[dict[str, Any], bytes | None]:
    if not payload:
        raise HTTPException(status_code=400, detail="empty file")
    lower_name = filename.lower()
    if payload[:8] == PNG_SIGNATURE:
        try:
            return _extract_st_json_from_png(payload), payload
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid SillyTavern png: {e}") from e
    if lower_name.endswith(".json") or (content_type and "json" in content_type.lower()):
        try:
            raw = json.loads(payload.decode("utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        if not _looks_like_st_card(raw):
            raise HTTPException(status_code=400, detail="json is not a SillyTavern character card")
        return raw, None
    raise HTTPException(status_code=400, detail="unsupported SillyTavern file format")


@router.post("/import/sillytavern/preview")
async def preview_sillytavern_import(file: UploadFile = File(...)) -> dict[str, Any]:
    _cleanup_expired_sillytavern_pending()
    payload = await file.read()
    raw, png_payload = _parse_sillytavern_upload(payload, file.filename or "", file.content_type)
    preview = _build_sillytavern_preview(raw)
    pending_id = uuid4().hex
    expires_at = datetime.now().astimezone() + timedelta(seconds=SILLYTAVERN_IMPORT_PENDING_TTL_SECONDS)
    expires_at = expires_at.replace(microsecond=0)
    _sillytavern_pending_store[pending_id] = (
        expires_at,
        {
            "raw": raw,
            "pngPayload": png_payload,
            "filename": file.filename or "",
            "preview": preview,
        },
    )
    return {
        "ok": True,
        "pendingId": pending_id,
        "expiresAt": expires_at.isoformat(),
        "preview": preview,
    }


@router.post("/import/sillytavern/confirm")
def confirm_sillytavern_import(req: SillyTavernConfirmRequest) -> dict[str, Any]:
    _cleanup_expired_sillytavern_pending()
    item = _sillytavern_pending_store.get(req.pendingId)
    if not item:
        raise HTTPException(status_code=404, detail="SillyTavern pending not found or expired")
    _, stored = item
    raw = stored.get("raw")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="invalid SillyTavern pending payload")
    avatar_filename: str | None = None
    png_payload = stored.get("pngPayload")
    if isinstance(png_payload, bytes) and png_payload:
        avatar_filename = f"{uuid4().hex}.png"
        save_avatar(avatar_filename, png_payload)
    result = _import_sillytavern_card(
        raw,
        avatar_filename=avatar_filename,
        enable_mvu_compatibility=req.enableMvuCompatibility,
        mvu_mode=req.mvuMode,
    )
    _sillytavern_pending_store.pop(req.pendingId, None)
    return {"ok": True, **result}


def _decode_character_html_bytes(payload: bytes) -> str:
    if not payload:
        raise HTTPException(status_code=400, detail="empty html")
    try:
        return payload.decode("utf-8")
    except Exception:
        return payload.decode("utf-8", errors="ignore")


def _import_character_from_html_string(html: str, avatar_url_hint: str | None = None) -> dict[str, Any]:
    card, warnings = _parse_character_from_html(html, avatar_url_hint=avatar_url_hint)
    saved = save_character(card)
    return {
        "ok": True,
        "imported": ["character"],
        "warnings": warnings,
        "characterId": saved.id,
        "characterName": saved.name,
    }


def _import_character_from_janitor_json_dict(char: dict[str, Any], avatar_url_hint: str | None = None) -> dict[str, Any]:
    if not _janitor_char_json_has_greetings(char):
        raise HTTPException(status_code=400, detail="charJson must include first_message or first_messages")
    card, warnings = _parse_character_from_json(char, avatar_url_hint=avatar_url_hint)
    saved = save_character(card)
    return {
        "ok": True,
        "imported": ["character"],
        "warnings": warnings,
        "characterId": saved.id,
        "characterName": saved.name,
    }


@router.post("/import/janitor/character-json")
async def import_janitor_character_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")
    char = body.get("charJson")
    if not isinstance(char, dict):
        raise HTTPException(status_code=400, detail="charJson is required and must be an object")
    raw_hint = body.get("avatarUrl")
    avatar_url_hint = raw_hint.strip() if isinstance(raw_hint, str) and raw_hint.strip() else None
    try:
        return _import_character_from_janitor_json_dict(char, avatar_url_hint=avatar_url_hint)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/import/janitor/character-html")
async def import_janitor_character_html(request: Request, file: UploadFile | None = File(None)) -> dict[str, Any]:
    ct = (request.headers.get("content-type") or "").lower()
    html: str
    if "application/json" in ct:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="json body must be an object")
        raw_html = body.get("html")
        if not isinstance(raw_html, str) or not raw_html.strip():
            raise HTTPException(status_code=400, detail="html is required")
        html = raw_html
        raw_hint = body.get("avatarUrl")
        avatar_url_hint = raw_hint.strip() if isinstance(raw_hint, str) and raw_hint.strip() else None
    else:
        avatar_url_hint = None
        if file is None:
            raise HTTPException(status_code=400, detail="file is required for multipart upload")
        payload = await file.read()
        html = _decode_character_html_bytes(payload)
    try:
        return _import_character_from_html_string(html, avatar_url_hint=avatar_url_hint)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import")
async def import_data(file: UploadFile = File(...)) -> dict:
    """
    导入数据
    
    自动识别文件格式并导入：
    - ZIP文件（PK开头）：解压并导入所有内容
    - PNG文件（含 ccv3/chara tEXt）：按 SillyTavern 角色卡导入
    - JSON文件：导入设置/聊天/角色
    - TXT文件：解析聊天导出或角色卡片文本
    
    Args:
        file: 上传的文件
    
    Returns:
        dict: 导入结果 {"ok": True, "imported": [...], "warnings": [...]}
    
    Raises:
        HTTPException: 文件为空、格式不支持或解析失败时抛出相应错误
    """
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty file")

    filename = (file.filename or "").lower()
    try:
        if payload[:4] == b"PK\x03\x04":
            result = _import_from_zip(payload)
            return {"ok": True, **result}
        if payload[:8] == PNG_SIGNATURE:
            st_raw = _extract_st_json_from_png(payload)
            avatar_filename = f"{uuid4().hex}.png"
            save_avatar(avatar_filename, payload)
            return {"ok": True, **_import_sillytavern_card(st_raw, avatar_filename=avatar_filename)}
        if filename.endswith(".jsonl") or (file.content_type and "jsonl" in file.content_type):
            result = _import_from_jsonl(payload.decode("utf-8"))
            return {"ok": True, **result}
        if filename.endswith(".json") or (file.content_type and "json" in file.content_type):
            raw = json.loads(payload.decode("utf-8"))
            result = _import_from_json(raw)
            return {"ok": True, **result}
        text = payload.decode("utf-8")
        if "SimpleTavern Chat Export" in text or "[Message]" in text:
            chat = _parse_chat_text(text)
            save_chat(chat)
            return {"ok": True, "imported": ["chat"], "warnings": []}
        if "角色名称" in text or "【简介】" in text:
            card = _parse_character_text(text)
            save_character(card)
            return {"ok": True, "imported": ["character"], "warnings": []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    raise HTTPException(status_code=400, detail="unsupported file format")
