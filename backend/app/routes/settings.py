from __future__ import annotations

from fastapi import APIRouter

from app.schemas import Settings
from app.storage import load_settings, save_settings


router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=Settings)
def get_settings() -> Settings:
    return load_settings()


@router.put("/settings", response_model=Settings)
def put_settings(settings: Settings) -> Settings:
    # 直接落盘（单用户本地）
    return save_settings(settings)


