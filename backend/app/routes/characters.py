"""
角色管理路由模块

提供角色卡片的CRUD操作API端点。

主要功能：
    - GET /characters: 获取所有角色列表
    - POST /characters: 创建新角色
    - GET /characters/{character_id}: 获取指定角色
    - PUT /characters/{character_id}: 更新角色
    - DELETE /characters/{character_id}: 删除角色

主要函数：
    - get_characters: 获取所有角色
    - create_character: 创建新角色
    - get_character: 获取指定角色
    - update_character: 更新角色
    - remove_character: 删除角色

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入schemas.py的CharacterCard和storage.py的角色管理函数
    - 依赖：依赖schemas.py和storage.py
    - 位置：路由层，处理角色相关的HTTP请求
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.schemas import CharacterCard
from app.storage import (
    delete_character,
    list_characters,
    load_character,
    save_character,
)

router = APIRouter(tags=["characters"])


def _now_iso() -> str:
    """
    获取当前时间的ISO格式字符串
    
    Returns:
        str: 当前时间的ISO格式字符串
    """
    return datetime.now().astimezone().isoformat()


@router.get("/characters", response_model=list[CharacterCard])
def get_characters() -> list[CharacterCard]:
    """
    获取所有角色列表
    
    Returns:
        list[CharacterCard]: 角色卡片列表，按更新时间倒序
    """
    return list_characters()


@router.post("/characters", response_model=CharacterCard)
def create_character(card: CharacterCard) -> CharacterCard:
    """
    创建新角色
    
    前端可直接传递完整的角色卡片。如果未设置createdAt，则自动设置当前时间。
    自动更新updatedAt为当前时间。
    
    Args:
        card: 角色卡片对象
    
    Returns:
        CharacterCard: 创建后的角色卡片对象
    """
    if not card.createdAt:
        card.createdAt = _now_iso()
    card.updatedAt = _now_iso()
    return save_character(card)


@router.get("/characters/{character_id}", response_model=CharacterCard)
def get_character(character_id: str) -> CharacterCard:
    """
    获取指定角色
    
    Args:
        character_id: 角色ID
    
    Returns:
        CharacterCard: 角色卡片对象
    
    Raises:
        HTTPException: 角色不存在时抛出404错误
    """
    try:
        return load_character(character_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")


@router.put("/characters/{character_id}", response_model=CharacterCard)
def update_character(character_id: str, card: CharacterCard) -> CharacterCard:
    """
    更新角色
    
    保留原有的createdAt时间戳（避免编辑时覆盖）。
    如果URL中的character_id与card.id不一致，以URL中的ID为准。
    自动更新updatedAt为当前时间。
    
    Args:
        character_id: 角色ID（URL参数）
        card: 更新的角色卡片对象
    
    Returns:
        CharacterCard: 更新后的角色卡片对象
    
    Raises:
        HTTPException: 角色不存在且未提供createdAt时可能抛出404错误
    """
    try:
        existing = load_character(character_id)
        if not card.createdAt:
            card.createdAt = existing.createdAt
        elif existing.createdAt:
            card.createdAt = existing.createdAt
    except FileNotFoundError:
        if not card.createdAt:
            card.createdAt = _now_iso()

    if card.id != character_id:
        card.id = character_id
    card.updatedAt = _now_iso()
    return save_character(card)


@router.delete("/characters/{character_id}")
def remove_character(character_id: str) -> dict:
    """
    删除角色
    
    同时会删除该角色关联的所有聊天会话。
    
    Args:
        character_id: 角色ID
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_character(character_id)
    return {"ok": True}
