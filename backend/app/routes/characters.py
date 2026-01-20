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
    return datetime.now().astimezone().isoformat()


@router.get("/characters", response_model=list[CharacterCard])
def get_characters() -> list[CharacterCard]:
    return list_characters()


@router.post("/characters", response_model=CharacterCard)
def create_character(card: CharacterCard) -> CharacterCard:
    # 前端可直接传完整卡；这里确保时间字段
    if not card.createdAt:
        card.createdAt = _now_iso()
    card.updatedAt = _now_iso()
    return save_character(card)


@router.get("/characters/{character_id}", response_model=CharacterCard)
def get_character(character_id: str) -> CharacterCard:
    try:
        return load_character(character_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")


@router.put("/characters/{character_id}", response_model=CharacterCard)
def update_character(character_id: str, card: CharacterCard) -> CharacterCard:
    # 保留 createdAt（避免编辑时覆盖）
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
    delete_character(character_id)
    return {"ok": True}


