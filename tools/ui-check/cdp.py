"""极简的 Chrome DevTools Protocol 驱动，只用 websockets，不引入 Playwright。"""
import asyncio
import base64
import json
import os
import urllib.request

import websockets

# 从任意元素走到 ChatPage 和设置抽屉的实例，开发模式下可以直接操作它们的状态。
HELPERS = r"""
(() => {
  const root = () => { let c = document.querySelector('#app *').__vueParentComponent; while (c.parent) c = c.parent; return c; };
  const find = (test) => {
    const seen = new Set();
    const walk = (i) => {
      if (!i || seen.has(i)) return null;
      seen.add(i);
      if (test(i)) return i;
      const stack = [i.subTree];
      while (stack.length) {
        const v = stack.pop();
        if (!v) continue;
        if (v.component) { const r = walk(v.component); if (r) return r; }
        if (Array.isArray(v.children)) stack.push(...v.children);
        if (v.suspense) stack.push(v.suspense.activeBranch);
      }
      return null;
    };
    return walk(root());
  };
  window.__chat = () => find((i) => i.setupState && i.setupState.actions && i.setupState.assistant);
  window.__drawer = () => find((i) => i.setupState && i.setupState.openRegexRuleEditor);
  window.__ui = () => document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('ui');
})()
"""

# 关掉挡操作的提示框，比如“未总结消息达到阈值”。
DISMISS = """(() => { const b=document.querySelector('.app-notify-backdrop'); if(!b) return false; const c=[...b.parentElement.querySelectorAll('button')].find(x=>x.innerText.trim()==='取消'); c&&c.click(); return !!c; })()"""


class Page:
    def __init__(self, ws, target_id, base_url, shots_dir):
        self.ws = ws
        self.target_id = target_id
        self.base_url = base_url
        self.shots_dir = shots_dir
        self.seq = 0
        self.pending = {}
        self.exceptions = []
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        async for raw in self.ws:
            message = json.loads(raw)
            if "id" in message and message["id"] in self.pending:
                self.pending.pop(message["id"]).set_result(message)
            elif message.get("method") == "Runtime.exceptionThrown":
                details = message["params"]["exceptionDetails"]
                self.exceptions.append((details.get("exception", {}).get("description") or details.get("text", ""))[:400])

    async def send(self, method, **params):
        self.seq += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[self.seq] = future
        await self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        result = await asyncio.wait_for(future, 30)
        if "error" in result:
            raise RuntimeError(f"{method}: {result['error']}")
        return result.get("result", {})

    async def js(self, expression):
        result = await self.send("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise RuntimeError(details.get("exception", {}).get("description") or str(details))
        return result["result"].get("value")

    async def goto(self, path="/", settle=2.5):
        await self.send("Page.navigate", url=self.base_url + path)
        await self.wait_for("document.readyState === 'complete'")
        await asyncio.sleep(settle)
        await self.js(HELPERS)
        await self.js(DISMISS)

    async def wait_for(self, expression, timeout=15):
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            if await self.js(f"!!({expression})"):
                return True
            await asyncio.sleep(0.05)
        raise TimeoutError(expression)

    async def shot(self, name):
        data = await self.send("Page.captureScreenshot", format="png")
        path = os.path.join(self.shots_dir, name + ".png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data["data"]))
        return path

    async def key(self, key, vk):
        for kind in ("keyDown", "keyUp"):
            await self.send("Input.dispatchKeyEvent", type=kind, key=key, code=key, windowsVirtualKeyCode=vk)

    async def wheel(self, delta_y, x=800, y=400):
        await self.send("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0, deltaY=delta_y)

    async def mouse(self, kind, x, y, **extra):
        await self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, **extra)


async def open_page(cdp_port, base_url, shots_dir, width=1440, height=900):
    request = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(request) as response:
        info = json.load(response)
    ws = await websockets.connect(info["webSocketDebuggerUrl"], max_size=None)
    page = Page(ws, info["id"], base_url, shots_dir)
    await page.send("Page.enable")
    await page.send("Runtime.enable")
    await page.send("Emulation.setFocusEmulationEnabled", enabled=True)
    await page.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
    return page


async def close_page(cdp_port, page):
    urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/close/{page.target_id}").read()
    page.reader.cancel()
    await page.ws.close()
