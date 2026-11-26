"""Exercise two locally built --qa releases through real Windows packaging and WebView2."""
import argparse
import asyncio
import base64
from contextlib import closing, ExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import websockets
import httpx
import pywintypes
import win32api
import win32file
import win32gui
import win32process

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/ui-check"))
from cdp import Page, open_page


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def until(read, timeout=70):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            result = read()
            if result:
                return result
        except (OSError, ValueError, PermissionError):
            pass
        await asyncio.sleep(.25)
    raise TimeoutError(getattr(read, "__name__", "condition"))


def manager_hwnd(pid):
    found = []
    def inspect(hwnd, unused):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == pid and "SimpleTavern" in win32gui.GetWindowText(hwnd):
            found.append(hwnd)
    win32gui.EnumWindows(inspect, None)
    return found[0] if found else None


async def attach(debug_port, run_dir):
    def target():
        with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=1) as response:
            return next((t for t in json.load(response) if t["type"] == "page"
                         and "tauri.localhost" in t["url"] and "SimpleTavern" in t["title"]), None)
    obj = await until(target)
    ws = await websockets.connect(obj["webSocketDebuggerUrl"], max_size=None, proxy=None)
    page = Page(ws, obj["id"], obj["url"], run_dir)
    await page.send("Page.enable")
    await page.send("Runtime.enable")
    try:
        await page.wait_for("document.getElementById('status')", 30)
    except TimeoutError:
        print("WebView2:", await page.js("[location.href, document.title, document.body?.innerText.slice(0, 300)]"), flush=True)
        await page.shot("unexpected-window")
        await disconnect(page)
        raise
    return page


async def disconnect(page):
    page.reader.cancel()
    await page.ws.close()


async def wait_for_appearance(page, theme, scheme):
    await page.wait_for(
        f"document.documentElement.dataset.theme === '{theme}' && "
        f"getComputedStyle(document.documentElement).colorScheme === '{scheme}'"
    )


async def check_manager_appearance(page, origin):
    await page.wait_for("!document.getElementById('primary').hidden")
    with httpx.Client(base_url=origin, trust_env=False) as api:
        settings = api.get("/api/settings").raise_for_status().json()

        def save(**changes):
            settings.update(changes)
            api.put("/api/settings", json=settings).raise_for_status()

        save(themeId="teal", themeMode="light")
        await wait_for_appearance(page, "teal", "light")
        assert await page.js("getComputedStyle(document.getElementById('primary')).backgroundColor") == "rgb(32, 90, 101)"
        await page.shot("manager-light")

        invalid = api.put("/api/settings", json={**settings, "themeMode": "invalid", "themeId": "blue"})
        assert invalid.status_code == 422
        assert await page.js("document.documentElement.dataset.theme") == "teal"

        async def upload(shade):
            image = await page.js(f"""(() => {{
              const canvas = document.createElement('canvas')
              const context = canvas.getContext('2d')
              context.fillStyle = '{shade}'
              context.fillRect(0, 0, canvas.width, canvas.height)
              return canvas.toDataURL().split(',')[1]
            }})()""")
            return api.post("/api/page-backgrounds", files={
                "file": ("wallpaper.png", base64.b64decode(image), "image/png")
            }).raise_for_status().json()["filename"]

        bright = await upload("#fbf8ed")
        dark = await upload("#14121a")
        save(themeMode="background", pageBackgroundImage=dark, pageBackgroundOpacity=1)
        await wait_for_appearance(page, "teal", "dark")
        save(pageBackgroundImage=bright)
        await wait_for_appearance(page, "teal", "light")
        save(pageBackgroundOpacity=0)
        await wait_for_appearance(page, "teal", "dark")
        save(pageBackgroundOpacity=1)
        await wait_for_appearance(page, "teal", "light")
        api.delete(f"/api/page-backgrounds/{bright}").raise_for_status()
        await wait_for_appearance(page, "teal", "dark")

        imported = {**settings, "themeId": "amber", "themeMode": "light"}
        result = api.post("/api/import", files={
            "file": ("settings.json", json.dumps(imported), "application/json")
        }).raise_for_status().json()
        assert "settings" in result["imported"]
        await wait_for_appearance(page, "amber", "light")

        save(themeId="green", themeMode="light")
        save(themeId="violet", themeMode="dark")
        await wait_for_appearance(page, "violet", "dark")
        await page.shot("manager-dark")
    print("PASS manager: saved and imported themes, rejected save, and wallpaper brightness", flush=True)


async def chat_tab(browser, origin, home):
    with httpx.Client(base_url=origin, trust_env=False) as api:
        card = api.post("/api/characters", json={"name": "QA", "description": "QA"}).raise_for_status().json()
        api.post("/api/chats", json={"characterId": card["id"], "title": "QA"}).raise_for_status()
    cdp_port = port()
    chrome = subprocess.Popen([browser, "--headless=new", "--no-first-run", "--disable-background-networking",
                               "--no-proxy-server", f"--remote-debugging-port={cdp_port}",
                               f"--user-data-dir={home / 'chat-browser'}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        await until(lambda: urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=1).close() is None)
        tab = await open_page(cdp_port, origin, home)
        await tab.send("Page.navigate", url=origin)
        await tab.wait_for("document.querySelector('textarea[placeholder^=发送消息]:not(:disabled)')", 30)
        await tab.js("""(() => {
            const field = document.querySelector('textarea[placeholder^=发送消息]');
            field.value = 'QA 未发送的草稿';
            field.dispatchEvent(new Event('input', {bubbles:true}));
            window.qaTimeOrigin = performance.timeOrigin;
        })()""")
        await tab.set_file('document.querySelector(\'input[accept="image/*"]\')', str(ROOT / "desktop/icons/icon.png"))
        await tab.wait_for('document.querySelector(\'img[alt="icon.png"]\')?.naturalWidth > 0')
        return chrome, tab
    except BaseException:
        chrome.terminate()
        chrome.wait(15)
        raise


async def run(mode, first, expected, run_dir, browser, feed):
    home = run_dir / mode
    home.mkdir()
    root = home / ("program 中文 目录" if mode == "installed" else "program")
    root.mkdir()
    debug_port, chat_port, api_port = (port() for _ in range(3))
    local = home / "local"
    local.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(local), WEBVIEW2_USER_DATA_FOLDER=str(home / "webview"),
               WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={debug_port} --no-proxy-server")
    system = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join(map(str, (system / "System32", system)))
    exe = root / "current/SimpleTavern.exe"
    if mode == "portable":
        with zipfile.ZipFile(next(first.glob("*QA-*-Portable.zip"))) as archive:
            archive.extractall(root)
        profile = root
    else:
        installer = next(first.glob("*QA-*-Setup.exe"))
        occupied = home / "occupied"
        occupied.mkdir()
        marker = occupied / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        rejected = subprocess.run([installer, "--silent", "--installto", occupied], env=env, timeout=30)
        assert rejected.returncode != 0 and list(occupied.iterdir()) == [marker]
        assert marker.read_text(encoding="utf-8") == "keep"
        subprocess.run([installer, "--silent", "--installto", root], env=env, check=True, timeout=100)
        other = home / "other-program"
        rejected = subprocess.run([installer, "--silent", "--installto", other], env=env, timeout=30)
        assert rejected.returncode != 0 and not other.exists()
        subprocess.run([installer, "--silent"], env=env, check=True, timeout=100)
        assert exe.is_file() and not (local / "SimpleTavernDesktopQA").exists()
        print("PASS installed: preserved other files and reused the registered custom directory", flush=True)
        profile = local / "SimpleTavernDesktopQA.User"
    profile.mkdir(exist_ok=True)
    (profile / "manager.json").write_text(json.dumps({"port": chat_port, "api_port": api_port}))
    process = subprocess.Popen([exe, "--resume"], env=env)
    page = None
    chrome = tab = None
    try:
        page = await attach(debug_port, home)
        await page.wait_for("document.getElementById('primary').textContent==='开始使用'")
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            occupied.bind(("127.0.0.1", chat_port))
            occupied.listen(1)
            await page.js("document.getElementById('primary').click()")
            await page.wait_for("document.getElementById('detail').textContent.includes('无法绑定')", 50)
            chat_port = port()
            await until(lambda: not manager_pids(root / "current/service/TavernService.exe"))
            await page.js(f"document.getElementById('port').value={chat_port}; document.getElementById('ports').requestSubmit()")
            await page.wait_for("document.getElementById('status').textContent==='酒馆正在运行'", 70)
            with socket.create_connection(occupied.getsockname(), timeout=2):
                pass
        print(f"PASS {mode}: changed conflicting port and kept its previous listener alive", flush=True)
        await page.wait_for("document.getElementById('status').textContent==='酒馆正在运行'", 70)
        hwnd = await until(lambda: manager_hwnd(process.pid))
        win32gui.PostMessage(hwnd, 0x0010, 0, 0)
        await page.wait_for("!document.getElementById('trayTip').hidden")
        await page.js("document.querySelector('[data-action=hide]').click()")
        await until(lambda: not win32gui.IsWindowVisible(hwnd))
        origin = f"http://127.0.0.1:{chat_port}"
        assert b"simpletavern-desktop" in urllib.request.urlopen(origin, timeout=3).read()
        second = subprocess.Popen([exe, "--resume"], env=env)
        assert await asyncio.to_thread(second.wait, 15) == 0
        await until(lambda: win32gui.IsWindowVisible(hwnd))
        await page.js("document.getElementById('logs').open=true")
        await page.wait_for("document.getElementById('entries').children.length>0")
        await page.shot("manager")
        await check_manager_appearance(page, origin)
        await page.wait_for("document.getElementById('update').textContent==='退出时更新'", 20)
        marker = profile / "data/qa-retained.txt"
        marker.write_text("retained", encoding="utf-8")
        if feed:
            assets = list(feed.glob(f"SimpleTavernDesktopQA-{expected}-*.nupkg"))
            assert assets, "QA packages for the target version are missing"
            with ExitStack() as locked:
                for asset in assets:
                    locked.enter_context(closing(win32file.CreateFile(str(asset), win32file.GENERIC_READ, 0,
                                                     None, win32file.OPEN_EXISTING, 0, None)))
                await page.js("document.getElementById('update').click()")
                await page.wait_for("document.getElementById('updateMessage').textContent.includes('校验失败')", 40)
                assert urllib.request.urlopen(origin + "/api/health").status == 200
            print(f"PASS {mode}: unavailable update left the previous service usable", flush=True)
        if browser:
            chrome, tab = await chat_tab(browser, origin, home)
            assert await tab.js("""(async () => {
                const headers = {'X-SimpleTavern-Desktop': '1'};
                const state = await (await fetch('/api/desktop/state', {headers})).json();
                headers['X-Desktop-Session'] = state.session;
                return (await fetch('/api/desktop/update/download', {method:'POST', headers})).ok;
            })()""")
        else:
            await page.js("document.getElementById('update').click()")
        await page.wait_for("document.getElementById('update').textContent==='立即重启更新'", 90)
        print(f"PASS {mode}: first use, tray, single instance, chat and background download", flush=True)
        button = "#update" if mode == "installed" else "[data-action=quit]"
        await page.js(f"document.querySelector('{button}').click()")
        await disconnect(page)
        page = None
        assert await asyncio.to_thread(process.wait, 45) == 0
        await until(lambda: expected in (root / "current/sq.version").read_text(encoding="utf-8-sig"))
        print(f"PASS {mode}: updater replaced the on-disk manifest", flush=True)
        if mode == "portable":
            await until(lambda: not manager_pids(root / "Update.exe"))
            process = subprocess.Popen([exe, "--resume"], env=env)
        page = await attach(debug_port, home)
        await wait_for_appearance(page, "violet", "dark")
        await page.wait_for("document.getElementById('status').textContent==='酒馆正在运行'", 70)
        assert await page.js("getComputedStyle(document.getElementById('primary')).borderRadius") == "12px"
        assert await page.js("getComputedStyle(document.getElementById('entries')).fontSize") == "12px"
        await page.wait_for(f"document.getElementById('version').textContent==='v{expected}'", 20)
        assert marker.read_text(encoding="utf-8") == "retained"
        assert urllib.request.urlopen(origin + "/api/update/version").status == 200
        if tab:
            assert await tab.js("""window.qaTimeOrigin===performance.timeOrigin &&
                document.querySelector('textarea[placeholder^=发送消息]').value==='QA 未发送的草稿' &&
                document.querySelector('img[alt="icon.png"]')?.naturalWidth > 0""")
            assert (await tab.js("(async () => (await fetch('/api/update/version')).json())()"))["version"] == expected
            print(f"PASS {mode}: original browser tab retained its draft and reached the updated service", flush=True)
        print(f"PASS {mode}: applied {expected}, original port and data preserved", flush=True)
        await page.js("document.querySelector('[data-action=quit]').click()")
        await until(lambda: not manager_pids(exe))
    finally:
        if tab is not None:
            await disconnect(tab)
        if chrome is not None:
            chrome.terminate()
            chrome.wait(15)
        if page is not None:
            await disconnect(page)
        # Terminate only manager processes from this unique QA directory.
        for pid in manager_pids(exe):
            with closing(win32api.OpenProcess(1, False, pid)) as handle:
                win32api.TerminateProcess(handle, 1)
        if mode == "installed" and (root / "Update.exe").exists():
            subprocess.run([root / "Update.exe", "uninstall", "--silent"], env=env, timeout=45)


def manager_pids(exe):
    matches = []
    for pid in win32process.EnumProcesses():
        try:
            with closing(win32api.OpenProcess(0x410, False, pid)) as handle:
                if Path(win32process.GetModuleFileNameEx(handle, 0)) == exe:
                    matches.append(pid)
        except pywintypes.error:
            continue
    return matches


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--mode", choices=["both", "portable", "installed"], default="both")
    parser.add_argument("--browser", type=Path, help="also verify an unsent draft in an isolated Chromium profile")
    parser.add_argument("--qa-feed", type=Path, help="also test a failed download by briefly locking the QA assets")
    opts = parser.parse_args()
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=opts.first.resolve().parent))
    print(run_dir, flush=True)
    for mode in (["portable", "installed"] if opts.mode == "both" else [opts.mode]):
        asyncio.run(run(mode, opts.first.resolve(), opts.expected, run_dir, opts.browser, opts.qa_feed))
