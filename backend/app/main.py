from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.avatars import router as avatars_router
from app.routes.characters import router as characters_router
from app.routes.chats import router as chats_router
from app.routes.generate import router as generate_router
from app.routes.import_export import router as import_export_router
from app.routes.settings import router as settings_router
from app.routes.llm import router as llm_router
from app.storage import ensure_data_initialized


app = FastAPI(title="SimpleTavern", version="0.1.0")

# 单用户本地运行，默认放开 CORS 以便前端开发环境访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    ensure_data_initialized()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


app.include_router(settings_router, prefix="/api")
app.include_router(characters_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(avatars_router, prefix="/api")
app.include_router(import_export_router, prefix="/api")


