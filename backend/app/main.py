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

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_error_handlers
from app.request_context import REQUEST_ID_HEADER, RequestIdMiddleware
from app.routes.avatars import router as avatars_router
from app.routes.characters import router as characters_router
from app.routes.chats import router as chats_router
from app.routes.clipboard import router as clipboard_router
from app.routes.data_integrity import router as data_integrity_router
from app.routes.font import router as font_router
from app.routes.generate import router as generate_router
from app.routes.http_log import router as http_log_router
from app.routes.import_export import router as import_export_router
from app.routes.page_backgrounds import router as page_backgrounds_router
from app.routes.shader_presets import router as shader_presets_router
from app.routes.settings import router as settings_router
from app.routes.llm import router as llm_router
from app.routes.assistant import router as assistant_router
from app.routes.tokenizer import router as tokenizer_router
from app.routes.update import router as update_router
from app.routes.web_search import router as web_search_router
from app.routes.worldbooks import router as worldbooks_router
from app.routes.mvu import router as mvu_router
from app.routes.tts import router as tts_router
from app.services.data_integrity import data_integrity_service
from app.services.glm_local_tts_process import stop as stop_glm_local_tts
from app.services.http_client import shutdown_http_clients, startup_http_clients
from app.services.http_log_sweeper import http_log_sweeper
from app.services.omnivoice_local_tts_process import stop as stop_omnivoice_local_tts
from app.services.qwen3_local_tts_process import stop as stop_qwen3_local_tts
from app.services.tts_cache import tts_cache_patrol
from app.storage import ensure_data_initialized
from app.tokenizer_service import warmup_tokenizer
from app.version import APP_VERSION


async def _warm_fork_index() -> None:
    """启动后预热 fork 索引，避免首个 lineage 请求承担冷重建。"""
    from app.fork_index import rebuild_fork_index

    await asyncio.to_thread(rebuild_fork_index)


async def _warm_chat_path_index() -> None:
    """启动后预热 chatId→path 索引，避免首个 load_chat 全角色扫描。"""
    from app.chat_path_index import warm_chat_path_index

    await asyncio.to_thread(warm_chat_path_index)


async def _warm_worldbook_index() -> None:
    """启动后预热世界书激活索引，避免首个 generate 全库读盘。"""
    from app.worldbook_index import warm_worldbook_index

    await asyncio.to_thread(warm_worldbook_index)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期：启动时初始化数据目录并预加载 tokenizer；
    关闭时无额外清理（yield 之后可添加 shutdown 逻辑）。
    """
    ensure_data_initialized()
    warmup_tokenizer()
    await startup_http_clients()
    fork_index_task = asyncio.create_task(_warm_fork_index())
    chat_path_index_task = asyncio.create_task(_warm_chat_path_index())
    worldbook_index_task = asyncio.create_task(_warm_worldbook_index())
    integrity_scan_task = asyncio.create_task(data_integrity_service.run_startup_scan())
    await tts_cache_patrol.start()
    await http_log_sweeper.start()
    try:
        yield
    finally:
        await http_log_sweeper.stop()
        await tts_cache_patrol.stop()
        stop_glm_local_tts()
        stop_omnivoice_local_tts()
        stop_qwen3_local_tts()
        await shutdown_http_clients()
        fork_index_task.cancel()
        chat_path_index_task.cancel()
        worldbook_index_task.cancel()
        integrity_scan_task.cancel()
        try:
            await fork_index_task
        except asyncio.CancelledError:
            pass
        try:
            await chat_path_index_task
        except asyncio.CancelledError:
            pass
        try:
            await worldbook_index_task
        except asyncio.CancelledError:
            pass
        try:
            await integrity_scan_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="SimpleTavern", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(RequestIdMiddleware)
install_error_handlers(app)


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
app.include_router(data_integrity_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(web_search_router, prefix="/api")
app.include_router(avatars_router, prefix="/api")
app.include_router(font_router, prefix="/api")
app.include_router(http_log_router, prefix="/api")
app.include_router(page_backgrounds_router, prefix="/api")
app.include_router(shader_presets_router, prefix="/api")
app.include_router(import_export_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(tokenizer_router, prefix="/api")
app.include_router(update_router, prefix="/api")
app.include_router(mvu_router, prefix="/api")
app.include_router(worldbooks_router, prefix="/api")
app.include_router(tts_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=9091,
        reload=True,
        timeout_graceful_shutdown=3,
    )
