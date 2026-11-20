"""Packaged loopback service. Its parent owns both control pipes."""
import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading

import uvicorn
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles


def emit(event, **fields):
    with output_lock:
        print(json.dumps({"event": event, **fields}, ensure_ascii=True), file=control_out, flush=True)


class WorkGate:
    """Count mutating requests until their final streaming/background work finishes."""
    def __init__(self):
        self.pending = 0
        self.draining = False

    def middleware(self, app):
        async def wrapped(scope, receive, send):
            work = (scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS")
                    and not scope["path"].startswith("/api/desktop/"))
            if not work:
                return await app(scope, receive, send)
            if self.draining:
                return await JSONResponse({"detail": "服务正在重启，请稍后再试"}, 503)(scope, receive, send)
            self.pending += 1
            try:
                await app(scope, receive, send)
            finally:
                self.pending -= 1
        return wrapped


def listener(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen()
        return sock
    except OSError:
        sock.close()
        emit("port_error", port=port)
        raise


async def run(args):
    from app.main import app
    from app import desktop_voice
    from app.content_regex_scanner import scan_in_progress
    from app.services.mvu_daemon import work_in_progress
    from app.services.work_drain import draining

    origin = f"http://127.0.0.1:{args.port}"
    token = secrets.token_urlsafe(32)
    gate = WorkGate()
    update = {"phase": "idle", "version": args.version, "message": ""}
    commands = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def read_control():
        try:
            with os.fdopen(os.dup(sys.stdin.fileno()), "rb", buffering=0) as pipe:
                for line in pipe:
                    loop.call_soon_threadsafe(commands.put_nowait, json.loads(line))
        finally:
            loop.call_soon_threadsafe(commands.put_nowait, {"action": "parent_closed"})

    @app.get("/api/desktop/state")
    async def desktop_state(request: Request):
        require_page(request)
        return JSONResponse({**update, "session": token, "draining": gate.draining},
                            headers={"Cache-Control": "no-store"})

    def require_page(request):
        if (request.headers.get("host") != origin.removeprefix("http://")
                or request.headers.get("sec-fetch-site") != "same-origin"
                or request.headers.get("x-simpletavern-desktop") != "1"
                or request.headers.get("origin", origin) != origin):
            raise HTTPException(403, "请从当前酒馆页面操作")

    @app.post("/api/desktop/update/{action}")
    async def update_action(action: str, request: Request):
        require_page(request)
        if request.headers.get("origin") != origin or not secrets.compare_digest(
                request.headers.get("x-desktop-session", ""), token):
            raise HTTPException(403, "请重新检查更新")
        if action not in ("check", "download", "restart", "cancel"):
            raise HTTPException(404)
        emit("update_action", action=action)
        return {"ok": True}

    # Old open tabs must never be able to launch the source-tree installer.
    @app.middleware("http")
    async def packaged_api(request, call_next):
        if request.url.path == "/api/update/version":
            return JSONResponse({"version": args.version, "desktop": True})
        if request.url.path == "/api/update/startup-check":
            return JSONResponse({"shouldNotify": False, "hasUpdate": False})
        if request.url.path.startswith("/api/update/"):
            return JSONResponse({"detail": "请使用服务管理器更新桌面版"}, 409)
        response = await call_next(request)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.url.path.startswith("/api/desktop/"):
            # Only a fixed category and status cross the pipe. Paths may contain user data.
            section = request.url.path.split("/", 3)[2] if request.url.path.startswith("/api/") else ""
            category = {"settings": "设置", "tts": "语音", "chats": "会话", "characters": "角色",
                        "import": "导入", "llm": "模型"}.get(section, "本地服务")
            emit("request", category=category, status=response.status_code)
            if request.url.path == "/api/settings" and response.status_code < 300:
                commands.put_nowait({"action": "voices"})
        return response

    static_root = args.web.resolve()
    html = (static_root / "index.html").read_text(encoding="utf-8").replace(
        "<head>", '<head><meta name="simpletavern-desktop" content="1">', 1)

    @app.get("/")
    @app.get("/chat")
    @app.get("/characters")
    async def index():
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=static_root), name="desktop-chat")
    server = uvicorn.Server(uvicorn.Config(gate.middleware(app), loop="asyncio", http="h11",
                                           ws="none", access_log=False, log_config=None,
                                           timeout_graceful_shutdown=4))
    with contextlib.ExitStack() as stack:
        sockets = [stack.enter_context(listener(p)) for p in dict.fromkeys((args.port, args.api_port))]
        serving = asyncio.create_task(server.serve(sockets=sockets))
        threading.Thread(target=read_control, daemon=True).start()
        while not server.started and not serving.done():
            await asyncio.sleep(.05)
        if not server.started:
            await serving
            return
        emit("ready")
        pending_voice = set()
        reported_idle = False
        orphaned = False
        async def voice(command):
            try:
                await desktop_voice.handle(command, emit)
            except Exception as exc:
                emit("voice_error", kind=type(exc).__name__)
        while not serving.done():
            try:
                command = await asyncio.wait_for(commands.get(), .15)
            except asyncio.TimeoutError:
                command = {}
            action = command.get("action")
            if action == "update_state":
                update = command["state"]
            elif action == "drain":
                gate.draining = True
                draining.set()
                reported_idle = False
            elif action == "cancel":
                gate.draining = False
                draining.clear()
                reported_idle = False
            elif action == "parent_closed":
                gate.draining = True
                draining.set()
                orphaned = True
            elif action in ("voices", "voice") and not gate.draining:
                task = asyncio.create_task(voice(command))
                pending_voice.add(task)
                task.add_done_callback(pending_voice.discard)
            if gate.draining and not (gate.pending or pending_voice or work_in_progress() or scan_in_progress()):
                if orphaned or action == "shutdown":
                    server.should_exit = True
                    break
                if not reported_idle:
                    emit("drained")
                    reported_idle = True
        await serving


if __name__ == "__main__":
    # Only explicit manager events enter the control channel, even if a library
    # prints raw upstream content or a traceback during startup.
    output_lock = threading.Lock()
    control_out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="ascii")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--api-port", required=True, type=int)
    parser.add_argument("--web", required=True, type=Path)
    parser.add_argument("--version", required=True)
    os.environ["SIMPLETAVERN_DESKTOP"] = "1"
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as exc:
        emit("failed", kind=type(exc).__name__)
        raise SystemExit(1)
