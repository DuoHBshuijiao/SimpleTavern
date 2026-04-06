"""Routes for in-memory data integrity issues and safe repair."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.services.data_integrity import data_integrity_service

router = APIRouter(tags=["data-integrity"])


class DataIntegrityRepairRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)


@router.get("/data-integrity/issues")
async def get_data_integrity_issues() -> dict:
    return await data_integrity_service.list_issues()


@router.post("/data-integrity/repair")
async def repair_data_integrity(body: DataIntegrityRepairRequest | None = None) -> dict:
    return await data_integrity_service.repair_issues(body.paths if body else None)