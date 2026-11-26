"""Exercise the shipped backend in an isolated profile. No provider credentials needed."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

import httpx
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/api-check"))
from checks_baseline import _chat
from checks_t832 import vertex_jwt_exchange
from harness import Api, Env
from mock_upstream import MockUpstream, REPLY


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(exe, web):
    with tempfile.TemporaryDirectory(prefix="酒馆 desktop ") as directory:
        ports = [free_port() for _ in range(3)]
        origin = f"http://127.0.0.1:{ports[0]}"
        proc = subprocess.Popen([str(exe), "--port", str(ports[0]), "--api-port", str(ports[1]),
            "--web", str(web), "--version", "1.0.0"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
            env={**os.environ, "PATH": os.pathsep.join(str(Path(os.environ["SystemRoot"]) / p)
                                                      for p in ("System32", "System32/WindowsPowerShell/v1.0")),
                 "SIMPLETAVERN_DATA_DIR": directory, "NO_PROXY":"127.0.0.1,localhost"})
        events = queue.Queue()
        def read():
            for line in proc.stdout:
                events.put(json.loads(line))
            events.put(None)
        def command(action, **fields):
            proc.stdin.write((json.dumps({"action": action, **fields}) + "\n").encode())
            proc.stdin.flush()
        def expect(event):
            item = events.get(timeout=45)
            while item and item["event"] != event and item["event"] in ("request", "voices", "appearance_changed"):
                if item["event"] == "request":
                    assert set(item) == {"event", "category", "status"}
                item = events.get(timeout=45)
            if item is None:
                raise AssertionError(proc.stderr.read().decode(errors="replace")[-2500:])
            assert item["event"] == event, item
            return item

        threading.Thread(target=read, daemon=True).start()
        try:
            expect("ready")
            with httpx.Client(base_url=origin, trust_env=False) as client:
                assert "simpletavern-desktop" in client.get("/chat").text
                assert client.get(f"http://127.0.0.1:{ports[1]}/api/health").json()["ok"]
                assert client.get("/api/tokenizer/health").raise_for_status().json()["available"]
                vocabulary = ROOT / "backend/tokenizer/deepseek_v3_tokenizer/tokenizer.json"
                reference = Tokenizer.from_file(str(vocabulary))
                sample = "酒馆でチャット 👨‍👩‍👦‍👦\n안녕하세요\t123456"
                tokens = client.post("/api/tokenizer/count", json={"text": sample}).raise_for_status().json()
                assert tokens["tokens"] == len(reference.encode(sample).ids)
                print("PASS packaged tokenizer matches the source vocabulary")
                assert client.get("/api/desktop/state").status_code == 403
                headers = {"Sec-Fetch-Site":"same-origin", "X-SimpleTavern-Desktop":"1"}
                token = client.get("/api/desktop/state", headers=headers).json()["session"]
                assert client.post("/api/desktop/update/check", headers=headers).status_code == 403
                headers.update({"Origin":origin, "X-Desktop-Session":token})
                assert client.post("/api/desktop/update/check", headers=headers).status_code == 200
                assert expect("update_action")["action"] == "check"
                assert client.post("/api/update/run").status_code == 409
                assert client.get("/api/update/startup-check").json()["shouldNotify"] is False
                print("PASS stable chat address, extension API and desktop update session")
                settings = client.get("/api/settings").raise_for_status().json()
                settings["ttsEnabled"] = True
                settings["apiPresets"].append({
                    "id": "external-test", "name": "外部测试网关", "presetKind": "tts",
                    "ttsProvider": "glm_local", "ttsGlmLocalManaged": False,
                    "baseUrl": f"http://127.0.0.1:{ports[1]}/api", "ttsGlmLocalPort": ports[1],
                })
                client.put("/api/settings", json=settings).raise_for_status()
                assert expect("appearance_changed") == {"event": "appearance_changed"}
                rows = expect("voices")["rows"]
                assert any(r["id"] == "external-test" and not r["managed"] and not r["owned"] for r in rows)
                command("voice", id="external-test", op="health")
                assert expect("voice_result")["state"] == "external_ready"
                assert expect("voices")["rows"][0]["owned"] is False
                print("PASS external speech gateway is reachable and reported as externally owned")
                gateway = Path(directory) / "qa-gateway"
                gateway.mkdir()
                gateway_port = free_port()
                (gateway / "run_api_gpu.ps1").write_text("""
$server = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, [int]$env:GLMTTS_API_PORT)
$server.Start()
try {
    while ($true) {
        $connection = $server.AcceptTcpClient()
        try {
            $stream = $connection.GetStream()
            $reader = [IO.StreamReader]::new($stream)
            while ($reader.ReadLine()) {}
            $reply = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 200 OK`r`nContent-Length: 2`r`nConnection: close`r`n`r`n{}")
            $stream.Write($reply, 0, $reply.Length)
        } finally { $connection.Dispose() }
    }
} finally { $server.Stop() }
""", encoding="ascii")
                settings["apiPresets"].append({
                    "id": "owned-test", "name": "受管测试网关", "presetKind": "tts", "ttsProvider": "glm_local",
                    "ttsGlmLocalManaged": True, "ttsGlmLocalRepoPath": str(gateway),
                    "ttsGlmLocalPort": gateway_port, "baseUrl": f"http://127.0.0.1:{gateway_port}",
                })
                client.put("/api/settings", json=settings).raise_for_status()
                expect("voices")
                command("voice", id="owned-test", op="start")
                assert expect("voice_result")["state"] == "owned"
                rows = expect("voices")["rows"]
                assert next(r for r in rows if r["id"] == "owned-test")["owned"]
                command("voice", id="owned-test", op="stop")
                assert expect("voice_result")["state"] == "idle"
                expect("voices")
                with socket.socket() as probe:
                    assert probe.connect_ex(("127.0.0.1", gateway_port)) != 0
                assert client.get(f"http://127.0.0.1:{ports[1]}/api/health").is_success
                print("PASS started and stopped a managed gateway process while the external gateway remained reachable")
                mock = MockUpstream(ports[2]).start()
                try:
                    api = Api(origin)
                    env = Env(api, mock)
                    env.fixtures["openai_key"] = secrets.token_hex(12)
                    chat = _chat(env, "openai_compatible_chat")
                    upstream_started = threading.Event()
                    release_reply = threading.Event()
                    handler = mock.server.RequestHandlerClass
                    start_stream = handler._start_stream
                    def hold_stream(request, content_type):
                        start_stream(request, content_type)
                        upstream_started.set()
                        release_reply.wait(15)
                    handler._start_stream = hold_stream
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        generating = pool.submit(env.generate, chat)
                        try:
                            assert upstream_started.wait(15)
                            command("drain")
                            deadline = time.monotonic() + 4
                            while not client.get("/api/desktop/state", headers=headers).json()["draining"]:
                                assert time.monotonic() < deadline
                                time.sleep(.05)
                            assert client.post("/api/chats", json={}).status_code == 503
                            # Synchronize on a control action during the held stream.
                            assert client.post("/api/desktop/update/check", headers=headers).is_success
                            expect("update_action")
                            assert not generating.done()
                        finally:
                            release_reply.set()
                        result = generating.result(timeout=20)
                    expect("drained")
                    command("cancel")
                    assert result.is_sse and result.succeeded and result.text == REPLY, result.summary()
                    assert env.read_chat(chat)["messages"][-1]["content"] == REPLY
                    print("PASS active generation survives drain, persists the full response and then becomes idle")
                    vertex_jwt_exchange(env)
                    api.client.close()
                    print("PASS packaged Vertex service account signs a JWT and exchanges it for an access token")
                finally:
                    mock.stop()
                command("drain")
                expect("drained")
                assert client.post("/api/chats", json={}).status_code == 503
                command("cancel")
                command("voices")
                expect("voices")
                assert client.get("/api/desktop/state",headers=headers).json()["draining"] is False
                command("drain")
                expect("drained")
                command("shutdown")
            assert proc.wait(timeout=20) == 0
            print("PASS cancelable service drain and graceful shutdown")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=ROOT/"temp/windows-build/frozen/TavernService/TavernService.exe")
    parser.add_argument("--web", type=Path, default=ROOT/"frontend/dist")
    args = parser.parse_args()
    run(args.exe.resolve(), args.web.resolve())
