"""前端回归检查入口：建无密钥沙箱，起后端、前端、模拟模型和无头 Chromium，跑检查，收尾。说明见 README.md。"""
import argparse
import asyncio
import copy
import glob
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(REPO, "temp", "ui-check")

SECRET_KEY = re.compile(r"(api_?key|secret|token|password|cookie|credential|authorization)", re.I)
NOT_SECRET_KEY = re.compile(r"(tokens|token_?count|max_?token)", re.I)
SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|tvly-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{12,}|AIza[A-Za-z0-9_-]{20,}|xai-[A-Za-z0-9]{12,}|Bearer\s+[A-Za-z0-9._-]{16,}|eyJ[A-Za-z0-9_-]{20,}\.)")
URL_KEYS = ("baseUrl", "baseURL", "base_url", "apiBase", "endpoint")
LAST_PARAGRAPH = "他在门口停了一下，回头看了看身后的长廊。灯光从高处落下来，把影子拉得很长。没有人说话，只有远处传来断断续续的钟声。"


# ---------- 模拟模型 ----------
class MockState:
    tps = 1500
    # None 正常回复；http401、http429、http500 直接返回错误；stream_error 流里报错；stream_reset 流到一半断连接
    fault = None
    seen = []  # 收到过的请求：路径和鉴权头，用来确认密钥探针确实被发了出去


REASONING = "先判断语气，回答不宜太长，但要留一个钩子让对话继续。先写动作，再写一句话，最后用环境收尾。" * 6
REPLY = ("他把最后一笼包子挪到靠窗的位置，抬头看了你一眼。\n\n“这么晚还没吃？”他擦了擦手，从蒸笼底下摸出两个还冒着热气的。\n\n"
         "窗外的路灯忽明忽暗，**有只猫蹲在台阶上**，尾巴一下一下扫着落叶。\n\n他没再问什么，只是把收音机的声音调小了一点。\n\n") * 2


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": "mock", "object": "model"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        auth = self.headers.get("Authorization") or self.headers.get("x-api-key") or ""
        MockState.seen.append({"path": self.path, "auth": auth})
        fault = MockState.fault
        if fault in ("http401", "http429", "http500"):
            # 有些上游会把收到的密钥写回错误信息，这里故意回显，看它会不会进界面和日志
            echoed = auth.replace("Bearer ", "")
            data = json.dumps({"error": {"message": f"模拟上游错误，收到的密钥是 {echoed}", "type": "mock"}}, ensure_ascii=False).encode()
            self.send_response(int(fault[4:]))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not request.get("stream"):
            self._json({"id": "mock", "object": "chat.completion", "model": "mock", "choices": [
                {"index": 0, "message": {"role": "assistant", "content": REPLY[:40]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        step = 4

        def send(delta, finish=None):
            chunk = {"id": "mock", "object": "chat.completion.chunk", "model": "mock", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n")
            self.wfile.flush()

        try:
            send({"role": "assistant"})
            if fault == "stream_error":
                send({"content": "流里出错之前的半句"})
                self.wfile.write(b'data: {"error": {"message": "\xe6\xa8\xa1\xe6\x8b\x9f\xe6\xb5\x81\xe5\x86\x85\xe9\x94\x99\xe8\xaf\xaf", "code": 500}}\n\n')
                self.wfile.flush()
                return
            if fault == "stream_reset":
                send({"content": "断流之前的半句"})
                time.sleep(0.5)
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                self.close_connection = True
                self.connection.close()
                return
            for field, text in (("reasoning_content", REASONING), ("content", REPLY)):
                for i in range(0, len(text), step):
                    send({field: text[i:i + step]})
                    time.sleep(step / MockState.tps)
            send({}, "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


# ---------- 沙箱 ----------
REAL_SECRETS = set()


def scrub(node, mock_url, counters, rewrite_urls):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if SECRET_KEY.search(key) and not NOT_SECRET_KEY.search(key) and isinstance(value, str) and value:
                if len(value) >= 12:
                    # 只留在内存里，用来确认真实密钥没有进沙箱和日志，绝不打印或写盘
                    REAL_SECRETS.add(value)
                node[key] = "sandbox-dummy"
                counters["keys"] += 1
            elif rewrite_urls and key in URL_KEYS and isinstance(value, str) and value.startswith("http"):
                node[key] = mock_url
                counters["urls"] += 1
            else:
                scrub(value, mock_url, counters, rewrite_urls)
    elif isinstance(node, list):
        for value in node:
            scrub(value, mock_url, counters, rewrite_urls)


def extend_messages(chat, minimum):
    messages = chat.get("messages") or []
    seedless = [m for m in messages if str(m.get("content") or "").strip()]
    if not seedless:
        seedless = [{"version": 1, "role": "assistant", "content": "沙箱占位消息。", "ts": chat.get("createdAt")}]
    i = 0
    while len(messages) < minimum:
        clone = copy.deepcopy(seedless[i % len(seedless)])
        clone["id"] = uuid.uuid4().hex
        clone.pop("versions", None)
        messages.append(clone)
        i += 1
    chat["messages"] = messages


def build_sandbox(source, data_dir, mock_url):
    if not os.path.isdir(source):
        sys.exit(f"找不到数据目录：{source}")
    if os.path.realpath(source) == os.path.realpath(data_dir):
        sys.exit("沙箱目录不能和数据目录相同")
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    shutil.copytree(source, data_dir, ignore=shutil.ignore_patterns("*.lock", "backups", "http_log", "tts_cache", "huggingface"))
    counters = {"keys": 0, "urls": 0}
    for root, _, files in os.walk(data_dir):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception:
                continue
            before = dict(counters)
            scrub(doc, mock_url, counters, name in ("settings.json", "assistant_settings.json"))
            if counters != before:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=2)
    leftover = []
    for root, _, files in os.walk(data_dir):
        for name in files:
            if name.endswith(".json"):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8", errors="ignore") as f:
                    if SECRET_VALUE.search(f.read()):
                        leftover.append(os.path.relpath(path, data_dir))
    if leftover:
        shutil.rmtree(data_dir)
        sys.exit(f"沙箱里仍有疑似密钥，已删除沙箱并停止：{leftover[:5]}")
    print(f"沙箱已建：清空 {counters['keys']} 个密钥字段，改写 {counters['urls']} 个接口地址")

    singles, groups = [], []
    for path in glob.glob(os.path.join(data_dir, "chats", "**", "chat.json"), recursive=True):
        with open(path, encoding="utf-8") as f:
            chat = json.load(f)
        (groups if chat.get("isGroup") else singles).append((len(chat.get("messages") or []), path, chat))
    singles.sort(key=lambda row: -row[0])
    if len(singles) < 3 or not groups:
        sys.exit(f"检查需要至少 3 个单聊和 1 个群聊，现在只有 {len(singles)} 个单聊、{len(groups)} 个群聊")
    fixtures = {"group": groups[0][2]["id"]}
    for name, paragraphs, minimum, (_, path, chat) in zip(("LONG", "MID", "SHORT"), (60, 14, 1), (320, 60, 60), singles):
        extend_messages(chat, minimum)
        last = {"version": 1, "id": uuid.uuid4().hex, "role": "assistant", "ts": chat["messages"][-1].get("ts"),
                "characterId": chat["messages"][-1].get("characterId"),
                "content": f"【最后一条开头 {name}】\n\n" + "\n\n".join(f"{i + 1}. {LAST_PARAGRAPH}" for i in range(paragraphs)) + "\n\n【最后一条结尾】"}
        chat["messages"].append({k: v for k, v in last.items() if v is not None})
        # 构建产物上只能点侧栏，标题要唯一才找得到
        chat["title"] = f"沙箱 {name}"
        # 让搜索词命中足够多的消息，超过后端上限
        for message in chat["messages"][:-1]:
            if name == "LONG" and str(message.get("content") or "").strip():
                message["content"] = str(message["content"]) + "\n\n沙箱检索词"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(chat, f, ensure_ascii=False, indent=2)
        fixtures[name] = chat["id"]

    # 阅读字体需要一个字体文件
    fonts_dir = os.path.join(data_dir, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    if not os.listdir(fonts_dir):
        for candidate in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.isfile(candidate):
                shutil.copy(candidate, fonts_dir)
                break
    return fixtures


# ---------- 进程 ----------
def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_chrome():
    env = os.environ.get("UI_CHECK_CHROME")
    if env and os.path.isfile(env):
        return env
    local = os.environ.get("LOCALAPPDATA", "")
    for path in sorted(glob.glob(os.path.join(local, "ms-playwright", "chromium-*", "*", "chrome.exe")), reverse=True):
        return path
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", shutil.which("chromium") or "", shutil.which("google-chrome") or ""):
        if path and os.path.isfile(path):
            return path
    sys.exit("找不到 Chromium，请设置环境变量 UI_CHECK_CHROME")


def wait_http(url, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2).read(1)
            return
        except Exception:
            time.sleep(0.3)
    sys.exit(f"服务没有在 {seconds} 秒内启动：{url}")


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()


def main():
    parser = argparse.ArgumentParser(description="前端回归检查")
    parser.add_argument("--only", help="只跑这些检查，逗号分隔")
    parser.add_argument("--list", action="store_true", help="列出全部检查")
    parser.add_argument("--source", default=os.path.join(REPO, "data"), help="沙箱的数据来源，只读")
    parser.add_argument("--front-port", type=int, default=9381)
    parser.add_argument("--back-port", type=int, default=9391)
    parser.add_argument("--mock-port", type=int, default=9399)
    parser.add_argument("--cdp-port", type=int, default=9433)
    parser.add_argument("--built-port", type=int, default=9382)
    parser.add_argument("--dist", help="built 检查用这个现成的构建产物，不重新构建（用来做修改前的对照）")
    parser.add_argument("--built-only", action="store_true", help="core 和 modals 只跑构建产物，不跑开发服务器（做对照时用）")
    args = parser.parse_args()

    import checks

    if args.list:
        for name, fn in checks.CHECKS.items():
            print(f"{name:<12}{(fn.__doc__ or '').strip()}")
        return 0
    only = args.only.split(",") if args.only else list(checks.CHECKS)
    unknown = [name for name in only if name not in checks.CHECKS]
    if unknown:
        sys.exit(f"没有这些检查：{unknown}")
    for port in (args.front_port, args.built_port, args.back_port, args.mock_port, args.cdp_port):
        if not port_free(port):
            sys.exit(f"端口 {port} 已被占用，请换端口或先关闭占用它的程序")

    shots = os.path.join(WORK, "shots")
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(shots)
    data_dir = os.path.join(WORK, "data")
    mock_url = f"http://127.0.0.1:{args.mock_port}/v1"
    fixtures = build_sandbox(args.source, data_dir, mock_url)

    mock = ThreadingHTTPServer(("127.0.0.1", args.mock_port), MockHandler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    env = {**os.environ, "SIMPLETAVERN_DATA_DIR": data_dir, "PYTHONDONTWRITEBYTECODE": "1"}
    processes = []
    log = open(os.path.join(WORK, "services.log"), "w", encoding="utf-8", errors="replace")
    profile = tempfile.mkdtemp(prefix="ui-check-chrome-")
    try:
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.back_port)],
            cwd=os.path.join(REPO, "backend"), env=env, stdout=log, stderr=log))
        wait_http(f"http://127.0.0.1:{args.back_port}/api/settings")
        frontend = os.path.join(REPO, "frontend")
        vite = os.path.join(frontend, "node_modules", "vite", "bin", "vite.js")
        processes.append(subprocess.Popen(
            ["node", vite, "--port", str(args.front_port), "--strictPort", "--host", "127.0.0.1"],
            cwd=frontend, env={**env, "SIMPLETAVERN_API_PROXY": f"http://127.0.0.1:{args.back_port}"}, stdout=log, stderr=log))
        wait_http(f"http://127.0.0.1:{args.front_port}/")
        processes.append(subprocess.Popen(
            [find_chrome(), "--headless=new", f"--remote-debugging-port={args.cdp_port}", f"--user-data-dir={profile}",
             "--window-size=1440,900", "--hide-scrollbars", "--no-first-run", "--disable-gpu", "about:blank"],
            stdout=log, stderr=log))
        wait_http(f"http://127.0.0.1:{args.cdp_port}/json/version")

        built_url = []

        def serve_built():
            """构建到临时目录并启动预览，不碰 frontend/dist。多项检查共用一次构建。"""
            if built_url:
                return built_url[0]
            out_dir = os.path.abspath(args.dist) if args.dist else os.path.join(WORK, "dist")
            context.built_dir = out_dir
            front_env = {**env, "SIMPLETAVERN_API_PROXY": f"http://127.0.0.1:{args.back_port}"}
            if not args.dist:
                subprocess.run(["node", vite, "build", "--outDir", out_dir, "--emptyOutDir"], cwd=frontend, env=front_env, stdout=log, stderr=log, check=True)
            processes.append(subprocess.Popen(
                ["node", vite, "preview", "--outDir", out_dir, "--port", str(args.built_port), "--strictPort", "--host", "127.0.0.1"],
                cwd=frontend, env=front_env, stdout=log, stderr=log))
            url = f"http://127.0.0.1:{args.built_port}"
            wait_http(url + "/")
            built_url.append(url)
            return url

        context = checks.Context(
            base_url=f"http://127.0.0.1:{args.front_port}", api_url=f"http://127.0.0.1:{args.back_port}",
            cdp_port=args.cdp_port, shots_dir=shots, fixtures=fixtures, mock_state=MockState, serve_built=serve_built,
            work=WORK, data_dir=data_dir, log_path=log.name, real_secrets=REAL_SECRETS, built_only=args.built_only)
        failed = asyncio.run(checks.run(context, only))
    finally:
        for process in reversed(processes):
            stop(process)
        mock.shutdown()
        log.close()
        shutil.rmtree(profile, ignore_errors=True)
    print(f"截图和沙箱在 {WORK}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
