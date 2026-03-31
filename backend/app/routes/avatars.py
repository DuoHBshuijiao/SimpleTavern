"""
头像管理路由模块

提供头像文件的上传、获取和删除API端点。

主要功能：
    - POST /avatars: 上传头像（接受base64编码的图片数据）
    - GET /avatars/{filename}: 获取头像文件
    - DELETE /avatars/{filename}: 删除头像文件

主要函数：
    - upload_avatar: 上传头像
    - get_avatar: 获取头像文件
    - remove_avatar: 删除头像文件

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入storage.py的头像管理函数
    - 依赖：依赖storage.py
    - 位置：路由层，处理头像相关的HTTP请求
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.schemas import CharacterCard, WorldBook
from app.storage import avatar_path, avatars_dir, delete_avatar, save_avatar

router = APIRouter(tags=["avatars"])
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class UploadAvatarRequest(BaseModel):
    """
    头像上传请求模型
    
    接受base64编码的图片数据，支持data URL格式。
    
    主要属性：
        imageData: base64编码的图片数据，可包含或不包含data:image/...;base64,前缀
        filename: 可选的文件名，如果不提供则自动生成UUID
    """
    imageData: str
    filename: str | None = None


class EmbeddedCharacterCardPreview(BaseModel):
    """头像 PNG 中内嵌的 ST 角色卡预览（仅解析，不落盘角色/世界书）。"""

    card: CharacterCard
    worldbook: WorldBook | None = None


class UploadAvatarResponse(BaseModel):
    """
    头像上传响应模型
    
    主要属性：
    filename: 保存后的文件名
    embeddedCharacterCard: 若上传 PNG 内嵌了 ST 角色卡，则返回解析预览
    """
    filename: str
    embeddedCharacterCard: EmbeddedCharacterCardPreview | None = None


def _extract_png_text_map(payload: bytes) -> dict[str, list[str]]:
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
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty st payload")
    if text.startswith("{"):
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("st payload is not object")
    compact = "".join(text.split())
    padded = compact + ("=" * (-len(compact) % 4))
    decoded = base64.b64decode(padded.encode("ascii"), validate=False)
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("st payload is not object")
    return parsed


def _extract_st_json_from_png(payload: bytes) -> dict[str, Any]:
    text_map = _extract_png_text_map(payload)
    for candidate in text_map.get("ccv3", []) + text_map.get("chara", []):
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


def _build_extra_first_entries(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    source = raw_data.get("alternate_greetings")
    if not isinstance(source, list):
        return []
    out: list[dict[str, Any]] = []
    for item in source:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            out.append({"text": text, "chip": True})
    return out


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
        try:
            order_index = int(raw.get("insertion_order", idx))
        except Exception:
            order_index = idx
        entries.append({
            "title": str(raw.get("comment") or "").strip() or f"条目 {idx + 1}",
            "content": str(raw.get("content") or "").strip(),
            "enabled": bool(raw.get("enabled", True)),
            "orderIndex": order_index,
            "regex": _st_entry_regex(raw),
        })
    if not entries:
        return None
    wb_name = _coalesce_st_text(character_book.get("name"), f"{card_name or '角色'} 世界书")
    return WorldBook(name=wb_name, entries=entries)


def _map_st_to_character_and_worldbook(raw: dict[str, Any]) -> tuple[CharacterCard, WorldBook | None]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    merged = dict(raw)
    if isinstance(data, dict):
        merged.update(data)
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


@router.post("/avatars", response_model=UploadAvatarResponse)
def upload_avatar(req: UploadAvatarRequest) -> UploadAvatarResponse:
    """
    上传头像
    
    接受base64编码的图片数据，支持data URL格式。
    自动识别图片格式（png/jpg/gif/webp），如果未指定文件名则生成UUID文件名。
    
    Args:
        req: 上传请求，包含base64图片数据和可选文件名
    
    Returns:
        UploadAvatarResponse: 包含保存后的文件名
    
    Raises:
        HTTPException: base64解码失败或保存失败时抛出400或500错误
    """
    try:
        image_data = req.imageData
        
        if "," in image_data:
            header, image_data = image_data.split(",", 1)
            if "png" in header.lower():
                ext = "png"
            elif "gif" in header.lower():
                ext = "gif"
            elif "webp" in header.lower():
                ext = "webp"
            else:
                ext = "jpg"
        else:
            ext = "png"
        
        try:
            data = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        if req.filename:
            filename = req.filename
        else:
            filename = f"{uuid4().hex}.{ext}"
        
        embedded_preview: EmbeddedCharacterCardPreview | None = None
        if data[:8] == PNG_SIGNATURE:
            try:
                st_raw = _extract_st_json_from_png(data)
                card, worldbook = _map_st_to_character_and_worldbook(st_raw)
                card.avatar = filename
                card.attachedWorldBookIds = []
                embedded_preview = EmbeddedCharacterCardPreview(card=card, worldbook=worldbook)
            except Exception:
                embedded_preview = None

        save_avatar(filename, data)
        
        return UploadAvatarResponse(filename=filename, embeddedCharacterCard=embedded_preview)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avatars/{filename}")
def get_avatar(filename: str) -> FileResponse:
    """
    获取头像文件
    
    根据文件扩展名设置正确的媒体类型。
    
    Args:
        filename: 头像文件名
    
    Returns:
        FileResponse: 头像文件响应
    
    Raises:
        HTTPException: 文件不存在时抛出404错误
    """
    p = avatar_path(filename)
    if not p.exists():
        raise HTTPException(status_code=404, detail="avatar not found")
    
    ext = p.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")
    
    return FileResponse(p, media_type=media_type)


@router.delete("/avatars/{filename}")
def remove_avatar(filename: str) -> dict:
    """
    删除头像文件
    
    Args:
        filename: 头像文件名
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_avatar(filename)
    return {"ok": True}
