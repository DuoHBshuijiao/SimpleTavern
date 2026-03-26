"""
世界书管理路由模块
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import WorldBook
from app.storage import delete_worldbook, list_worldbooks, load_worldbook, save_worldbook

router = APIRouter(tags=["worldbooks"])


@router.get("/worldbooks", response_model=list[WorldBook])
def get_worldbooks() -> list[WorldBook]:
    return list_worldbooks()


@router.get("/worldbooks/{worldbook_id}", response_model=WorldBook)
def get_worldbook(worldbook_id: str) -> WorldBook:
    try:
        return load_worldbook(worldbook_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="worldbook not found")


@router.post("/worldbooks", response_model=WorldBook)
def create_worldbook(book: WorldBook) -> WorldBook:
    return save_worldbook(book)


@router.put("/worldbooks/{worldbook_id}", response_model=WorldBook)
def update_worldbook(worldbook_id: str, book: WorldBook) -> WorldBook:
    if book.id != worldbook_id:
        book.id = worldbook_id
    return save_worldbook(book)


@router.delete("/worldbooks/{worldbook_id}")
def remove_worldbook(worldbook_id: str) -> dict:
    delete_worldbook(worldbook_id)
    return {"ok": True}

