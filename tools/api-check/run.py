"""黑盒接口检查入口：建全新的空数据目录，启动后端和模拟上游，跑检查，收尾。说明见 README.md。"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(REPO, "temp", "api-check")


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url, seconds=90):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    end = time.time() + seconds
    while time.time() < end:
        try:
            opener.open(url, timeout=2).read(1)
            return
        except Exception:
            time.sleep(0.3)
    sys.exit(f"服务没有在 {seconds} 秒内启动：{url}")


def stop(process):
    """只停自己启动的进程及其子进程。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


class Backend:
    """一个用独立空数据目录的后端进程。"""

    def __init__(self, name, port, proxy_port):
        self.port = port
        self.data_dir = os.path.join(WORK, name, "data")
        self.log_path = os.path.join(WORK, name, "backend.log")
        self.proxy_port = proxy_port
        self.process = None
        self.log = None

    def start(self):
        os.makedirs(self.data_dir, exist_ok=True)
        self.log = open(self.log_path, "a", encoding="utf-8", errors="replace")
        # 代理指向模拟服务：后端若想访问外网，会在那里留下记录并被拒绝。httpx 不走代理访问本机。
        proxy = f"http://127.0.0.1:{self.proxy_port}"
        env = {**os.environ, "SIMPLETAVERN_DATA_DIR": self.data_dir, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
               "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "ALL_PROXY": proxy, "http_proxy": proxy, "https_proxy": proxy, "all_proxy": proxy,
               "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=os.path.join(REPO, "backend"), env=env, stdout=self.log, stderr=self.log)
        wait_http(f"http://127.0.0.1:{self.port}/api/health")
        return self

    def stop(self):
        if self.process:
            stop(self.process)
        if self.log:
            self.log.close()


def select(checks, only):
    if not only:
        return list(checks)
    wanted = [item.strip() for item in only.split(",") if item.strip()]
    chosen = [c for c in checks if any(c.name == w or c.name.startswith(w + ".") for w in wanted)]
    if not chosen:
        sys.exit(f"没有匹配的检查：{wanted}")
    return chosen


def main():
    parser = argparse.ArgumentParser(description="黑盒接口检查")
    parser.add_argument("--only", help="只跑这些检查，逗号分隔：t832,core,baseline,selftest，也可以写完整名字或前缀")
    parser.add_argument("--list", action="store_true", help="列出全部检查")
    parser.add_argument("--back-port", type=int, default=9701)
    parser.add_argument("--mock-port", type=int, default=9702)
    parser.add_argument("--second-port", type=int, default=9703, help="恢复演练用的第二个后端")
    parser.add_argument("--selftest-port", type=int, default=9718, help="自检用的模拟服务")
    parser.add_argument("--closed-port", type=int, default=9719, help="保持关闭，用来测上游连不上")
    parser.add_argument("--keep", action="store_true", help="结束后保留 temp/api-check（数据目录和后端日志）")
    args = parser.parse_args()

    if os.environ.get("PYTHONIOENCODING") is None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import checks_selftest
    import checks_baseline  # noqa: F401
    import checks_core  # noqa: F401
    import checks_t832  # noqa: F401
    import fixtures
    from harness import CHECKS, Api, Env, run_checks
    from mock_upstream import MockUpstream

    if args.list:
        for item in CHECKS:
            print(f"{item.name:<52}{item.doc}")
        print(f"\n共 {len(CHECKS)} 项")
        return 0

    selected = select(CHECKS, args.only)
    for port in (args.back_port, args.mock_port, args.second_port, args.selftest_port, args.closed_port):
        if not port_free(port):
            sys.exit(f"端口 {port} 已被占用，请换端口或先关闭占用它的程序")

    groups = {c.group for c in selected}
    selftests = [c for c in selected if c.group == "selftest"]
    others = [c for c in selected if c.group != "selftest"]
    checks_selftest.STATE["port"] = args.selftest_port

    passed, failed, notes = [], [], []
    if selftests:
        print(f"== 自检（{len(selftests)} 项，不启动后端）", flush=True)
        try:
            p, f, n = run_checks(selftests, None)
            passed += p
            failed += f
            notes += n
        finally:
            checks_selftest.stop_selftest_mock()

    backend = second = mock = None
    if others:
        if os.path.exists(WORK):
            shutil.rmtree(WORK)
        os.makedirs(WORK)
        mock = MockUpstream(args.mock_port).start()
        key = fixtures.generate_rsa_private_key()
        pem = fixtures.private_key_pem(key)
        info = fixtures.service_account_info(pem, mock.token_uri)
        mock.service_account = info
        mock.public_key = fixtures.public_key_pem(key)
        try:
            backend = Backend("main", args.back_port, args.mock_port).start()

            def start_second():
                nonlocal second
                if second is None:
                    second = Backend("restore", args.second_port, args.mock_port).start()
                return Api(f"http://127.0.0.1:{args.second_port}")

            def restart_second():
                start_second()
                second.stop()
                second.start()
                return Api(f"http://127.0.0.1:{args.second_port}")

            env = Env(Api(f"http://127.0.0.1:{args.back_port}"), mock, log_path=backend.log_path, second_backend=start_second, restart_second=restart_second, closed_port=args.closed_port)
            env.fixtures.update(bedrock_key=fixtures.bedrock_api_key(), mistral_key=fixtures.mistral_api_key(), pem=pem, sa_json=json.dumps(info), openai_key="sk-" + fixtures.mistral_api_key() + "abcdefgh")
            print(f"== 接口检查（{len(others)} 项，分组：{', '.join(sorted(groups - {'selftest'}))}）", flush=True)
            p, f, n = run_checks(others, env)
            passed += p
            failed += f
            notes += n
        finally:
            for process in (second, backend):
                if process:
                    process.stop()
            if mock:
                mock.stop()

    print()
    for group in sorted(groups):
        members = [c for c in selected if c.group == group]
        count_failed = sum(1 for item, _ in failed if item.group == group)
        count_note = sum(1 for item, _ in notes if item.group == group)
        print(f"{group}: 共 {len(members)} 项，通过 {len(members) - count_failed - count_note}，失败 {count_failed}，规格未定义 {count_note}")
    if notes:
        print("\n规格未定义（只记录观察结果）：")
        for item, text in notes:
            print(f"  {item.name}：{text}")
    if failed:
        print("\n失败：")
        for item, text in failed:
            print(f"  {item.name}：{text}")
    if args.keep:
        print(f"\n数据目录和后端日志保留在 {WORK}")
    elif os.path.exists(WORK):
        shutil.rmtree(WORK, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
