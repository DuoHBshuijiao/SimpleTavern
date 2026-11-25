"""Production checks for link-only sources footers and favicon loading."""

import asyncio
import base64
import itertools
import json
from urllib.parse import urlsplit

import websockets

import cdp
import dom_checks as dom


async def serve_source_icons(socket):
    """Keep the synthetic sites inside the browser's test session."""
    ids = itertools.count(2)
    async for raw in socket:
        event = json.loads(raw)
        if event.get("method") != "Fetch.requestPaused":
            continue
        params = event["params"]
        url = urlsplit(params["request"]["url"])
        media, status, body = "text/plain", 404, b""
        if (url.hostname, url.path) in [
            ("source1.fixture.test", "/favicon.ico"),
            ("source2.fixture.test", "/declared-icon.png"),
        ]:
            media, status, body = "image/png", 200, dom.png_bytes()
        elif url.hostname == "source2.fixture.test" and url.path == "/":
            media, status, body = "text/html", 200, b'<head><link rel="icon" href="/declared-icon.png"></head>'
        await socket.send(json.dumps({
            "id": next(ids), "method": "Fetch.fulfillRequest",
            "params": {
                "requestId": params["requestId"], "responseCode": status,
                "responseHeaders": [{"name": "Content-Type", "value": media},
                                    {"name": "Access-Control-Allow-Origin", "value": "*"}],
                "body": base64.b64encode(body).decode(),
            },
        }))


async def check_web_sources(ctx):
    """历史回复的来源卡片、重复链接、键盘展开和网站图标。"""
    fixture = "WEB-SOURCES"
    urls = [f"https://source{n}.fixture.test/articles/{n}?ref=reading" for n in range(1, 9)]
    same_site_url = "https://source1.fixture.test/articles/9"
    user_url = "https://example.test/user-link"
    code_url = "https://example.test/code-link"
    page = None
    card_id = None

    def write(path, payload):
        status, _, detail = dom.request(ctx, "POST", path, payload)
        if status != 200:
            raise RuntimeError(f"{path}: {detail.decode()[:200]}")
        return json.loads(detail)

    try:
        card_id = write("/api/characters", {"name": "来源检查角色", "firstMessage": ""})["id"]
        chat = write("/api/chats", {"characterId": card_id, "title": "来源检查会话"})
        ctx.fixtures[fixture] = chat["id"]
        path = f"/api/chats/{chat['id']}/messages"
        write(path, {"role": "assistant", "content": "这条回复用来对照没有来源的操作按钮位置。"})
        write(path, {"role": "user", "content": f"用户链接。\n\n来源： [{user_url}](<{user_url}>)"})
        body = (f"【最后一条开头 {fixture}】正文 [站内引用](<{urls[0]}>)。\n\n"
                "- **欧盟消息：**这是第一条。\n- **交通： **这是第二条。\n\n"
                f"```md\n- **原始范例：**保留\n来源：\n- {code_url}\n```\n\n"
                f"**来源：**\n- [第一站的文章](<{urls[0]}>)\n- {urls[1]}\n\n"
                "来源：\n" + "\n".join(f"- [资料 {i + 1}](<{url}>)" for i, url in enumerate(urls))
                + f"\n- {same_site_url}")
        write(path, {"role": "assistant", "content": body})

        page = await cdp.open_page(ctx.cdp_port, ctx.serve_built(), ctx.shots_dir, width=1120)
        await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        debugger = f"ws://127.0.0.1:{ctx.cdp_port}/devtools/page/{page.target_id}"
        async with websockets.connect(debugger) as socket:
            await socket.send(json.dumps({"id": 1, "method": "Fetch.enable", "params": {
                "patterns": [{"urlPattern": "https://*.fixture.test/*"}],
            }}))
            await socket.recv()
            icon_server = asyncio.create_task(serve_source_icons(socket))
            try:
                await dom.goto_app(page)
                await dom.enter_chat(ctx, page, fixture)
                row = "$rows().at(-1)"
                source = f"{row}.querySelector('.message-web-sources')"
                toggle = f"{source}.querySelector('.message-web-source-toggle')"
                toolbar = f"{row}.querySelector('.message-action-toolbar')"
                collapsed = await page.js(f"""(() => {{
                  const nav = {source};
                  const button = {toggle};
                  return nav?.querySelectorAll('a').length === 0 &&
                    button?.getAttribute('aria-expanded') === 'false' &&
                    button.textContent.trim() === '来源 · 9 篇';
                }})()""")
                ctx.check("默认只显示有文章数的来源胶囊", collapsed)
                if not collapsed:
                    return
                footer_layout = f"""(() => {{
                  const actions = {toolbar}.getBoundingClientRect();
                  const footer = {source}.querySelector('.message-web-source-toolbar').getBoundingClientRect();
                  const toggle = {toggle}.getBoundingClientRect();
                  const other = $rows().at(-3).querySelector('.message-footer');
                  const otherActions = other.querySelector('.message-action-toolbar').getBoundingClientRect();
                  const otherFooter = other.querySelector('.message-web-source-toolbar').getBoundingClientRect();
                  return {{offset: [actions.x - footer.x, actions.y - footer.y],
                            otherOffset: [otherActions.x - otherFooter.x, otherActions.y - otherFooter.y],
                            rightAligned: Math.abs(toggle.right - footer.right) <= 1 && toggle.left >= actions.right}};
                }})()"""
                layout = await page.js(footer_layout)
                ctx.check("来源靠右，有无来源时操作按钮起点一致",
                          layout["rightAligned"] and layout["offset"] == layout["otherOffset"], layout)
                alignment = await page.js(f"""(() => {{
                  const row = {row};
                  const author = row.querySelector('.message-author');
                  const button = $btn(row, '重写');
                  const body = row.querySelector('.stream-markdown p');
                  const textStart = el => {{
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    return range.getClientRects()[0].left;
                  }};
                  return {{start: [author, body, button].map(textStart), authorBackground: getComputedStyle(author).backgroundColor,
                    buttonWidth: button.getBoundingClientRect().width, buttonHeight: button.getBoundingClientRect().height,
                    buttonRadius: getComputedStyle(button).borderTopLeftRadius}};
                }})()""")
                ctx.check("角色名、正文和重写的文字对齐，角色名没有底色，按钮保留最小高度与圆角",
                          max(alignment["start"]) - min(alignment["start"]) <= 1
                          and alignment["authorBackground"] == "rgba(0, 0, 0, 0)" and alignment["buttonHeight"] >= 28
                          and alignment["buttonRadius"] != "0px", alignment)
                await page.js(f"{source}.scrollIntoView({{block:'center'}})")
                await page.mouse("mouseMoved", 8, 8)
                await page.wait_for(f"getComputedStyle({toolbar}).opacity === '0'")
                point = await page.js(f"""(() => {{
                  const b = {row}.querySelector('[data-chat-bubble-shell]').getBoundingClientRect();
                  const f = {source}.getBoundingClientRect();
                  return [b.left + 20, f.top - 16];
                }})()""")
                await page.mouse("mouseMoved", *point)
                await page.wait_for(f"getComputedStyle({toolbar}).opacity === '1'")
                await page.shot("web-sources-hover")
                await page.mouse("mouseMoved", 8, 8)
                await page.wait_for(f"getComputedStyle({toolbar}).opacity === '0'")
                ctx.check("鼠标离开后操作工具栏隐藏，右侧来源保留",
                          await page.js(f"getComputedStyle({toolbar}).pointerEvents === 'none' && !!{toggle}.offsetParent"))
                await page.key("Tab", 9)
                await page.js(f"{toolbar}.querySelector('button').focus({{preventScroll:true}})")
                await page.wait_for(f"getComputedStyle({toolbar}).opacity === '1'")
                ctx.check("键盘焦点可显示并操作工具栏",
                          await page.js(f"{toolbar}.contains(document.activeElement) && document.activeElement.matches(':focus-visible')"))
                ctx.check("行内引用、围栏代码和用户消息仍显示原始内容", await page.js(f"""(() => {{
                  const bubble = {row}.querySelector('.stream-markdown');
                  const previous = $rows().at(-2);
                  return bubble.querySelectorAll('a').length === 1 &&
                    bubble.querySelector('a').href === {json.dumps(urls[0])} &&
                    bubble.querySelector('pre code').textContent.includes({json.dumps(code_url)}) &&
                    previous.querySelector('.stream-markdown a').href === {json.dumps(user_url)} &&
                    !previous.querySelector('nav[aria-label=引用来源]');
                }})()"""))
                ctx.check("历史消息的中文列表标题加粗，代码内的原始格式保留", await page.js(f"""(() => {{
                  const bubble = {row}.querySelector('.stream-markdown');
                  const titles = [...bubble.querySelectorAll('li strong')].map(e => e.textContent);
                  return titles.join('/') === '欧盟消息/交通' &&
                    bubble.querySelector('pre code').textContent.includes('**原始范例：**保留');
                }})()"""))
                await page.js(f"{source}.scrollIntoView({{block:'center'}})")
                await page.shot("web-sources-collapsed")
                await page.js(f"{toggle}.focus()")
                await page.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter",
                                windowsVirtualKeyCode=13, text="\r")
                await page.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
                await page.wait_for(f"{toggle}.getAttribute('aria-expanded') === 'true'")
                opened_layout = await page.js(footer_layout)
                ctx.check("展开来源不挪动同排按钮",
                          opened_layout["rightAligned"] and opened_layout["offset"] == layout["offset"], opened_layout)
                links = await page.js(f"[...{source}.querySelectorAll('a')].map(a => a.href)")
                ctx.check("按回车展开后逐条展示九个网址，合并重复链接", links == [*urls, same_site_url], links)
                ctx.check("同站的两篇文章以标题和站点序号区分", await page.js(f"""(() => {{
                  const cards = {source}.querySelectorAll('a');
                  return cards[0].innerText.includes('第一站的文章') && cards[0].innerText.includes('source1.fixture.test') &&
                    cards[8].innerText.trim() === 'source1.fixture.test · 2';
                }})()"""))
                await page.wait_for(f"""[...{source}.querySelectorAll('img')]
                  .some(img => img.src.endsWith('/declared-icon.png') && img.naturalWidth > 0)""")
                ctx.check("展开后加载标准 favicon、页面声明的图标和通用回退", await page.js(f"""(() => {{
                  const cards = {source}.querySelectorAll('a');
                  return cards[0].querySelector('img')?.naturalWidth > 0 &&
                    cards[1].querySelector('img')?.naturalWidth > 0 && !!cards[2].querySelector('.lucide-globe');
                }})()"""))
                await page.send("Emulation.setDeviceMetricsOverride", width=420, height=800, deviceScaleFactor=1, mobile=False)
                await page.wait_for("getComputedStyle(document.querySelector('aside')).position === 'fixed'")
                await page.js("""if (Number(getComputedStyle(document.querySelector('aside')).opacity) >= .01)
                  document.querySelector('[aria-label=切换侧边栏]').click()""")
                await page.wait_for("Number(getComputedStyle(document.querySelector('aside')).opacity) < .01")
                await page.wait_for(f"{source}.getBoundingClientRect().right <= innerWidth + 1")
                await page.js(f"{source}.scrollIntoView({{block:'center'}})")
                ctx.check("窄屏来源卡片换行，行内无横向溢出", await page.js(f"""(() => {{
                  const nav = {source}, edges = nav.getBoundingClientRect();
                  const cards = [...nav.querySelectorAll('a')].map(a => a.getBoundingClientRect());
                  return edges.width > 0 && new Set(cards.map(r => r.top)).size > 1 &&
                    cards.every(r => r.left >= edges.left && r.right <= edges.right + 1);
                }})()"""))
                await page.shot("web-sources-expanded-narrow")
                await page.js(f"{toggle}.click()")
                ctx.check("可收起卡片并恢复来源计数", await page.js(
                    f"{source}.querySelectorAll('a').length === 0 && " +
                    f"{toggle}.getAttribute('aria-expanded') === 'false'"))
            finally:
                icon_server.cancel()
                await asyncio.gather(icon_server, return_exceptions=True)
    finally:
        if page:
            await ctx.close(page)
        if card_id:
            dom.request(ctx, "DELETE", f"/api/characters/{card_id}", None)
