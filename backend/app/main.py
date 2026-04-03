"""
FastAPI应用入口模块

本模块是应用的入口点，负责：
- 创建FastAPI应用实例
- 配置CORS中间件
- 注册所有路由
- 应用启动时的初始化

主要功能：
    - 创建FastAPI应用
    - 配置CORS（允许所有来源，便于本地开发）
    - 应用启动时初始化数据目录
    - 注册所有API路由
    - 提供健康检查端点

主要函数：
    - lifespan: 应用生命周期（启动时初始化、关闭时可清理）
    - health: 健康检查端点

文件关系：
    - 被导入：无（作为应用入口被直接运行）
    - 导入：导入所有routes模块的router和storage模块
    - 依赖：依赖所有routes模块和storage模块
    - 位置：应用入口层，整合所有路由模块
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.avatars import router as avatars_router
from app.routes.characters import router as characters_router
from app.routes.chats import router as chats_router
from app.routes.clipboard import router as clipboard_router
from app.routes.font import router as font_router
from app.routes.generate import router as generate_router
from app.routes.import_export import router as import_export_router
from app.routes.settings import router as settings_router
from app.routes.llm import router as llm_router
from app.routes.assistant import router as assistant_router
from app.routes.tokenizer import router as tokenizer_router
from app.routes.update import router as update_router
from app.routes.worldbooks import router as worldbooks_router
from app.storage import ensure_data_initialized
from app.tokenizer_service import warmup_tokenizer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期：启动时初始化数据目录并预加载 tokenizer；
    关闭时无额外清理（yield 之后可添加 shutdown 逻辑）。
    """
    ensure_data_initialized()
    warmup_tokenizer()
    yield


app = FastAPI(title="SimpleTavern", version="v0.305", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """
    健康检查端点
    
    用于检查应用是否正常运行。
    
    Returns:
        dict: 健康状态 {"ok": True}
    """
    return {"ok": True}


app.include_router(settings_router, prefix="/api")
app.include_router(characters_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(clipboard_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(avatars_router, prefix="/api")
app.include_router(font_router, prefix="/api")
app.include_router(import_export_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(tokenizer_router, prefix="/api")
app.include_router(update_router, prefix="/api")
app.include_router(worldbooks_router, prefix="/api")
