"""只操作 DOM 的检查：构建产物没有 Vue 实例，点击、输入和按键都走用户能做的路径。

core 和 modals 同一份代码在开发服务器和构建产物上各跑一遍，结果不一致时单独报出来。
其余是沙箱核对：主题、窗口尺寸、长会话耗时、错误路径和密钥扫描，只跑在构建产物上。
"""
import asyncio
import base64
import glob
import io
import json
import os
import re
import statistics
import struct
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

import cdp

THEMES = ("blue", "green", "teal", "violet", "amber", "rose", "sunset")
KEY_PROBE = "sk-uicheckprobe0123456789abcdefghij"

HELPERS = r"""
(() => {
  const cs = getComputedStyle;
  window.$s = () => { let e=[...document.querySelectorAll('.max-w-4xl.mx-auto')].find(x=>x.querySelector(':scope > .group')); while(e && !/auto|scroll/.test(cs(e).overflowY)) e=e.parentElement; return e; };
  window.$rows = () => { const s=$s(); return s ? [...s.querySelector('.max-w-4xl').children].filter(x=>x.classList.contains('group')) : []; };
  window.$last = () => { const el=$s(), rows=$rows(), r=el.getBoundingClientRect(), l=rows[rows.length-1].getBoundingClientRect();
    return {top:Math.round(l.top-r.top), pad:Math.round(parseFloat(cs(el).paddingTop)), rowH:Math.round(l.height), dist:Math.round(el.scrollHeight-el.clientHeight-el.scrollTop), scrollTop:Math.round(el.scrollTop), text:rows[rows.length-1].innerText.slice(0,0)}; };
  window.$modal = (title) => [...document.querySelectorAll('.modal')].find(m=>(m.querySelector('.modal-title')?.innerText||'').includes(title));
  window.$titles = () => [...document.querySelectorAll('.modal .modal-title')].map(t=>t.innerText.trim());
  window.$btn = (root, text) => [...root.querySelectorAll('button')].filter(x=>x.offsetParent!==null).find(x=>x.innerText.trim()===text);
  window.$click = (root, text) => { const b=$btn(root,text); if(!b) throw new Error('没有按钮 '+text); b.click(); };
  window.$type = (el, value) => { if(!el) throw new Error('找不到输入框'); const p=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(p,'value').set.call(el,value); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); };
  window.$input = () => [...document.querySelectorAll('textarea')].find(t=>t.offsetParent!==null && !t.closest('.modal,.drawer-wrapper'));
  window.$drawerOpen = () => { const w=document.querySelector('.drawer-wrapper'); return !!w && cs(w).visibility!=='hidden'; };
  window.$rgb = (c) => { const x=document.createElement('canvas').getContext('2d',{willReadFrequently:true}); x.fillStyle=c; x.fillRect(0,0,1,1); const d=x.getImageData(0,0,1,1).data; return [d[0],d[1],d[2],d[3]/255]; };
  const lum = (c) => { const f=c.slice(0,3).map(v=>{v/=255; return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}); return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2]; };
  window.$contrast = (fg, bg) => { const a=lum(fg), b=lum(bg); return +((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05)).toFixed(2); };
})()
"""


async def open_app(ctx, url, width=1440, height=900, reduce_motion=False):
    page = await cdp.open_page(ctx.cdp_port, url, ctx.shots_dir, width, height)
    if reduce_motion:
        await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    await goto_app(page)
    return page


async def goto_app(page):
    await page.goto("/")
    await page.js(HELPERS)


def labeled(ctx, label):
    """名字带上环境，结果另存一份，用来比较开发和构建。"""
    def check(name, ok, detail=""):
        ctx.check(f"{label} {name}", ok, detail)
        ctx.dom_results.setdefault(label, {})[name] = bool(ok)
    return check


def environments(ctx):
    built = [("构建", ctx.serve_built())]
    return built if ctx.built_only else built + [("开发", ctx.base_url)]


def request(ctx, method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(ctx.api_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            return response.status, dict(response.headers), raw
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def update_settings(ctx, **changes):
    settings = ctx.api("/api/settings")
    settings.update(changes)
    status, _, _ = request(ctx, "PUT", "/api/settings", settings)
    if status != 200:
        raise RuntimeError(f"保存设置失败 {status}")
    return settings


# ---------- 进入会话 ----------
async def enter_chat(ctx, page, key, record=False, settle=1.2):
    """点侧栏的角色和会话。record 时按帧记录最后一条的位置：rAF 里量一次，这一帧画完后再量一次。"""
    chat = ctx.api(f"/api/chats/{ctx.fixtures[key]}")
    character = chat["characterId"]
    title = chat["title"]
    item = f"[...document.querySelectorAll('aside .group.cursor-pointer')].find(e=>e.querySelector('span.truncate')?.innerText.trim()==={json.dumps(title)})"
    marker = f"最后一条开头 {key}"
    if record:
        await page.js(rf"""(() => {{ window.__f=[]; window.__fp=[]; const t0=performance.now(); const at=()=>{{ const rows=$rows(); const last=rows[rows.length-1]; if(!last||!last.innerText.includes({json.dumps(marker)})) return null; return Math.round(last.getBoundingClientRect().top-$s().getBoundingClientRect().top); }};
          const tick=()=>{{ const a=at(); if(a!==null) window.__f.push(a); const c=new MessageChannel(); c.port1.onmessage=()=>{{ const b=at(); if(b!==null) window.__fp.push(b); }}; c.port2.postMessage(0); if(performance.now()-t0<3000) requestAnimationFrame(tick); }}; requestAnimationFrame(tick); }})(); 1""")
    await page.js(f"""document.querySelector('[data-character-id="{character}"]').click()""")
    await page.wait_for(item, 10)
    await page.js(f"{item}.click()")
    await page.wait_for(f"$rows().length && $rows()[$rows().length-1].innerText.includes({json.dumps(marker)})", 15)
    await asyncio.sleep(settle)
    await page.js(cdp.DISMISS)
    await asyncio.sleep(0.2)


# ---------- 弹窗动效 ----------
RECORD_MOTION = r"""(title) => { window.__mf=[]; window.__mfStop=false; window.__mfClose=null; const cs=getComputedStyle;
  const tick=()=>{ const m=$modal(title), t=performance.now(); if(!m) window.__mf.push({t,gone:true}); else { const d=m.querySelector('[role=dialog]'), b=m.querySelector('.modal-backdrop');
    window.__mf.push({t, root:+cs(m).opacity, back:+(+cs(b).opacity).toFixed(3), cont:+(+cs(d).opacity).toFixed(3), bodyH:d.querySelector('.modal-body')?.scrollHeight??null}); }
    if(!window.__mfStop) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }"""


def motion_verdict(frames, closed_at):
    """入场和退场都要能看到中间帧，根元素全程不淡（否则模糊到最后一帧才出现），退场高度不塌。返回不合格的原因。"""
    start = next((i for i, f in enumerate(frames) if not f.get("gone")), None)
    if start is None:
        return ["弹窗没有出现"]
    enter = [f for f in frames[start:] if f["t"] < closed_at and not f.get("gone")]
    leave = [f for f in frames[start:] if f["t"] >= closed_at]
    shown = [f for f in leave if not f.get("gone")]
    reasons = []
    if enter[0]["cont"] >= 0.5 or enter[0]["back"] >= 0.5:
        reasons.append(f"第一帧已经显示 {enter[0]}")
    if len({f["cont"] for f in enter if 0 < f["cont"] < 1}) < 3:
        reasons.append("入场没有中间帧")
    if len({f["back"] for f in enter if 0 < f["back"] < 1}) < 3:
        reasons.append("遮罩入场没有中间帧")
    if enter[-1]["cont"] != 1:
        reasons.append("入场没有走完")
    if any(f["root"] != 1 for f in enter + shown):
        reasons.append("根元素在淡入淡出")
    if len({f["cont"] for f in shown if 0 < f["cont"] < 1}) < 3:
        reasons.append("退场没有中间帧")
    if not leave or not leave[-1].get("gone"):
        reasons.append("退场后没有消失")
    if len({f["bodyH"] for f in shown}) > 1:
        reasons.append("退场时内容高度变了")
    return reasons


async def measure_motion(page, check, name, title, open_js, close_js, ready=None):
    """--transition-normal 拉长到 1 秒按帧采样。"""
    await page.js("document.documentElement.style.setProperty('--transition-normal','1s linear')")
    await page.js(f"({RECORD_MOTION})({json.dumps(title)})")
    await page.js(open_js)
    await page.wait_for(ready or f"$modal({json.dumps(title)})", 10)
    await asyncio.sleep(1.25)
    await page.js(f"window.__mfClose=performance.now(); {close_js}")
    await asyncio.sleep(1.4)
    data = await page.js("(() => { window.__mfStop=true; return {f:window.__mf, c:window.__mfClose}; })()")
    await page.js("document.documentElement.style.removeProperty('--transition-normal')")
    reasons = motion_verdict(data["f"], data["c"])
    check(f"动效 {name}", not reasons, reasons)
    await asyncio.sleep(0.1)


async def settings_open(page):
    await page.js("$click(document, '设置')")
    await page.wait_for("$drawerOpen()", 5)
    await asyncio.sleep(0.8)


# ---------- 核心行为 ----------
async def core_entry(ctx, url, check):
    page = await open_app(ctx, url)
    await enter_chat(ctx, page, "SHORT")
    await enter_chat(ctx, page, "LONG", record=True)
    state = await page.js("$last()")
    check("长消息停在开头", abs(state["top"] - state["pad"]) <= 2 and state["dist"] > 0, state)
    await asyncio.sleep(1.5)
    frames, painted = await page.js("[window.__f, window.__fp]")
    pad = state["pad"]
    check("进入时不闪结尾（画完的帧）", painted and all(abs(x - pad) <= 2 for x in painted), painted[:6])
    if frames and any(abs(x - pad) > 2 for x in frames):
        print(f"    记录：rAF 内量到过未就位的位置，前几帧 {frames[:4]}，画完后 {painted[:4]}")
    await page.shot(f"dom-entry-long-{check.label}")
    await page.js("(() => { const g=document.createElement('div'); g.style.height='260px'; const r=$rows(); r[r.length-1].querySelector('.prose').appendChild(g); })()")
    await asyncio.sleep(0.6)
    grown = await page.js("$last()")
    check("停在开头时内容变高不被拉走", abs(grown["top"] - pad) <= 2 and grown["dist"] > state["dist"], grown)
    await enter_chat(ctx, page, "MID")
    state = await page.js("$last()")
    check("中等长度停在开头", abs(state["top"] - state["pad"]) <= 2 and state["dist"] > 0, state)
    await enter_chat(ctx, page, "SHORT")
    state = await page.js("$last()")
    check("放得下时贴底", state["dist"] <= 2, state)
    await enter_chat(ctx, page, "LONG")
    state = await page.js("$last()")
    check("再次进入仍停在开头", abs(state["top"] - state["pad"]) <= 2 and state["dist"] > 0, state)
    await ctx.close(page)

    page = await open_app(ctx, url)
    await enter_chat(ctx, page, "SHORT", settle=0.6)
    chat = ctx.api("/api/chats/" + ctx.fixtures["LONG"])
    title = chat["title"]
    await page.js(f"""document.querySelector('[data-character-id="{chat['characterId']}"]').click()""")
    item = f"[...document.querySelectorAll('aside .group.cursor-pointer')].find(e=>e.querySelector('span.truncate')?.innerText.trim()==={json.dumps(title)})"
    await page.wait_for(item, 10)
    await page.js(f"{item}.click()")
    await page.wait_for("$rows().length && $rows()[$rows().length-1].innerText.includes('最后一条开头 LONG')", 15)
    await page.wheel(600)
    await asyncio.sleep(0.5)
    a = await page.js("$last()")
    await asyncio.sleep(1.5)
    b = await page.js("$last()")
    check("进入后立刻滚动不被抢", a["top"] == b["top"] and b["top"] < b["pad"] - 100 and b["dist"] > 0, (a, b))
    await ctx.close(page)


SEARCH_INPUT = """document.querySelector('input[aria-label="搜索当前会话"]')"""
SEARCH_STATE = r"""(() => { const el=$s(), r=el.getBoundingClientRect(), m=[...el.querySelectorAll('.message-row--search-target')], box=m[0]?.getBoundingClientRect();
  return {status:document.querySelector('.chat-header-search-panel-inner .text-2xs')?.innerText.trim(), marked:m.length, top:box?Math.round(box.top-r.top):null, pad:Math.round(parseFloat(getComputedStyle(el).paddingTop)),
    bg:m[0]?getComputedStyle(m[0],'::before').backgroundColor:null, shadow:m[0]?getComputedStyle(m[0],'::before').boxShadow:null}; })()"""


async def core_search(ctx, url, check):
    page = await open_app(ctx, url)
    await enter_chat(ctx, page, "LONG")
    await page.js("[...document.querySelectorAll('.header-action-chip')].find(b=>b.innerText.includes('搜索')).click()")
    await page.wait_for(SEARCH_INPUT, 5)
    await asyncio.sleep(0.6)
    await page.js(f"$type({SEARCH_INPUT}, '沙箱检索词'); {SEARCH_INPUT}.focus()")
    await asyncio.sleep(1.0)
    state = await page.js(SEARCH_STATE)
    check("搜索：超过上限显示 300+", state["status"] == "共 300+ 条", state["status"])
    for _ in range(2):
        await page.key("Enter", 13)
        await asyncio.sleep(0.5)
    state = await page.js(SEARCH_STATE)
    check("搜索：回车逐条跳转并计数", state["status"] == "2/300+" and state["marked"] == 1, state)
    check("搜索：目标定位到开头", state["top"] is not None and abs(state["top"] - state["pad"]) <= 2, state)
    check("搜索：目标是中性底色，不发光", state["shadow"] == "none" and str(state["bg"]).endswith("/ 0.08)"), state)
    await page.shot(f"dom-search-{check.label}")
    await page.js("""document.querySelector('button[aria-label="上一个搜索结果"]').click()""")
    await asyncio.sleep(0.5)
    state = await page.js(SEARCH_STATE)
    check("搜索：上一个", state["status"] == "1/300+" and state["marked"] == 1, state)
    await page.js("""document.querySelector('button[aria-label="上一个搜索结果"]').click()""")
    await asyncio.sleep(0.7)
    state = await page.js(SEARCH_STATE)
    check("搜索：从第一条回绕到最后一条，定位准确", state["status"] == "300/300+" and state["marked"] == 1 and abs((state["top"] or 9999) - state["pad"]) <= 2, state)
    chips = await page.js("document.querySelectorAll('[data-search-chip]').length")
    for index in (chips // 2, 5, chips - 1, chips // 3):
        await page.js(f"""document.querySelector('[data-search-chip="{index}"]').click()""")
        trace = []
        for _ in range(16):
            await asyncio.sleep(0.25)
            state = await page.js(SEARCH_STATE)
            trace.append((state["top"] or 9999) - state["pad"])
        print(f"    记录：点第 {index + 1} 张卡片后，目标距开头每 250ms {trace}")
        check(f"搜索：点结果卡片第 {index + 1} 张，定位准确", state["status"] == f"{index + 1}/300+" and state["marked"] == 1 and abs(trace[-1]) <= 2, (chips, state))
    await page.js(f"$type({SEARCH_INPUT}, '最后一条开头 LONG')")
    await asyncio.sleep(1.0)
    state = await page.js(SEARCH_STATE)
    check("搜索：少量结果没有加号", state["status"] == "共 1 条", state["status"])
    await page.js(f"$type({SEARCH_INPUT}, '不可能出现的词zzqq')")
    await asyncio.sleep(1.0)
    state = await page.js(SEARCH_STATE)
    check("搜索：没有结果时说明", state["status"] == "无结果", state["status"])
    await page.js("""document.querySelector('button[aria-label="关闭会话搜索"]').click()""")
    await asyncio.sleep(1.0)
    check("搜索：关闭后清除高亮", (await page.js("document.querySelectorAll('.message-row--search-target').length")) == 0)
    await ctx.close(page)


async def core_delete(ctx, url, check):
    chat_id = ctx.fixtures["MID"]
    messages = lambda: ctx.api(f"/api/chats/{chat_id}")["messages"]
    page = await open_app(ctx, url)
    await enter_chat(ctx, page, "MID")
    # 删倒数第二条，留着带标记的最后一条给后面的检查
    button = "(() => { const r=$rows(); return r[r.length-2].querySelector('.inline-confirm'); })()"
    before = messages()
    target = before[-2]["id"]
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.1)
    armed = await page.js(f"({{t:{button}.innerText.trim(), a:{button}.classList.contains('inline-confirm--armed'), dialog:!!document.querySelector('.app-notify-backdrop')}})")
    check("删除：第一次点击原地变确认，不弹框", armed == {"t": "确认？", "a": True, "dialog": False}, armed)
    check("删除：第一次点击不删除", len(messages()) == len(before))
    await asyncio.sleep(3.3)
    check("删除：3 秒后复原", (await page.js(f"{button}.innerText.trim()")) == "删除")
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.05)
    await page.js(f"{button}.blur()")
    await asyncio.sleep(0.05)
    check("删除：失焦复原", (await page.js(f"{button}.innerText.trim()")) == "删除")
    check("删除：取消后数据没动", len(messages()) == len(before))
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.05)
    await page.js(f"{button}.click()")
    await asyncio.sleep(1.0)
    after = messages()
    check("删除：第二次点击才删除，只删这一条", len(after) == len(before) - 1 and target not in {m["id"] for m in after}, (len(before), len(after)))
    await goto_app(page)
    await enter_chat(ctx, page, "MID")
    check("删除：刷新后最后一条还在", "最后一条开头 MID" in await page.js("$rows()[$rows().length-1].innerText"))
    await ctx.close(page)


async def core_modal(ctx, url, check):
    page = await open_app(ctx, url)
    edit = """document.querySelector('[data-character-id] button[aria-label="编辑角色"]').click()"""
    await measure_motion(page, check, "编辑角色", "编辑角色", edit, """$modal('编辑角色').querySelector('.modal-close').click()""")
    await page.js(edit)
    await page.wait_for("$modal('编辑角色')", 5)
    await asyncio.sleep(0.5)
    await page.js("$click($modal('编辑角色'), '更换头像')")
    await page.wait_for("$modal('设置头像')", 5)
    await asyncio.sleep(0.5)
    check("Esc：打开两层", await page.js("$titles().length") == 2, await page.js("$titles()"))
    await page.key("Escape", 27)
    await asyncio.sleep(0.6)
    check("Esc：第一次只关上面一层", await page.js("$titles().join()") == "编辑角色", await page.js("$titles()"))
    await page.key("Escape", 27)
    await asyncio.sleep(0.6)
    await page.js(cdp.DISMISS)
    await asyncio.sleep(0.3)
    check("Esc：第二次关下面一层", await page.js("$titles().length") == 0, await page.js("$titles()"))
    await settings_open(page)
    await page.key("Escape", 27)
    await asyncio.sleep(0.8)
    check("Esc：关掉设置抽屉", not await page.js("$drawerOpen()"))
    await ctx.close(page)

    page = await open_app(ctx, url, reduce_motion=True)
    await page.js(edit)
    await page.wait_for("$modal('编辑角色')", 5)
    await asyncio.sleep(0.3)
    state = await page.js("(() => { const m=$modal('编辑角色'); return [getComputedStyle(m.querySelector('[role=dialog]')).opacity, getComputedStyle(m.querySelector('.modal-backdrop')).opacity]; })()")
    check("减少动态效果时弹窗能完整显示", state == ["1", "1"], state)
    await ctx.close(page)


async def check_core(ctx):
    """DOM 驱动的核心行为，开发和构建各跑一遍：进入定位、搜索、原地删除、弹窗动效和 Esc"""
    for label, url in environments(ctx):
        check = labeled(ctx, label)
        check.label = "built" if label == "构建" else "dev"
        for part in (core_entry, core_search, core_delete, core_modal):
            try:
                await part(ctx, url, check)
            except Exception as error:
                check(f"{part.__name__} 没有跑完", False, repr(error)[:300])


# ---------- PNG 内嵌卡和 OAuth 弹窗 ----------
def png_bytes(card=None):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    width, height = 64, 64
    raw = b"".join(b"\x00" + bytes((200, 120, 60)) * width for _ in range(height))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    if card:
        out += chunk(b"tEXt", b"chara\x00" + base64.b64encode(json.dumps(card, ensure_ascii=False).encode()))
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


EMBEDDED_CARD = {
    "spec": "chara_card_v2", "spec_version": "2.0",
    "data": {"name": "沙箱内嵌卡", "description": "沙箱内嵌简介", "personality": "沙箱内嵌性格", "scenario": "沙箱内嵌场景",
             "first_mes": "沙箱内嵌首句", "mes_example": "", "system_prompt": "", "alternate_greetings": [], "tags": []},
}
PNG_TITLE = "PNG 内嵌"


async def upload_avatar(page, path):
    """走真实路径：编辑角色 → 更换头像 → 选文件 → 保存头像。停在点保存之前。"""
    await page.js("$click($modal('编辑角色'), '更换头像')")
    await page.wait_for("$modal('设置头像')", 5)
    await asyncio.sleep(0.4)
    await page.set_file("""$modal('设置头像').querySelector('input[type=file]')""", path)
    await page.wait_for("$modal('设置头像').querySelector('.cropper-container img')", 8)
    await asyncio.sleep(0.8)


SAVE_AVATAR = "$click($modal('设置头像'), '保存头像')"


async def wait_png_closed(page):
    await page.wait_for(f"!$modal({json.dumps(PNG_TITLE)})", 6)
    await asyncio.sleep(0.2)


async def modals_png(ctx, url, check, files):
    page = await open_app(ctx, url)
    await page.js("""document.querySelector('[data-character-id] button[aria-label="编辑角色"]').click()""")
    await page.wait_for("$modal('编辑角色')", 5)
    await asyncio.sleep(0.5)

    # 对照：普通 PNG 不该弹确认
    await upload_avatar(page, files["plain"])
    await page.js(SAVE_AVATAR)
    await asyncio.sleep(1.5)
    check("PNG：普通图片不弹确认", not await page.js(f"$modal({json.dumps(PNG_TITLE)})"), await page.js("$titles()"))

    await upload_avatar(page, files["card"])
    await measure_motion(page, check, "PNG 内嵌卡确认", PNG_TITLE, SAVE_AVATAR, f"$modal({json.dumps(PNG_TITLE)}).querySelector('.modal-close').click()")
    await asyncio.sleep(0.3)
    check("PNG：X 关闭后角色编辑还在", await page.js("$titles().join()") == "编辑角色", await page.js("$titles()"))

    first = """[...$modal('编辑角色').querySelectorAll('.settings-field')].find(f=>f.querySelector('.settings-label')?.innerText.trim().startsWith('首句'))?.querySelector('textarea,input')?.value"""
    original = await page.js(first)
    closers = (
        ("Esc", None),
        ("点遮罩", f"$modal({json.dumps(PNG_TITLE)}).querySelector('.modal-backdrop').click()"),
        ("仅使用头像", f"$click($modal({json.dumps(PNG_TITLE)}), '仅使用头像')"),
    )
    for name, closer in closers:
        await upload_avatar(page, files["card"])
        await page.js(SAVE_AVATAR)
        await page.wait_for(f"$modal({json.dumps(PNG_TITLE)})", 8)
        await asyncio.sleep(0.5)
        if name == "Esc":
            text = await page.js(f"$modal({json.dumps(PNG_TITLE)}).innerText")
            check("PNG：弹窗显示检测到的角色名", "沙箱内嵌卡" in text)
            await page.shot(f"dom-png-modal-{check.label}")
            await page.key("Escape", 27)
        else:
            await page.js(closer)
        await wait_png_closed(page)
        check(f"PNG：{name} 只关这一层，内容没被覆盖", await page.js("$titles().join()") == "编辑角色" and await page.js(first) == original, await page.js("$titles()"))

    await upload_avatar(page, files["card"])
    await page.js(SAVE_AVATAR)
    await page.wait_for(f"$modal({json.dumps(PNG_TITLE)})", 8)
    await asyncio.sleep(0.5)
    await page.js(f"$click($modal({json.dumps(PNG_TITLE)}), '覆盖当前编辑')")
    await wait_png_closed(page)
    await asyncio.sleep(0.5)
    check("PNG：确认后覆盖到编辑内容", await page.js(first) == "沙箱内嵌首句", await page.js(first) == original)
    await ctx.close(page)


OAUTH_PROVIDERS = (
    ("openai-chatgpt", "使用 ChatGPT 登录", None),
    ("xai-oauth", "登录", "xAI 应用 Client ID"),
    ("github-copilot", "登录", "GitHub Enterprise"),
)


async def modals_oauth(ctx, url, check):
    template = next(x for x in ctx.api("/api/settings")["apiPresets"] if x.get("presetKind") != "tts")
    added = [{**template, "id": f"ui-check-{provider}", "name": f"沙箱登录 {provider}", "providerId": provider, "apiKey": ""} for provider, _, _ in OAUTH_PROVIDERS]
    original = ctx.api("/api/settings")["apiPresets"]
    update_settings(ctx, apiPresets=original + added)
    try:
        page = await open_app(ctx, url)
        await settings_open(page)
        await page.js("$click(document.querySelector('.drawer-panel'), 'API 预设')")
        await asyncio.sleep(0.8)
        select = lambda name: f"""[...document.querySelectorAll('.drawer-panel [draggable=true]')].find(e=>e.innerText.includes({json.dumps(name)})).click()"""
        for provider, button, field in OAUTH_PROVIDERS:
            await page.js(select(f"沙箱登录 {provider}"))
            await asyncio.sleep(0.6)
            if not await page.js(f"!!$btn(document.querySelector('.drawer-panel'), {json.dumps(button)})"):
                check(f"OAuth {provider}：有登录按钮", False)
                continue
            title = "登录"
            opener = f"$click(document.querySelector('.drawer-panel'), {json.dumps(button)})"
            await measure_motion(page, check, f"OAuth {provider}", title, opener, "$modal('登录').querySelector('.modal-close').click()")
            check(f"OAuth {provider}：X 关闭后抽屉还在", await page.js("$drawerOpen() && !$modal('登录')"))
            await page.js(opener)
            await page.wait_for("$modal('登录')", 6)
            await asyncio.sleep(0.5)
            text = await page.js("$modal('登录').innerText")
            check(f"OAuth {provider}：字段正确", (field is None or field in text) and "开始登录" in text, text[:80])
            await page.shot(f"dom-oauth-{provider}-{check.label}")
            await page.key("Escape", 27)
            await page.wait_for("!$modal('登录')", 5)
            await asyncio.sleep(0.3)
            check(f"OAuth {provider}：Esc 只关弹窗", await page.js("$drawerOpen()"))
            for name, closer in (("点遮罩", "$modal('登录').querySelector('.modal-backdrop').click()"), ("取消", "$click($modal('登录'), '取消')")):
                await page.js(opener)
                await page.wait_for("$modal('登录')", 6)
                await asyncio.sleep(0.4)
                await page.js(closer)
                await page.wait_for("!$modal('登录')", 5)
                await asyncio.sleep(0.2)
                check(f"OAuth {provider}：{name}关闭后抽屉还在", await page.js("$drawerOpen()"))
        started = await page.js("performance.getEntriesByType('resource').filter(e=>e.name.includes('/oauth/start')).length")
        check("OAuth：只开关弹窗不发起登录", started == 0, started)
        await ctx.close(page)
    finally:
        update_settings(ctx, apiPresets=original)


async def check_modals(ctx):
    """PNG 内嵌卡确认和 OAuth 登录弹窗，开发和构建各跑一遍：打开、按帧动效、各种关闭"""
    fixtures = os.path.join(ctx.work, "fixtures")
    os.makedirs(fixtures, exist_ok=True)
    files = {"plain": os.path.join(fixtures, "plain.png"), "card": os.path.join(fixtures, "card.png")}
    with open(files["plain"], "wb") as f:
        f.write(png_bytes())
    with open(files["card"], "wb") as f:
        f.write(png_bytes(EMBEDDED_CARD))
    for label, url in environments(ctx):
        check = labeled(ctx, label)
        check.label = "built" if label == "构建" else "dev"
        for name, part in (("PNG", lambda: modals_png(ctx, url, check, files)), ("OAuth", lambda: modals_oauth(ctx, url, check))):
            try:
                await part()
            except Exception as error:
                check(f"{name} 弹窗没有跑完", False, repr(error)[:300])


def check_dev_built_diff(ctx):
    built, dev = ctx.dom_results.get("构建", {}), ctx.dom_results.get("开发", {})
    if not built or not dev:
        ctx.check("开发和构建都跑过 core 和 modals", False, "要和 core、modals 一起跑，并且不能加 --built-only")
        return
    diff = sorted(name for name in set(built) & set(dev) if built[name] != dev[name])
    only = sorted(set(built) ^ set(dev))
    ctx.check("开发和构建结果一致", not diff and not only, {"不同": diff, "只有一边": only})
    if diff or only:
        for name in diff:
            print(f"    不一致：{name}  构建={'通过' if built[name] else '失败'}  开发={'通过' if dev[name] else '失败'}")


async def check_dev_built(ctx):
    """把 core 和 modals 在开发和构建上的结果逐项比较"""
    check_dev_built_diff(ctx)


# ---------- 主题 ----------
THEME_PROBE = r"""(() => { const cs=getComputedStyle; const root=document.querySelector('[data-theme]');
  const primary=[...document.querySelectorAll('.btn-primary')].find(e=>e.offsetParent!==null); const p=primary?cs(primary):null;
  const main=$input();
  return {theme:root?root.dataset.theme:null, primaryBg:p?$rgb(p.backgroundColor):null, primaryFg:p?$rgb(p.color):null, contrast:p?$contrast($rgb(p.color),$rgb(p.backgroundColor)):null, brand:cs(root||document.documentElement).getPropertyValue('--color-brand').trim(), hasInput:!!main}; })()"""


async def check_themes(ctx):
    """7 个主题各拍主界面、设置和弹窗，背景透明度 30%。主色要互不相同，主按钮文字对比度够。截图另外人工看"""
    url = ctx.serve_built()
    saved = ctx.api("/api/settings")
    seen = {}
    bad = []
    try:
        for theme in THEMES:
            update_settings(ctx, themeId=theme, pageBackgroundOpacity=0.3)
            page = await open_app(ctx, url)
            await enter_chat(ctx, page, "LONG")
            state = await page.js(THEME_PROBE)
            seen[theme] = state["primaryBg"]
            if state["theme"] != theme:
                bad.append((theme, "data-theme", state["theme"]))
            if (state["contrast"] or 0) < 4.5:
                bad.append((theme, "主按钮对比度", state["contrast"]))
            ctx.note(f"主题 {theme}", {"主按钮底色": state["primaryBg"][:3], "主按钮对比度": state["contrast"]})
            await page.shot(f"theme-{theme}-main")
            await settings_open(page)
            await page.shot(f"theme-{theme}-settings")
            await page.key("Escape", 27)
            await asyncio.sleep(0.8)
            await page.js("""document.querySelector('[data-character-id] button[aria-label="编辑角色"]').click()""")
            await page.wait_for("$modal('编辑角色')", 5)
            await asyncio.sleep(0.8)
            await page.shot(f"theme-{theme}-modal")
            await ctx.close(page)
        ctx.check("7 个主题的 data-theme 正确，主按钮对比度不低于 4.5", not bad, bad)
        ctx.check("7 个主题的主色互不相同", len({tuple(x) for x in seen.values()}) == len(THEMES), seen)
    finally:
        update_settings(ctx, themeId=saved.get("themeId"), pageBackgroundOpacity=saved.get("pageBackgroundOpacity"))


# ---------- 窗口尺寸 ----------
OVERFLOW = r"""(() => { const W=innerWidth, H=innerHeight, cs=getComputedStyle; const rootOver=Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)-W;
  const off=[]; let parked=0; for(const e of document.querySelectorAll('body *')){ if(e.closest('svg')&&e.tagName!=='svg') continue; const s=cs(e); if(s.display==='none'||s.visibility==='hidden'||+s.opacity===0) continue; const r=e.getBoundingClientRect(); if(!r.width||!r.height) continue; if(r.right<=W+1&&r.left>=-1) continue; if(r.left>=W-1||r.right<=1) { parked++; continue; }
    let a=e.parentElement, clipped=false; while(a&&a!==document.body){ const o=cs(a).overflowX; if(o!=='visible'){ const ar=a.getBoundingClientRect(); if(ar.right<=W+1&&ar.left>=-1){ clipped=true; break; } } a=a.parentElement; } if(clipped) continue;
    if(s.position==='fixed'&&s.pointerEvents==='none') continue;
    off.push(e.tagName.toLowerCase()+'.'+String(e.className.baseVal??e.className).split(/\s+/).slice(0,3).join('.')+' ['+Math.round(r.left)+','+Math.round(r.right)+']'); if(off.length>=8) break; }
  return {rootOver, off, parked}; })()"""
HIT = r"""(sel) => { const out={}; for(const [name,find] of Object.entries(sel)){ const e=find(); if(!e){ out[name]='缺失'; continue; } const r=e.getBoundingClientRect(); const x=r.left+r.width/2, y=r.top+r.height/2; const t=document.elementFromPoint(x,y);
    out[name]= (x<0||y<0||x>innerWidth||y>innerHeight)?'在窗口外':(t&&(t===e||e.contains(t)||t.contains(e)&&t.tagName==='LABEL'))?'ok':('被遮挡 '+(t?t.tagName.toLowerCase()+'.'+String(t.className.baseVal??t.className).split(/\s+/).slice(0,2).join('.'):'')); } return out; }"""
MAIN_CONTROLS = """({输入框:()=>$input(), 发送:()=>$btn(document,'发送')||[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='发送'), 搜索:()=>[...document.querySelectorAll('.header-action-chip')][0]})"""
MODAL_CONTROLS = """({关闭:()=>[...document.querySelectorAll('.modal .modal-close')].pop(), 底部按钮:()=>[...document.querySelectorAll('.modal .modal-footer button')].pop(), 标题:()=>[...document.querySelectorAll('.modal .modal-title')].pop()})"""


async def viewport_measure(page, name, size, controls, problems):
    state = await page.js(OVERFLOW)
    hits = await page.js(f"({HIT})({controls})") if controls else {}
    bad_hits = {k: v for k, v in hits.items() if v != "ok"}
    if state["rootOver"] > 0 or state["off"] or bad_hits:
        problems.append({"窗口": size, "页面": name, "横向溢出": state["rootOver"], "出界元素": state["off"], "控件": bad_hits})
    return state, hits


async def check_viewports(ctx):
    """1920、1440、1100 和 420 宽：主要页面量 scrollWidth、出界元素和控件是否被挡。先注入错误状态确认量得出来"""
    url = ctx.serve_built()
    page = await open_app(ctx, url, 1440, 900)
    await enter_chat(ctx, page, "LONG")
    await page.js("(() => { const d=document.createElement('div'); d.id='__wide'; d.style.cssText='width:3000px;height:10px;position:relative'; document.body.appendChild(d); })()")
    state = await page.js(OVERFLOW)
    ctx.check("对照：注入超宽元素能量出溢出", state["rootOver"] > 0 and state["off"], state)
    await page.js("document.getElementById('__wide').remove()")
    await page.js("(() => { const d=document.createElement('div'); d.id='__cover'; d.style.cssText='position:fixed;inset:0;z-index:99999'; document.body.appendChild(d); })()")
    hits = await page.js(f"({HIT})({MAIN_CONTROLS})")
    ctx.check("对照：注入遮挡层能量出被挡", all(v.startswith("被遮挡") for v in hits.values()), hits)
    await page.js("document.getElementById('__cover').remove()")
    await ctx.close(page)

    problems = []
    edit = """document.querySelector('[data-character-id] button[aria-label="编辑角色"]').click()"""
    for width, height in ((1920, 1080), (1440, 900), (1100, 700), (420, 800)):
        size = f"{width}x{height}"
        page = await open_app(ctx, url, width, height)
        await enter_chat_any(ctx, page, "LONG")
        await viewport_measure(page, "主界面", size, MAIN_CONTROLS, problems)
        await page.shot(f"viewport-{width}-main")
        if width < 768:
            # 窄屏选完会话侧栏不会自己收起，再量一次收起后的样子
            await page.js("""document.querySelector('[aria-label="切换侧边栏"]').click()""")
            await asyncio.sleep(1.6)
            await viewport_measure(page, "主界面（收起侧栏）", size, MAIN_CONTROLS, problems)
            await page.shot(f"viewport-{width}-main-collapsed")
        await page.js("[...document.querySelectorAll('.header-action-chip')][0].click()")
        await asyncio.sleep(0.8)
        await viewport_measure(page, "会话搜索", size, None, problems)
        await page.shot(f"viewport-{width}-search")
        await page.js("""document.querySelector('button[aria-label="关闭会话搜索"]').click()""")
        await asyncio.sleep(0.9)
        opened_settings = await page.js("!!$btn(document,'设置') || !![...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='设置'||b.getAttribute('aria-label')==='设置')")
        if opened_settings:
            await page.js("""([...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='设置'||b.getAttribute('aria-label')==='设置')).click()""")
            await page.wait_for("$drawerOpen()", 5)
            await asyncio.sleep(0.9)
            for tab in ("全局设置", "API 预设", "当前会话"):
                has = await page.js(f"!![...document.querySelectorAll('.drawer-panel button')].find(b=>b.innerText.trim()==={json.dumps(tab)})")
                if has:
                    await page.js(f"[...document.querySelectorAll('.drawer-panel button')].find(b=>b.innerText.trim()==={json.dumps(tab)}).click()")
                    await asyncio.sleep(0.7)
                    await viewport_measure(page, f"设置 {tab}", size, None, problems)
                    await page.shot(f"viewport-{width}-settings-{tab}")
                else:
                    problems.append({"窗口": size, "页面": f"设置 {tab}", "说明": "找不到这个标签"})
            await page.key("Escape", 27)
            await asyncio.sleep(0.8)
        else:
            problems.append({"窗口": size, "页面": "设置", "说明": "找不到设置按钮"})
        # 窄屏时侧栏可能收起，先确认角色按钮能点到
        await page.js(edit)
        await page.wait_for("$modal('编辑角色')", 5)
        await asyncio.sleep(0.8)
        await viewport_measure(page, "角色编辑弹窗", size, MODAL_CONTROLS, problems)
        await page.shot(f"viewport-{width}-modal")
        await ctx.close(page)
    for row in problems:
        print("    " + json.dumps(row, ensure_ascii=False))
    ctx.check("四种窗口都没有横向溢出、出界和遮挡", not problems, f"{len(problems)} 处")


# ---------- 长会话耗时 ----------
def median(values):
    return round(statistics.median(values)) if values else None


async def timed_open(ctx, page, key, runs=5):
    chat_id = ctx.fixtures[key]
    chat = ctx.api(f"/api/chats/{chat_id}")
    title = chat["title"]
    item = f"[...document.querySelectorAll('aside .group.cursor-pointer')].find(e=>e.querySelector('span.truncate')?.innerText.trim()==={json.dumps(title)})"
    other = "SHORT" if key != "SHORT" else "MID"
    results = []
    for _ in range(runs):
        # 先切到另一个会话：LONG 可能已经是首页会话，直接点它量不到变化
        await enter_chat_any(ctx, page, other)
        # 从点角色开始计时：点角色可能直接进入它最近的会话；没进入的话再点会话条目，只点一次
        result = await page.js(rf"""new Promise(done => {{ performance.clearResourceTimings(); const t0=performance.now(); const before=(()=>{{ const r=$rows(); return r.length?r[r.length-1].innerText:''; }})(); document.querySelector('[data-character-id="{chat['characterId']}"]').click(); let clicked=false; const pick=()=>{{ if(clicked) return; const it={item}; if(it&&!it.classList.contains('bg-brand-a10')){{ clicked=true; it.click(); }} }}; let longest=0, prev=t0, shown=null; const tick=()=>{{ pick(); const now=performance.now(); longest=Math.max(longest,now-prev); prev=now; const r=$rows(); const last=r[r.length-1]; if(shown===null&&last&&last.innerText!==before){{ const el=$s(); const top=last.getBoundingClientRect().top-el.getBoundingClientRect().top; if(Math.abs(top-parseFloat(getComputedStyle(el).paddingTop))<=2||el.scrollHeight-el.clientHeight-el.scrollTop<=2) shown=now-t0; }} if(shown!==null||now-t0>15000){{ const api=performance.getEntriesByType('resource').find(e=>e.name.endsWith('/api/chats/'+{json.dumps(chat_id)})); done({{shown,longest,api:api?api.duration:null}}); }} else requestAnimationFrame(tick); }}; requestAnimationFrame(tick); }})""")
        results.append(result)
        await asyncio.sleep(0.6)
    return results


async def check_long_chat(ctx):
    """长会话：打开、发送、保存的耗时。软件渲染和模拟模型下的数字，只能看量级"""
    url = ctx.serve_built()
    ctx.mock_state.tps = 1500
    ctx.mock_state.fault = None
    page = await open_app(ctx, url)
    long_id = ctx.fixtures["LONG"]
    long_chat = ctx.api(f"/api/chats/{long_id}")
    count = len(long_chat["messages"])
    path = next(iter(glob.glob(os.path.join(ctx.data_dir, "chats", "**", long_id, "chat.json"), recursive=True)), None)
    size_kb = round(os.path.getsize(path) / 1024) if path else None
    ctx.check("长会话不少于 320 条", count >= 320, count)
    ctx.note("长会话规模", {"消息数": count, "chat.json KB": size_kb})

    for key in ("LONG",):
        rows = await timed_open(ctx, page, key)
        shown = [r["shown"] for r in rows if r["shown"] is not None]
        ctx.note(f"打开 {key}（点击到最后一条就位，5 次）", {"中位 ms": median(shown), "最大 ms": round(max(shown)) if shown else None, "接口中位 ms": median([r["api"] for r in rows if r["api"]]), "最长帧中位 ms": median([r["longest"] for r in rows])})
        ctx.check(f"打开 {key} 量到了数字", len(shown) == len(rows), rows[:2])

    await enter_chat(ctx, page, "LONG")
    sends = []
    for index in range(3):
        text = f"沙箱耗时探针 {index}"
        await page.js(f"""$type($input(), {json.dumps(text)})""")
        await asyncio.sleep(0.2)
        result = await page.js(rf"""new Promise(done => {{ performance.clearResourceTimings(); const t0=performance.now(); let user=null, first=null, frames=0, slow=0, longest=0, prev=t0; [...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='发送'&&b.offsetParent!==null).click();
          const tick=()=>{{ const now=performance.now(); const gap=now-prev; prev=now; frames++; longest=Math.max(longest,gap); if(gap>50) slow++; const r=$rows(); const texts=r.slice(-2).map(x=>x.innerText); if(user===null&&texts.some(t=>t.includes({json.dumps(text)}))) user=now-t0; if(first===null&&r.length&&r[r.length-1].innerText.includes('他把最后一笼包子')&&r[r.length-2]?.innerText.includes({json.dumps(text)})) first=now-t0; if(first!==null&&(r[r.length-1].innerText.match(/收音机的声音调小/g)||[]).length>=2){{ done({{user,first,done:now-t0,frames,slow,longest}}); return; }} if(now-t0>30000){{ done({{user,first,done:null,frames,slow,longest}}); return; }} requestAnimationFrame(tick); }}; requestAnimationFrame(tick); }})""")
        await asyncio.sleep(1.5)
        saved = ctx.api(f"/api/chats/{long_id}")["messages"]
        ok = result["done"] is not None and any(m.get("content") == text for m in saved[-2:]) and "收音机" in str(saved[-1].get("content"))
        ctx.check(f"发送第 {index + 1} 条写回后端", ok, (result, len(saved)))
        sends.append(result)
        await page.js(cdp.DISMISS)
    ctx.note("发送（3 次）", {"用户消息出现 ms": [round(s["user"] or -1) for s in sends], "首字出现 ms": [round(s["first"] or -1) for s in sends], "流完 ms": [round(s["done"] or -1) for s in sends], "超过 50ms 的帧": [s["slow"] for s in sends], "最长帧 ms": [round(s["longest"]) for s in sends]})
    await page.shot("long-send")

    # 保存：界面上编辑倒数第二条再点仅保存，量保存接口和弹窗收起
    saves = []
    for index in range(3):
        await page.js("(() => { const r=$rows(); const row=r[r.length-2]; $click(row, '编辑'); })()")
        await page.wait_for("$modal('编辑消息')", 5)
        await asyncio.sleep(0.5)
        await page.js(f"""$type($modal('编辑消息').querySelector('textarea'), {json.dumps(f"沙箱保存探针 {index}")})""")
        await asyncio.sleep(0.2)
        result = await page.js(r"""new Promise(done => { performance.clearResourceTimings(); const t0=performance.now(); $click($modal('编辑消息'), '仅保存'); const tick=()=>{ const put=performance.getEntriesByType('resource').find(e=>/\/messages\//.test(e.name)||/\/api\/chats\/[^/]+$/.test(e.name)); const open=!!$modal('编辑消息'); if(put&&!open){ done({api:put.duration, ui:performance.now()-t0, url:put.name.replace(/.*\/api/,'/api').replace(/[0-9a-f-]{16,}/g,':id')}); return; } if(performance.now()-t0>15000){ done({api:null,ui:null,open}); return; } requestAnimationFrame(tick); }; requestAnimationFrame(tick); })""")
        saves.append(result)
        await asyncio.sleep(0.6)
    saved = ctx.api(f"/api/chats/{long_id}")["messages"]
    ctx.check("保存写回后端", any(m.get("content") == "沙箱保存探针 2" for m in saved[-3:]), saves)
    ctx.note("保存（编辑消息，3 次）", {"接口 ms": [round(s["api"] or -1) for s in saves], "到弹窗收起 ms": [round(s["ui"] or -1) for s in saves], "接口": saves[0].get("url")})

    # 接口单独测，排除前端
    message = saved[-2]
    timings = []
    for index in range(5):
        start = asyncio.get_running_loop().time()
        status, _, _ = await asyncio.to_thread(request, ctx, "PUT", f"/api/chats/{long_id}/messages/{message['id']}", {"role": message["role"], "content": f"沙箱保存探针接口 {index}"})
        timings.append((asyncio.get_running_loop().time() - start) * 1000)
    ctx.check("保存接口单测可用", status == 200, status)
    ctx.note("保存接口单测（5 次）", {"中位 ms": median(timings), "最大 ms": round(max(timings))})

    # 冷启动：刷新后长会话排在最前，量到最后一条就位
    await page.send("Page.addScriptToEvaluateOnNewDocument", source=r"""(() => { const t=setInterval(()=>{ const c=[...document.querySelectorAll('.max-w-4xl.mx-auto')].find(x=>x.querySelector(':scope > .group')); if(c){ window.__coldRows=performance.now(); clearInterval(t); } },16); })()""")
    colds = []
    for _ in range(3):
        await page.send("Page.navigate", url=url + "/")
        await page.wait_for("document.readyState === 'complete'")
        await page.wait_for("window.__coldRows", 20)
        colds.append(await page.js("window.__coldRows"))
        await asyncio.sleep(0.8)
    ctx.note("冷启动到消息出现（3 次）", {"ms": [round(x) for x in colds]})
    ctx.check("冷启动量到了数字", len(colds) == 3, colds)
    await page.js(HELPERS)
    await ctx.close(page)


# ---------- 错误路径 ----------
ERROR_ITEMS = r"""[...document.querySelectorAll('code.font-mono')].filter(c=>c.parentElement.innerText.startsWith('requestId')).map(c=>{ const box=c.closest('.surface-panel'); return {requestId:c.innerText.trim(), title:box?.querySelector('.font-semibold')?.innerText.trim(), message:box?.querySelector('pre')?.innerText.trim(), suggestion:[...(box?.querySelectorAll('p')||[])].map(p=>p.innerText).find(t=>t.startsWith('建议操作'))||null}; })"""
ERROR_ANY = r"""[...document.querySelectorAll('button[aria-label="关闭错误提示"]')].map(b=>{ const box=b.closest('.surface-panel'); return {title:box?.querySelector('.font-semibold')?.innerText.trim(), message:box?.querySelector('pre')?.innerText.trim(), hasId:box?.innerText.includes('requestId')}; })"""


# 断连接时，提示里出现其中任何一个就算说明了“连上后中途断开”
TRANSPORT_WORDS = ("中断", "断开", "中途", "断流", "意外结束", "提前结束", "未完整", "不完整", "截断", "interrupted", "disconnect", "reset", "aborted", "incomplete")
STREAM_HALF = {"stream_error": "流里出错之前的半句", "stream_reset": "断流之前的半句"}


async def send_in_chat(page, text):
    await page.js(f"""$type($input(), {json.dumps(text)})""")
    await asyncio.sleep(0.2)
    await page.js("[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='发送'&&b.offsetParent!==null).click()")


async def check_errors(ctx):
    """错误路径：模拟上游返回错误，界面错误栈要有 requestId，用户消息不丢。先确认没有错误时不会出现"""
    url = ctx.serve_built()
    state = ctx.mock_state
    state.tps = 1500
    chat_id = ctx.fixtures["SHORT"]
    page = await open_app(ctx, url)
    await enter_chat_any(ctx, page, "SHORT")

    state.fault = None
    await send_in_chat(page, "沙箱错误路径 对照")
    for _ in range(40):
        await asyncio.sleep(0.5)
        last = ctx.api(f"/api/chats/{chat_id}")["messages"][-1]
        if "收音机" in str(last.get("content")):
            break
    await asyncio.sleep(0.8)
    errors = await page.js(ERROR_ANY)
    ctx.check("对照：上游正常时错误栈是空的", not errors and "收音机" in str(last.get("content")), errors)

    faults = {"http401": "鉴权失败", "http429": "限流", "http500": "上游 500", "stream_error": "流内错误", "stream_reset": "流中断连接"}
    for fault, name in faults.items():
        state.fault = fault
        before = ctx.api(f"/api/chats/{chat_id}")["messages"]
        text = f"沙箱错误路径 {fault}"
        await send_in_chat(page, text)
        try:
            await page.wait_for(f"({ERROR_ANY}).length > 0", 25)
        except TimeoutError:
            ctx.check(f"{name}：错误进入错误栈", False, "25 秒内没有出现")
            state.fault = None
            await page.shot(f"error-{fault}-none")
            await goto_app(page)
            await enter_chat_any(ctx, page, "SHORT")
            continue
        await asyncio.sleep(1.0)
        items = await page.js(ERROR_ITEMS)
        anything = await page.js(ERROR_ANY)
        ctx.check(f"{name}：错误栈里有 requestId", bool(items) and all(re.fullmatch(r"[\w-]{6,}", x["requestId"]) for x in items), anything)
        await page.shot(f"error-{fault}")
        request_id = items[0]["requestId"] if items else None
        ctx.note(f"错误 {fault}", {"标题": items[0]["title"] if items else None, "提示": (items[0]["message"] if items else "")[:120], "建议": items[0]["suggestion"] if items else None})
        visible = await page.js("document.body.innerText")
        ctx.secret_ui[fault] = "sandbox-dummy" in visible
        ctx.check(f"{name}：界面不显示回显的密钥", "sandbox-dummy" not in visible)
        messages = ctx.api(f"/api/chats/{chat_id}")["messages"]
        ctx.check(f"{name}：用户消息写回后端，只有一条", sum(m.get("content") == text for m in messages) == 1, [m.get("role") for m in messages[-3:]])
        ctx.check(f"{name}：界面上用户消息还在", await page.js(f"$rows().slice(-3).some(r=>r.innerText.includes({json.dumps(text)}))"))
        tail = [m for m in messages[len(before):]]
        ctx.note(f"错误 {fault} 之后新增的消息", [{"role": m.get("role"), "空": not str(m.get("content") or "").strip()} for m in tail])
        if fault in STREAM_HALF:
            panels = " ".join(" ".join(str(x.get(k) or "") for k in ("title", "message")) for x in anything)
            panels += " " + " ".join(str(x.get("suggestion") or "") for x in items)
            ctx.check(f"{name}：保留了半句", any(m.get("role") == "assistant" and STREAM_HALF[fault] in str(m.get("content")) for m in tail), [m.get("role") for m in tail])
            if fault == "stream_error":
                upstream = state.stream_error_text
                in_panel = upstream in panels
                in_page = upstream in visible
                ctx.note("流内错误：上游原文出现的位置", {"错误栈": in_panel, "页面任意位置": in_page})
                ctx.check(f"{name}：错误提示里有上游原文", in_panel or in_page, panels[:160])
            else:
                words = [w for w in TRANSPORT_WORDS if w in panels.lower()]
                ctx.note("断连接：命中的关键词", words)
                ctx.check(f"{name}：提示说明是传输中断", bool(words), panels[:160])
                ctx.check(f"{name}：提示不说成无法连接", "无法连接" not in panels, panels[:160])
        if request_id:
            hits = 0
            for path in glob.glob(os.path.join(ctx.data_dir, "http_log", "*.jsonl")):
                with open(path, encoding="utf-8", errors="ignore") as f:
                    hits += sum(request_id in line for line in f)
            ctx.note(f"错误 {fault} 的 requestId 在 HTTP 日志里出现", hits)
        state.fault = None
        await page.js("""[...document.querySelectorAll('button[aria-label="关闭错误提示"]')].forEach(b=>b.click())""")
        await asyncio.sleep(0.5)
        await goto_app(page)
        await enter_chat_any(ctx, page, "SHORT")
        ctx.check(f"{name}：刷新后用户消息还在", await page.js(f"$rows().slice(-3).some(r=>r.innerText.includes({json.dumps(text)}))"))
        if fault == "http500":
            # 上游恢复后，不重新打字就能续上，用户消息不重复
            primary = await page.js("""[...document.querySelectorAll('button')].filter(b=>b.offsetParent!==null).map(b=>b.innerText.trim()).find(t=>t==='继续轮次'||t==='发送')""")
            ctx.note("错误后主按钮", primary)
            await page.js(f"$click(document, {json.dumps(primary)})")
            for _ in range(40):
                await asyncio.sleep(0.5)
                messages = ctx.api(f"/api/chats/{chat_id}")["messages"]
                if "收音机" in str(messages[-1].get("content")):
                    break
            resumed = "收音机" in str(messages[-1].get("content"))
            ctx.note("错误后不打字直接点主按钮能否续上", resumed)
            if not resumed:
                # 单聊里最后一条是用户消息时，重试的路径是编辑这条再“保存并发送”
                await page.js(f"(() => {{ const r=$rows().filter(x=>x.innerText.includes({json.dumps(text)})).pop(); $click(r, '编辑'); }})()")
                await page.wait_for("$modal('编辑消息')", 5)
                await asyncio.sleep(0.4)
                await page.js("$click($modal('编辑消息'), '保存并发送')")
                for _ in range(40):
                    await asyncio.sleep(0.5)
                    messages = ctx.api(f"/api/chats/{chat_id}")["messages"]
                    if "收音机" in str(messages[-1].get("content")):
                        break
            ctx.check(f"{name}：恢复后能重试（编辑后保存并发送），用户消息不重复", "收音机" in str(messages[-1].get("content")) and sum(m.get("content") == text for m in messages) == 1, [m.get("role") for m in messages[-3:]])
    await ctx.close(page)

    # REST：错误信封和响应头
    status, headers, raw = request(ctx, "GET", "/api/chats/does-not-exist-ui-check")
    body = json.loads(raw or b"{}")
    header_id = next((v for k, v in headers.items() if k.lower() == "x-request-id"), None)
    ctx.check("REST 错误带 requestId，和响应头一致", status == 404 and body.get("requestId") and body.get("requestId") == header_id, (status, list(body)))
    status, headers, raw = request(ctx, "PUT", "/api/settings", {"themeId": 123, "apiPresets": "错误类型"})
    body = json.loads(raw or b"{}")
    ctx.check("REST 校验错误带 requestId", status >= 400 and body.get("requestId"), (status, list(body)))

    # REST 进错误栈：会话在别处被删掉后再发送，发送前就失败，走的是普通 JSON 错误，不是 SSE
    source = ctx.api(f"/api/chats/{chat_id}")
    status, _, raw = request(ctx, "POST", "/api/chats", {"characterId": source["characterId"], "title": "沙箱 REST 错误"})
    created = json.loads(raw)
    ctx.check("建临时会话", status == 200, status)
    page = await open_app(ctx, url)
    await page.js(f"""document.querySelector('[data-character-id="{source['characterId']}"]').click()""")
    item = """[...document.querySelectorAll('aside .group.cursor-pointer')].find(e=>e.querySelector('span.truncate')?.innerText.trim()==='沙箱 REST 错误')"""
    await page.wait_for(item, 10)
    await page.js(f"{item}.click()")
    await asyncio.sleep(1.5)
    await page.js(cdp.DISMISS)
    request(ctx, "DELETE", f"/api/chats/{created['id']}")
    await send_in_chat(page, "沙箱错误路径 REST")
    try:
        await page.wait_for(f"({ERROR_ANY}).length > 0", 10)
        await asyncio.sleep(0.5)
        items = await page.js(ERROR_ITEMS)
        anything = await page.js(ERROR_ANY)
        ctx.check("REST 错误进入错误栈，有 requestId", bool(items), anything)
        await page.shot("error-rest")
        ctx.note("错误 REST", {"标题": anything[0]["title"], "提示": str(anything[0]["message"])[:120], "有 requestId": anything[0]["hasId"]})
    except TimeoutError:
        ctx.check("REST 错误进入错误栈，有 requestId", False, "10 秒内没有出现")
        await page.shot("error-rest-none")
    draft = await page.js("$input()?.value")
    rows = await page.js("$rows().some(r=>r.innerText.includes('沙箱错误路径 REST'))")
    ctx.check("REST 错误：用户的话还在输入框或消息列表里", draft == "沙箱错误路径 REST" or rows, (draft == "沙箱错误路径 REST", rows))
    ctx.check("REST 错误：没有未捕获的异常", not page.exceptions, [x[:80] for x in page.exceptions[:2]])
    await cdp.close_page(ctx.cdp_port, page)


async def enter_chat_any(ctx, page, key):
    """最后一条可能已经不是带标记的那条，只等列表出现。"""
    chat = ctx.api(f"/api/chats/{ctx.fixtures[key]}")
    title = chat["title"]
    item = f"[...document.querySelectorAll('aside .group.cursor-pointer')].find(e=>e.querySelector('span.truncate')?.innerText.trim()==={json.dumps(title)})"
    await page.js(f"""document.querySelector('[data-character-id="{chat['characterId']}"]').click()""")
    await page.wait_for(item, 10)
    await page.js(f"{item}.click()")
    await page.wait_for("$rows().length > 0", 15)
    await asyncio.sleep(1.2)
    await page.js(cdp.DISMISS)
    await asyncio.sleep(0.2)


# ---------- 密钥扫描 ----------
SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|tvly-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{12,}|AIza[A-Za-z0-9_-]{20,}|xai-[A-Za-z0-9]{12,}|Bearer\s+[A-Za-z0-9._-]{16,}|eyJ[A-Za-z0-9_-]{20,}\.)")


def scan_text(text, real_secrets):
    return {
        "探针 sandbox-dummy": text.count("sandbox-dummy"),
        "探针 sk-": text.count(KEY_PROBE),
        "疑似密钥格式": len(SECRET_VALUE.findall(text)) - text.count(KEY_PROBE),
        "真实密钥原文": sum(secret in text for secret in real_secrets),
    }


def scan_blob(name, blob, real_secrets, out):
    """zip 拆开逐个扫，其他一律按文本扫。只记录文件名和次数，不记录内容。"""
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for member in archive.namelist():
                scan_blob(f"{name}!{member}", archive.read(member), real_secrets, out)
        return
    hits = scan_text(blob.decode("utf-8", errors="ignore"), real_secrets)
    if any(hits.values()):
        out[name] = {k: v for k, v in hits.items() if v}


def probe_places(paths):
    """探针出现在 HTTP 日志记录的哪个字段，只给字段路径，不给内容。"""
    places = {}

    def walk(node, trail):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, trail + [str(key)])
        elif isinstance(node, list):
            for value in node:
                walk(value, trail)
        elif isinstance(node, str):
            for probe in ("sandbox-dummy", KEY_PROBE):
                if probe in node:
                    name = ".".join(trail) + ("" if probe == "sandbox-dummy" else " " + KEY_PROBE)
                    places[name] = places.get(name, 0) + 1

    for path in paths:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    walk(json.loads(line), [])
                except ValueError:
                    continue
    return places


def scan_paths(paths, root, real_secrets):
    out = {}
    for path in paths:
        with open(path, "rb") as f:
            scan_blob(os.path.relpath(path, root).replace("\\", "/"), f.read(), real_secrets, out)
    return out


async def check_secrets(ctx):
    """日志、HTTP 日志和导出里没有明文密钥。先证明探针确实发出去了，也证明扫描器扫得到"""
    state = ctx.mock_state
    url = ctx.serve_built()
    # 换一个符合真实格式的探针发一轮，上游还把它回显回来
    settings = ctx.api("/api/settings")
    presets = settings["apiPresets"]
    changed = [{**p, "apiKey": KEY_PROBE} if p.get("presetKind") != "tts" else p for p in presets]
    update_settings(ctx, apiPresets=changed)
    state.seen.clear()
    page = await open_app(ctx, url)
    await enter_chat_any(ctx, page, "SHORT")
    state.fault = "http401"
    await send_in_chat(page, "沙箱密钥探针 上游回显")
    await page.wait_for(f"({ERROR_ANY}).length > 0", 25)
    await asyncio.sleep(1.0)
    visible = await page.js("document.body.innerText")
    ctx.check("回显真实格式密钥：界面看不到", KEY_PROBE not in visible)
    state.fault = None
    await page.js("""[...document.querySelectorAll('button[aria-label="关闭错误提示"]')].forEach(b=>b.click())""")
    await asyncio.sleep(0.5)
    await goto_app(page)
    await enter_chat_any(ctx, page, "SHORT")
    await send_in_chat(page, "沙箱密钥探针 正常")
    await asyncio.sleep(4)
    await ctx.close(page)
    sent = [x["auth"] for x in state.seen]
    ctx.check("对照：探针确实发给了上游", any(KEY_PROBE in x for x in sent), len(sent))

    exports = os.path.join(ctx.work, "exports")
    os.makedirs(exports, exist_ok=True)
    def fetch(name, path):
        status, _, raw = request(ctx, "GET", path)
        with open(os.path.join(exports, name), "wb") as f:
            f.write(raw)
        return status
    chat = ctx.api(f"/api/chats/{ctx.fixtures['SHORT']}")
    statuses = {
        "chat.txt": fetch("chat.txt", f"/api/chats/{chat['id']}/export?format=txt"),
        "chat.json": fetch("chat.json", f"/api/chats/{chat['id']}/export?format=json"),
        "character.json": fetch("character.json", f"/api/characters/{chat['characterId']}/export"),
        "backup-basic.zip": fetch("backup-basic.zip", "/api/settings/backup?scope=basic"),
        "backup-with_characters.zip": fetch("backup-with_characters.zip", "/api/settings/backup?scope=with_characters"),
        "backup-with_chats.zip": fetch("backup-with_chats.zip", "/api/settings/backup?scope=with_chats"),
        "http-log-list.json": fetch("http-log-list.json", "/api/http-log?minutes=30&limit=2000"),
    }
    ctx.check("导出接口都成功", all(x == 200 for x in statuses.values()), statuses)

    settings_path = os.path.join(ctx.data_dir, "settings.json")
    known = scan_paths([settings_path], ctx.data_dir, set())
    ctx.check("对照：扫描器能在 settings.json 里扫到探针", known.get("settings.json", {}).get("探针 sk-", 0) > 0, known)

    http_logs = glob.glob(os.path.join(ctx.data_dir, "http_log", "*.jsonl"))
    records = 0
    masked = 0
    for path in http_logs:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                records += 1
                masked += '"***"' in line
    ctx.check("对照：HTTP 日志有记录，且有被脱敏的鉴权头", records > 0 and masked > 0, (records, masked))

    def show(name, hits):
        print(f"    {name}：{json.dumps(hits, ensure_ascii=False) if hits else '无'}")

    logs = scan_paths([ctx.log_path], ctx.work, ctx.real_secrets)
    show("服务日志", logs)
    ctx.check("服务日志没有明文密钥", not logs, logs)
    other_logs = [p for p in glob.glob(os.path.join(ctx.data_dir, "**", "*.log"), recursive=True)]
    other = scan_paths(other_logs, ctx.data_dir, ctx.real_secrets)
    show("数据目录其他日志", other)
    ctx.check("数据目录其他日志没有明文密钥", not other, other)
    http = scan_paths(http_logs, ctx.data_dir, ctx.real_secrets)
    show("HTTP 日志", http)
    places = probe_places(http_logs)
    hosts = {}
    for path in http_logs:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    host = urllib.parse.urlsplit(json.loads(line).get("url") or "").netloc
                except ValueError:
                    continue
                hosts[host] = hosts.get(host, 0) + 1
    ctx.note("HTTP 日志里的出站主机和次数（沙箱应只连模拟上游）", hosts)
    ctx.note("HTTP 日志里探针出现的字段", places)
    ctx.check("HTTP 日志：请求头和请求体没有明文密钥", not [k for k in places if k.startswith("request")], places)
    ctx.check("HTTP 日志：上游回显 sk- 格式的密钥被脱敏", not [k for k in places if KEY_PROBE in k], places)
    ctx.check("HTTP 日志：上游回显其他格式的密钥也不留明文", not [k for k in places if not k.startswith("request")], places)
    plain_exports = [os.path.join(exports, name) for name in statuses if not name.startswith("backup") and name != "http-log-list.json"]
    plain = scan_paths(plain_exports, exports, ctx.real_secrets)
    show("会话和角色导出", plain)
    ctx.check("会话和角色导出没有明文密钥", not plain, plain)
    backups = scan_paths([os.path.join(exports, name) for name in statuses if name.startswith("backup")], exports, ctx.real_secrets)
    show("设置备份", backups)
    ctx.check("设置备份没有明文密钥", not backups, list(backups)[:6])

    # 整个沙箱不能有真实密钥原文，否则上面的扫描都不可信
    leftovers = []
    for root, _, files in os.walk(ctx.work):
        if os.path.join(ctx.work, "dist") in root or os.path.join(ctx.work, "shots") in root:
            continue
        for name in files:
            with open(os.path.join(root, name), "rb") as f:
                blob = f.read().decode("utf-8", errors="ignore")
            if any(secret in blob for secret in ctx.real_secrets):
                leftovers.append(os.path.relpath(os.path.join(root, name), ctx.work).replace("\\", "/"))
    ctx.note("沙箱来源里识别出的真实密钥字段数", len(ctx.real_secrets))
    ctx.check("整个沙箱没有真实密钥原文", not leftovers, leftovers[:6])
    update_settings(ctx, apiPresets=presets)
