"""回归检查本体。每个 check_xxx 独立开页面，顺序见文件末尾的 CHECKS。"""
import asyncio
import glob
import json
import os
import urllib.request

import cdp
import dom_checks

C = "__chat().setupState"
D = "__drawer().setupState"
UI = "__ui()"
CLOSE_LAST = "[...document.querySelectorAll('.modal .modal-close')].filter(e=>e.offsetParent!==null).pop().click()"

# 最后一条消息所在行相对滚动区的位置
LAST_ROW = r"""(() => { const el=__chat().setupState.messageListRef.scrollRef; const r=el.getBoundingClientRect();
  const rows=[...el.querySelector('.max-w-4xl').children].filter(x=>x.classList.contains('group')); const last=rows[rows.length-1]; const lr=last.getBoundingClientRect();
  return {top:Math.round(lr.top-r.top), pad:Math.round(parseFloat(getComputedStyle(el).paddingTop)), rowH:Math.round(lr.height), dist:Math.round(el.scrollHeight-el.clientHeight-el.scrollTop), scrollTop:Math.round(el.scrollTop)}; })()"""
DIST = "(() => { const el=__chat().setupState.messageListRef.scrollRef; return Math.round(el.scrollHeight-el.clientHeight-el.scrollTop); })()"
GROW_LAST = """(() => { const el=__chat().setupState.messageListRef.scrollRef; const rows=[...el.querySelector('.max-w-4xl').children].filter(x=>x.classList.contains('group')); const g=document.createElement('div'); g.style.height='260px'; rows[rows.length-1].querySelector('.prose').appendChild(g); })()"""


def set_input(selector, value):
    return f"""(() => {{ const el={selector}; if(!el) throw new Error('找不到输入框 '+{json.dumps(selector[:60])}); const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el,{json.dumps(value)}); el.dispatchEvent(new Event('input',{{bubbles:true}})); el.dispatchEvent(new Event('change',{{bubbles:true}})); }})()"""


def field(label, tag="input,textarea"):
    return f"""[...document.querySelectorAll('.modal .settings-field')].filter(f=>f.offsetParent!==null).reverse().find(f=>f.querySelector('.settings-label')?.innerText.trim().startsWith({json.dumps(label)}))?.querySelector({json.dumps(tag)})"""


def switch(label):
    return field(label, "[role=switch]")


class Context:
    def __init__(self, base_url, api_url, cdp_port, shots_dir, fixtures, mock_state, serve_built, work=None, data_dir=None, log_path=None, real_secrets=(), built_only=False):
        self.serve_built = serve_built
        self.built_dir = None
        self.work = work
        self.data_dir = data_dir
        self.log_path = log_path
        self.real_secrets = real_secrets
        self.built_only = built_only
        self.dom_results = {}
        self.secret_ui = {}
        self.notes = []
        self.base_url = base_url
        self.api_url = api_url
        self.cdp_port = cdp_port
        self.shots_dir = shots_dir
        self.fixtures = fixtures
        self.mock_state = mock_state
        self.results = []

    def check(self, name, ok, detail=""):
        self.results.append((name, bool(ok)))
        print(("  通过  " if ok else "  失败  ") + name + (f"  {str(detail)[:200]}" if not ok or detail == "" else ""))

    def note(self, name, value):
        """记录测量值，不判断对错。"""
        self.notes.append((name, value))
        print(f"  记录  {name}：{json.dumps(value, ensure_ascii=False)}")

    def api(self, path):
        return json.load(urllib.request.urlopen(self.api_url + path))

    async def page(self, width=1440, height=900, reduce_motion=False):
        page = await cdp.open_page(self.cdp_port, self.base_url, self.shots_dir, width, height)
        if reduce_motion:
            await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        await page.goto("/")
        return page

    async def close(self, page):
        self.check("页面没有报错", not page.exceptions, page.exceptions[:2])
        await cdp.close_page(self.cdp_port, page)

    async def enter(self, page, chat_id, wait=1.8):
        await page.js(f"void {C}.selectChat({{id:{json.dumps(chat_id)}}}); 1")
        await asyncio.sleep(wait)
        await page.js(cdp.DISMISS)
        await asyncio.sleep(0.2)

    async def open_settings(self, page, tab="global"):
        await page.js(f"{UI}.requestOpenSettings('{tab}')")
        await asyncio.sleep(1.2)

    async def expand_appearance(self, page):
        await page.js("""(() => { const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>x.innerText.includes('外观与数据')); if(b.getAttribute('aria-expanded')!=='true') b.click(); })()""")
        await asyncio.sleep(0.5)


async def click_footer(page, text):
    await page.js(f"""(() => {{ const ms=[...document.querySelectorAll('.modal')]; const m=ms[ms.length-1]; const b=[...m.querySelectorAll('.modal-footer button')].find(x=>x.innerText.trim().includes({json.dumps(text)})); if(!b) throw new Error('没有按钮 '+{json.dumps(text)}); b.click(); }})()""")
    await asyncio.sleep(0.8)


async def motion(ctx, page, name, opener, closer):
    """拉长动画按帧量：遮罩和内容淡入淡出，根元素不淡（否则模糊到最后一帧才出现），退场高度不塌。"""
    probe = """(() => { const r=[...document.querySelectorAll('.modal, .fixed.inset-0')].filter(e=>!e.classList.contains('drawer-wrapper')&&e.querySelector('[role=dialog]')); const m=r[r.length-1]; if(!m) return {gone:true}; const d=m.querySelector('[role=dialog]'), b=m.firstElementChild; return {root:+getComputedStyle(m).opacity, back:+(+getComputedStyle(b).opacity).toFixed(2), cont:+(+getComputedStyle(d).opacity).toFixed(2), bodyH:d.querySelector('.modal-body')?.scrollHeight ?? null}; })()"""
    await page.js("document.documentElement.style.setProperty('--transition-normal','1s linear')")
    await page.js(opener)
    await asyncio.sleep(0.15)
    enter0 = await page.js(probe)
    await asyncio.sleep(1.1)
    enter1 = await page.js(probe)
    await page.js(closer)
    await asyncio.sleep(0.15)
    leave0 = await page.js(probe)
    await asyncio.sleep(0.4)
    leave1 = await page.js(probe)
    await asyncio.sleep(0.8)
    leave2 = await page.js(probe)
    await page.js("document.documentElement.style.removeProperty('--transition-normal')")
    await asyncio.sleep(0.1)
    # Vue 隔两帧才开始退场，重的弹窗在软件渲染下第一个采样点可能还没开始，所以看两个采样点
    fading = any(0 < sample.get("cont", 0) < 1 for sample in (leave0, leave1))
    ok = (
        enter0.get("cont", 1) < 0.5 and enter0.get("back", 1) < 0.5 and enter0.get("root") == 1
        and enter1.get("cont") == 1 and fading and leave2.get("gone") is True
        and (leave1.get("gone") or leave1.get("bodyH") == leave0.get("bodyH"))
    )
    ctx.check(f"动效 {name}", ok, (enter0, enter1, leave0, leave1, leave2))


async def check_first_load(ctx):
    """首次加载：最后一条放不下时在开头，放得下时贴底"""
    page = await ctx.page()
    state = await page.js(LAST_ROW)
    ctx.check("首次加载定位正确", abs(state["top"] - state["pad"]) <= 2 or state["dist"] <= 2, state)
    await page.shot("first-load")
    await ctx.close(page)


async def check_entry(ctx):
    """进入长会话：停在最后一条开头，没有闪结尾，滚动不被抢，增高不被拉走"""
    page = await ctx.page()
    await page.js(rf"""(() => {{ window.__f=[]; const t0=performance.now(); const tick=()=>{{ try {{ const el=__chat().setupState.messageListRef.scrollRef; const rows=[...el.querySelector('.max-w-4xl').children].filter(x=>x.classList.contains('group')); const last=rows[rows.length-1]; if(/最后一条开头 LONG/.test(last.innerText||'')) window.__f.push(Math.round(last.getBoundingClientRect().top-el.getBoundingClientRect().top)); }} catch(e) {{}} if(performance.now()-t0<1500) requestAnimationFrame(tick); }}; requestAnimationFrame(tick); void {C}.selectChat({{id:{json.dumps(ctx.fixtures['LONG'])}}}); }})(); 1""")
    await asyncio.sleep(1.8)
    frames = await page.js("window.__f")
    state = await page.js(LAST_ROW)
    ctx.check("长消息停在开头", abs(state["top"] - state["pad"]) <= 2 and state["dist"] > 0, state)
    ctx.check("进入时不闪结尾", frames and all(abs(f - state["pad"]) <= 2 for f in frames), frames[:6])
    await page.shot("entry-long")
    await page.js(GROW_LAST)
    await asyncio.sleep(0.6)
    grown = await page.js(LAST_ROW)
    ctx.check("停在开头时内容变高不被拉走", abs(grown["top"] - state["pad"]) <= 2 and grown["dist"] > state["dist"], grown)

    await ctx.enter(page, ctx.fixtures["MID"])
    state = await page.js(LAST_ROW)
    ctx.check("中等长度停在开头", abs(state["top"] - state["pad"]) <= 2 and state["dist"] > 0, state)

    await ctx.enter(page, ctx.fixtures["SHORT"])
    state = await page.js(LAST_ROW)
    ctx.check("放得下时贴底", state["dist"] <= 2, state)
    await asyncio.sleep(1.5)
    await page.js(GROW_LAST)
    await asyncio.sleep(0.8)
    grown = await page.js(LAST_ROW)
    ctx.check("贴底时内容变高继续贴底", grown["dist"] <= 2, grown)
    await page.wheel(-400)
    await asyncio.sleep(0.8)
    away = await page.js(LAST_ROW)
    await page.js(GROW_LAST)
    await asyncio.sleep(0.8)
    after = await page.js(LAST_ROW)
    ctx.check("往回看时内容变高不动", after["scrollTop"] == away["scrollTop"] and after["dist"] > away["dist"], (away, after))
    await ctx.close(page)

    page = await ctx.page()
    await page.js(f"void {C}.selectChat({{id:{json.dumps(ctx.fixtures['LONG'])}}}); 1")
    await asyncio.sleep(0.25)
    await page.wheel(600)
    await asyncio.sleep(0.5)
    a = await page.js(LAST_ROW)
    await asyncio.sleep(1.5)
    b = await page.js(LAST_ROW)
    ctx.check("进入后立刻滚动不被抢", a["top"] == b["top"] and b["top"] < b["pad"] - 100 and b["dist"] > 0, (a, b))
    await ctx.close(page)


async def check_search(ctx):
    """搜索：回车跳转、精确定位、目标高亮、计数、300+、无结果、关闭清除"""
    page = await ctx.page()
    await ctx.enter(page, ctx.fixtures["LONG"])
    await page.js(f"void {C}.openChatSearchBar(); 1")
    await asyncio.sleep(1.0)
    state = r"""(() => { const s=__chat().setupState; const el=s.messageListRef.scrollRef; const r=el.getBoundingClientRect(); const m=[...el.querySelectorAll('.message-row--search-target')]; const box=m[0]?.getBoundingClientRect(); return {status:s.chatSearchStatusText, marked:m.length, top:box?Math.round(box.top-r.top):null, pad:Math.round(parseFloat(getComputedStyle(el).paddingTop)), bg:m[0]?getComputedStyle(m[0],'::before').backgroundColor:null, shadow:m[0]?getComputedStyle(m[0],'::before').boxShadow:null}; })()"""
    await page.js(set_input("""document.querySelector('input[aria-label="搜索当前会话"]')""", "沙箱检索词"))
    await page.js("""document.querySelector('input[aria-label="搜索当前会话"]').focus()""")
    await asyncio.sleep(0.8)
    st = await page.js(state)
    ctx.check("超过上限显示 300+", st["status"] == "共 300+ 条", st["status"])
    for i in (1, 2):
        await page.key("Enter", 13)
        await asyncio.sleep(0.4)
    st = await page.js(state)
    ctx.check("回车逐条跳转", st["status"] == "2/300+" and st["marked"] == 1, st)
    ctx.check("目标是中性底色，不发光", st["shadow"] == "none" and "color(" in str(st["bg"]) and st["bg"].endswith("/ 0.08)"), st)
    await page.shot("search-target")
    total = await page.js(f"{C}.chatSearchHitsForNav.length")
    bad = []
    for index in (0, total // 2, total - 1, 5, total // 3):
        await page.js(f"{C}.jumpToSearchResult({index}); 1")
        await asyncio.sleep(0.45)
        st = await page.js(state)
        if st["marked"] != 1 or abs(st["top"] - st["pad"]) > 2:
            bad.append((index, st))
    ctx.check("远距离跳转定位准确", not bad, bad[:2])
    await page.js(set_input("""document.querySelector('input[aria-label="搜索当前会话"]')""", "最后一条开头 LONG"))
    await asyncio.sleep(0.8)
    ctx.check("少量结果没有加号", (await page.js(state))["status"] == "共 1 条", await page.js(state))
    await page.js(set_input("""document.querySelector('input[aria-label="搜索当前会话"]')""", "不可能出现的词zzqq"))
    await asyncio.sleep(0.8)
    ctx.check("没有结果时说明", (await page.js(state))["status"] == "无结果")
    await page.js(set_input("""document.querySelector('input[aria-label="搜索当前会话"]')""", "沙箱检索词"))
    await asyncio.sleep(0.8)
    await page.js(f"{C}.jumpToSearchResult(2); 1")
    await asyncio.sleep(0.4)
    await page.js("""document.querySelector('button[aria-label="关闭会话搜索"]').click()""")
    await asyncio.sleep(0.9)
    ctx.check("关闭后清除高亮", (await page.js("document.querySelectorAll('.message-row--search-target').length")) == 0)
    await ctx.close(page)


async def check_settings(ctx):
    """设置页：深链定位、TTS 分支、切换提供商不弹框、窄屏布局"""
    settings = ctx.api("/api/settings")
    llm = [x for x in settings["apiPresets"] if x.get("presetKind") != "tts"]
    target = llm[min(1, len(llm) - 1)]
    for start in ("closed", "open"):
        for field_name in ("echoReasoning", "promptCache", "webSearchSource"):
            page = await ctx.page()
            if start == "open":
                await ctx.open_settings(page)
            await page.js(f"{UI}.requestFocusSettings({{tab:'presets', presetId:{json.dumps(target['id'])}, field:{json.dumps(field_name)}}})")
            await asyncio.sleep(1.3)
            state = await page.js(f"""(() => {{ const el=[...document.querySelectorAll('[data-settings-field="{field_name}"]')].find(e=>e.classList.contains('settings-field-focus-ring')); if(!el) return {{ring:false}}; const b=el.getBoundingClientRect(); return {{ring:true,visible:el.offsetParent!==null,inView:b.top>=0&&b.top<innerHeight}}; }})()""")
            name = await page.js("""(() => { const i=[...document.querySelectorAll('input')].find(e=>e.offsetParent!==null && e.closest('.settings-field')?.innerText.includes('预设名称')); return i?i.value:null; })()""")
            ctx.check(f"深链 {start} {field_name}", state.get("ring") and state.get("visible") and state.get("inView") and name == target["name"], (state, name))
            await cdp.close_page(ctx.cdp_port, page)

    page = await ctx.page()
    await ctx.open_settings(page, "presets")
    tts = [x for x in settings["apiPresets"] if x.get("presetKind") == "tts"]
    pick = tts[0] if tts else None
    if pick is None:
        await page.js("""[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText.includes('新建')).click()""")
        await asyncio.sleep(0.3)
        await page.js("""[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText.includes('作为 TTS 服务')).click()""")
    else:
        await page.js(f"""[...document.querySelectorAll('[draggable]')].find(e=>e.offsetParent!==null&&e.innerText.trim().startsWith({json.dumps(pick['name'])})).click()""")
    await asyncio.sleep(0.4)
    expected = {"Qwen3": {"仓库路径", "主端口（CustomVoice 网关）", "由程序启动", "设备"}, "OmniVoice": {"仓库路径", "端口", "由程序启动", "设备"}, "GLM-TTS（本地）": {"仓库路径", "端口", "由程序启动"}, "硅基": set(), "OpenRouter": set()}
    for label, fields in expected.items():
        await page.js("""[...document.querySelectorAll('.settings-label')].find(e=>e.innerText.trim()==='TTS 提供商'&&e.offsetParent!==null).closest('.settings-field').querySelector('.cursor-pointer').click()""")
        await asyncio.sleep(0.3)
        await page.js(f"""(() => {{ const c=[...document.querySelectorAll('button,[role=option],li,div.cursor-pointer')].filter(e=>e.offsetParent!==null&&e.innerText.trim().includes({json.dumps(label)})&&e.children.length<4&&!e.closest('.settings-field')); c[c.length-1].click(); }})()""")
        await asyncio.sleep(0.5)
        ctx.check(f"切到 {label} 不弹框", not await page.js("!!document.querySelector('.app-notify-backdrop')"))
        labels = set(await page.js("""[...document.querySelectorAll('.settings-label')].filter(e=>e.offsetParent!==null).map(e=>e.innerText.trim())"""))
        over = await page.js("""(() => { const d=[...document.querySelectorAll('[role=dialog]')].find(x=>x.offsetParent!==null); const dr=d.getBoundingClientRect(); return [...d.querySelectorAll('*')].filter(e=>{ if(e.offsetParent===null) return false; const r=e.getBoundingClientRect(); if(!r.width||r.right<=dr.right+1) return false; let a=e.parentElement; while(a&&a!==d){ if(/auto|scroll/.test(getComputedStyle(a).overflowX)) return false; a=a.parentElement;} return true; }).length; })()""")
        ctx.check(f"{label} 字段和溢出", fields <= labels and over == 0, (sorted(fields - labels), over))
        await page.shot(f"tts-{label}")
    await ctx.close(page)

    for width, height in ((390, 844), (768, 1024)):
        for tab in ("global", "presets", "chat"):
            page = await ctx.page(width, height)
            await ctx.open_settings(page, tab)
            over = await page.js("""(() => { const d=[...document.querySelectorAll('[role=dialog]')].find(x=>x.offsetParent!==null); const dr=d.getBoundingClientRect(); return [...d.querySelectorAll('*')].filter(e=>{ if(e.offsetParent===null) return false; const r=e.getBoundingClientRect(); if(!r.width||r.right<=dr.right+1) return false; let a=e.parentElement; while(a&&a!==d){ if(/auto|scroll/.test(getComputedStyle(a).overflowX)) return false; a=a.parentElement;} return true; }).length; })()""")
            ctx.check(f"窄屏 {width} {tab} 无溢出", over == 0, over)
            await page.shot(f"narrow-{tab}-{width}")
            await cdp.close_page(ctx.cdp_port, page)


async def check_motion(ctx):
    """弹窗：入退场动效、Esc 每次只关一层、减少动态效果"""
    page = await ctx.page()
    await motion(ctx, page, "身份", f"{C}.actions.openEditPersona({C}.settings.settings.userPersonas[0])", CLOSE_LAST)
    await motion(ctx, page, "角色", f"{C}.actions.openEditCharacter({C}.characters.list[0])", CLOSE_LAST)
    await motion(ctx, page, "助手设置", f"{C}.assistant.showAssistantSettings.value = true", CLOSE_LAST)
    await motion(ctx, page, "建群", f"{C}.showGroupCreator = true", CLOSE_LAST)
    await motion(ctx, page, "导入", f"{C}.showImportModal = true", CLOSE_LAST)
    await motion(ctx, page, "导出", f"{C}.showExportModal = true", CLOSE_LAST)
    await motion(ctx, page, "身份切换确认", f"{C}.actions.showPersonaSwitchConfirm.value = true", f"{C}.actions.showPersonaSwitchConfirm.value = false")
    await motion(ctx, page, "知识图谱", f"{C}.knowledgeGraphModalOpen = true", f"{C}.knowledgeGraphModalOpen = false")
    await ctx.enter(page, ctx.fixtures["group"])
    await motion(ctx, page, "群聊设置", f"{C}.showGroupSettings = true", CLOSE_LAST)
    await motion(ctx, page, "成员设置", f"{C}.actions.openMemberSettingsEditor({C}.activeChat.memberIds[0])", CLOSE_LAST)
    await ctx.close(page)

    worldbooks = ctx.api("/api/worldbooks")
    page = await ctx.page()
    await ctx.open_settings(page)
    await motion(ctx, page, "正则规则", f"{D}.openRegexRuleEditor(null)", CLOSE_LAST)
    await motion(ctx, page, "模型选择", f"{D}.showModelSelector = true", f"{D}.showModelSelector = false")
    await motion(ctx, page, "音色选择", f"{D}.showVoiceSelector = true", f"{D}.showVoiceSelector = false")
    drawer = lambda: page.js("__drawer().props.show")
    modals = lambda: page.js("document.querySelectorAll('.modal').length")
    await page.js(f"{D}.openRegexRuleEditor(null)")
    await asyncio.sleep(0.5)
    await page.key("Escape", 27)
    await asyncio.sleep(0.5)
    ctx.check("Esc 关正则，抽屉还在", (await modals()) == 0 and await drawer())
    if worldbooks:
        book = worldbooks[0]["id"]
        await motion(ctx, page, "世界书", f"{D}.openWorldBookEditor({json.dumps(book)})", CLOSE_LAST)
        await page.js(f"{D}.openWorldBookEditor({json.dumps(book)})")
        await asyncio.sleep(0.8)
        opened = await page.js("""(() => { const b=document.querySelector('.modal button[aria-label="编辑"]'); if(!b) return false; b.click(); return true; })()""")
        await asyncio.sleep(0.5)
        if opened:
            await page.key("Escape", 27)
            await asyncio.sleep(0.5)
            ctx.check("Esc 只关条目", (await modals()) == 1 and await drawer())
        await page.key("Escape", 27)
        await asyncio.sleep(0.5)
        ctx.check("Esc 再关世界书", (await modals()) == 0 and await drawer())
    await page.key("Escape", 27)
    await asyncio.sleep(0.5)
    ctx.check("Esc 最后关抽屉", not await drawer())
    await page.js(f"{C}.actions.openEditCharacter({C}.characters.list[0])")
    await asyncio.sleep(0.5)
    await page.js(f"{C}.assistant.showAssistantSettings.value = true")
    await asyncio.sleep(0.5)
    await page.key("Escape", 27)
    await asyncio.sleep(0.5)
    ctx.check("Esc 只关助手设置，角色编辑还在", (await modals()) == 1 and await page.js(f"{C}.actions.showCharacterEditor.value"))
    await page.key("Escape", 27)
    await asyncio.sleep(0.5)
    await ctx.close(page)

    page = await ctx.page(reduce_motion=True)
    await page.js(f"{C}.showImportModal = true; 1")
    await asyncio.sleep(0.4)
    state = await page.js("(() => { const m=document.querySelector('.modal'); return {cont:getComputedStyle(m.querySelector('.modal-content')).opacity, back:getComputedStyle(m.querySelector('.modal-backdrop')).opacity}; })()")
    ctx.check("减少动态效果时弹窗能完整显示", state == {"cont": "1", "back": "1"}, state)
    await ctx.close(page)


async def check_saves(ctx):
    """弹窗保存：通过界面改值并保存，再从 API 读回"""
    page = await ctx.page()
    persona_id = await page.js(f"{C}.settings.settings.userPersonas[0].id")
    await page.js(f"{C}.actions.openEditPersona({C}.settings.settings.userPersonas[0])")
    await asyncio.sleep(0.4)
    await page.js(set_input(field("简介"), "沙箱身份简介"))
    await click_footer(page, "保存")
    persona = next(x for x in ctx.api("/api/settings")["userPersonas"] if x["id"] == persona_id)
    ctx.check("身份简介", persona["description"] == "沙箱身份简介")

    await page.js(f"{C}.assistant.showAssistantSettings.value = true")
    await asyncio.sleep(0.4)
    await page.js(set_input(field("温度"), "0.7"))
    await page.js(set_input(field("最大工具轮次"), "5"))
    before = await page.js(f"{switch('Fast 模式')}.getAttribute('aria-checked')")
    await page.js(f"{switch('Fast 模式')}.click()")
    await asyncio.sleep(0.1)
    ctx.check("助手 Fast 开关", before != await page.js(f"{switch('Fast 模式')}.getAttribute('aria-checked')"))
    await click_footer(page, "保存")
    saved = await page.js(f"({{t:{C}.assistant.assistantSettings.value.temperature, m:{C}.assistant.assistantSettings.value.maxToolTurns}})")
    ctx.check("助手设置字段", saved == {"t": 0.7, "m": 5}, saved)

    await page.js(f"{C}.actions.openEditCharacter({C}.characters.list[1])")
    await asyncio.sleep(0.5)
    character_id = await page.js(f"{C}.actions.editingCharacter.value.id")
    mvu_before = await page.js(f"{C}.actions.editingCharacter.value.mvuEnabled === true")
    await page.js(set_input(field("Personality"), "沙箱性格"))
    await page.js(set_input(field("首句"), "沙箱首句"))
    await page.js(f"{switch('启用 MVU 管线')}.click()")
    await page.js(f"{C}.actions.editingCharacter.value.mvuMode = 'regex'")
    await asyncio.sleep(0.2)
    await page.js("""[...document.querySelectorAll('.modal button')].find(b=>b.innerText.trim()==='新建规则').click()""")
    await asyncio.sleep(0.2)
    await page.js(set_input("""[...document.querySelectorAll('.modal textarea')].filter(t=>t.placeholder==='pattern').pop()""", "<state>(.*?)</state>"))
    await page.js(set_input("""[...document.querySelectorAll('.modal input')].filter(t=>t.placeholder==='规则名称（可选）').pop()""", "沙箱规则"))
    await page.js("""[...document.querySelectorAll('.modal button')].find(b=>b.innerText.trim()==='新建表格').click()""")
    await asyncio.sleep(0.2)
    await page.js(set_input("""[...document.querySelectorAll('.modal input')].filter(t=>t.placeholder==='表格名称').pop()""", "沙箱表"))
    await click_footer(page, "保存")
    await asyncio.sleep(0.5)
    card = ctx.api(f"/api/characters/{character_id}")
    ctx.check("角色文本字段", card["personality"] == "沙箱性格" and card["firstMessage"] == "沙箱首句")
    ctx.check("角色 MVU 开关", card.get("mvuEnabled") is (not mvu_before))
    rules = card.get("contentRegexRules") or []
    ctx.check("角色规则", rules and rules[-1]["pattern"] == "<state>(.*?)</state>" and rules[-1]["name"] == "沙箱规则" and rules[-1]["enabled"] is True, rules[-1:])
    tables = card.get("initialStateTables") or []
    ctx.check("角色状态表", tables and tables[-1]["name"] == "沙箱表", tables[-1:])

    group = ctx.fixtures["group"]
    await ctx.enter(page, group)
    await page.js(f"{C}.showGroupSettings = true; 1")
    await asyncio.sleep(0.4)
    text = await page.js("document.querySelector('.modal-content').innerText")
    ctx.check("开关文案", "system 放在最前（默认）" in text and "永远在底部" not in text)
    if await page.js(f"{switch('启用群聊 MVU')}.getAttribute('aria-checked')") == "false":
        await page.js(f"{switch('启用群聊 MVU')}.click()")
    await asyncio.sleep(0.2)
    await page.js(set_input(field("发言延迟"), "1234"))
    mode = await page.js("""[...document.querySelectorAll('.modal .settings-field')].find(f=>f.querySelector('.settings-label')?.innerText.trim()==='MVU 模式')?.innerText""")
    ctx.check("继承模式显示继承", "继承" in (mode or ""), mode)
    await page.shot("group-settings")
    await click_footer(page, "保存")
    await asyncio.sleep(0.5)
    chat = ctx.api(f"/api/chats/{group}")
    ctx.check("群聊 MVU", (chat.get("overrides") or {}).get("groupMvuEnabled") is True)
    ctx.check("发言延迟", chat.get("groupDelay") == 1234 or (chat.get("overrides") or {}).get("groupDelay") == 1234)

    member = await page.js(f"{C}.activeChat.memberIds[0]")
    await page.js(f"{C}.actions.openMemberSettingsEditor({json.dumps(member)}); 1")
    await asyncio.sleep(0.5)
    await page.js(set_input(field("Temperature"), "1.1"))
    await page.js(set_input(field("参与概率"), "0"))
    await page.js(f"{switch('插入 Scenario')}.click()")
    await asyncio.sleep(0.1)
    await click_footer(page, "保存")
    await asyncio.sleep(0.4)
    settings = (ctx.api(f"/api/chats/{group}").get("memberSettings") or {}).get(member) or {}
    ctx.check("成员设置和概率 0", settings.get("temperature") == 1.1 and settings.get("probability") == 0 and settings.get("includeScenario") is False, settings)

    await page.js(f"{C}.showGroupCreator = true; 1")
    await asyncio.sleep(0.5)
    await page.js(f"{switch('启用群聊 MVU')}.click()")
    await asyncio.sleep(0.2)
    await page.js("""(() => { const it=[...document.querySelectorAll('.modal .settings-item')]; it[0].click(); it[1].click(); })()""")
    await asyncio.sleep(0.3)
    ctx.check("建群选中成员", (await page.js("document.querySelectorAll('.modal .settings-item--selected').length")) == 2)
    await page.js(CLOSE_LAST)
    await asyncio.sleep(0.5)

    worldbooks = ctx.api("/api/worldbooks")
    await ctx.open_settings(page)
    if worldbooks:
        book = worldbooks[0]["id"]
        await page.js(f"{D}.openWorldBookEditor({json.dumps(book)})")
        await asyncio.sleep(0.8)
        if await page.js("""(() => { const b=document.querySelector('.modal button[aria-label="编辑"]'); if(!b) return false; b.click(); return true; })()"""):
            await asyncio.sleep(0.5)
            await page.js(set_input(field("标题"), "沙箱条目标题"))
            await page.js(set_input(field("正则表达式"), "沙箱|keyword"))
            await click_footer(page, "确定")
            await click_footer(page, "保存")
            entries = [e for e in ctx.api(f"/api/worldbooks/{book}")["entries"] if e.get("title") == "沙箱条目标题"]
            ctx.check("世界书条目", len(entries) == 1 and entries[0]["regex"] == "沙箱|keyword", entries[:1])
        else:
            await page.key("Escape", 27)
            await asyncio.sleep(0.4)
    await page.js(f"{D}.openRegexRuleEditor(null)")
    await asyncio.sleep(0.5)
    await page.js(set_input(field("规则名称"), "沙箱正文规则"))
    await page.js(set_input(field("Pattern"), "(沙箱)"))
    await click_footer(page, "保存")
    await asyncio.sleep(0.4)
    ctx.check("正则规则写回", await page.js(f"{D}.contentRegexRulesSorted?.some?.(r=>r.name==='沙箱正文规则')") is True)
    await ctx.close(page)


async def check_background(ctx):
    """背景预览：拖动时页面跟随，遮罩和抽屉让位，松手恢复，取消回到已保存值"""
    page = await ctx.page()
    image = await page.js("""[...document.querySelectorAll('img')].some(x=>/page[-_]backgrounds/.test(x.getAttribute('src')||''))""")
    await ctx.open_settings(page)
    await ctx.expand_appearance(page)
    slider = "[...document.querySelectorAll('input[type=range]')].find(r=>r.closest('.settings-field')?.innerText.includes('透明度'))"
    await page.js(f"{slider}.scrollIntoView({{block:'center'}})")
    await asyncio.sleep(0.4)
    box = await page.js(f"(() => {{ const r={slider}.getBoundingClientRect(); return {{x:r.left,y:r.top+r.height/2,w:r.width,v:+{slider}.value}}; }})()")
    state = f"""(() => {{ const w=document.querySelector('.drawer-wrapper'), b=w.querySelector('.drawer-backdrop'), d=w.querySelector('.drawer-panel'), a=w.querySelector('.settings-slider-active'); const other=d.querySelector('h2'); return {{adj:w.classList.contains('is-adjusting-background'), fade:w.classList.contains('is-background-fading'), back:+getComputedStyle(b).opacity, panelBg:getComputedStyle(d).backgroundColor, active:!!a, activeBg:a?getComputedStyle(a).backgroundColor:null, otherOp:other?+getComputedStyle(other).opacity:null, value:+{slider}.value}}; }})()"""
    opacity = """(() => { const i=[...document.querySelectorAll('img')].filter(x=>/page[-_]backgrounds/.test(x.getAttribute('src')||'')).sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width)[0]; return i?+getComputedStyle(i).opacity:null; })()"""
    start = await page.js(opacity)
    x0 = box["x"] + box["w"] * box["v"] / 100
    await page.mouse("mouseMoved", x0, box["y"])
    await page.mouse("mousePressed", x0, box["y"], button="left", clickCount=1)
    await asyncio.sleep(0.3)
    s1 = await page.js(state)
    ctx.check("拖动时遮罩和抽屉让位", s1["adj"] and s1["back"] == 0 and s1["active"] and s1["otherOp"] == 0 and s1["panelBg"] == "rgba(0, 0, 0, 0)", s1)
    ctx.check("滑块底色不透明", s1["activeBg"] and "/ " not in s1["activeBg"] and not s1["activeBg"].startswith("rgba"), s1["activeBg"])
    target = 0.8 if box["v"] < 50 else 0.2
    x1 = box["x"] + box["w"] * target
    await page.mouse("mouseMoved", x1, box["y"], button="left", buttons=1)
    await asyncio.sleep(0.25)
    s2 = await page.js(state)
    now = await page.js(opacity)
    if image:
        ctx.check("拖动时背景实时跟随", now is not None and abs(now - s2["value"] / 100) < 0.02 and abs(now - start) > 0.1, (s2["value"], now))
    await page.shot("background-dragging")
    await page.mouse("mouseReleased", x1, box["y"], button="left", clickCount=1)
    await asyncio.sleep(0.45)
    s3 = await page.js(state)
    ctx.check("松手恢复", not s3["adj"] and not s3["fade"] and s3["back"] > 0.3 and s3["otherOp"] == 1 and not s3["active"], s3)
    await page.js("""[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText.trim()==='取消'&&b.offsetParent!==null).click()""")
    await asyncio.sleep(0.5)
    await page.js("""(() => { const b=document.querySelector('.app-notify-backdrop'); if(!b) return; const c=[...b.parentElement.querySelectorAll('button')].find(x=>x.innerText.trim()!=='取消'); c&&c.click(); })()""")
    await asyncio.sleep(0.8)
    ctx.check("取消后抽屉关闭", not await page.js("__drawer().props.show"))
    if image:
        ctx.check("取消后回到已保存值", abs((await page.js(opacity)) - start) < 0.01)
    await ctx.close(page)


async def check_reading(ctx):
    """阅读字体和行高：只作用于消息正文，可预览，保存生效，代码保持等宽"""
    fonts = ctx.api("/api/fonts")
    page = await ctx.page()
    await ctx.enter(page, ctx.fixtures["LONG"])
    metric = """(() => { const c=document.querySelector('.message-reading-content'); const para=c.querySelector('p')||c; const s=getComputedStyle(para); const side=document.querySelector('aside .text-sm'); return {font:s.fontFamily, lh:parseFloat(s.lineHeight), fs:parseFloat(s.fontSize), ui:side?getComputedStyle(side).fontFamily:''}; })()"""
    base = await page.js(metric)
    await ctx.open_settings(page)
    await ctx.expand_appearance(page)
    font = fonts[0] if fonts else None
    await page.js(f"{D}.globalDraft.messageLineHeight = 2.2; {D}.globalDraft.readingFont = {json.dumps(font)}; 1")
    await asyncio.sleep(0.8)
    m = await page.js(metric)
    ctx.check("行高预览", abs(m["lh"] / m["fs"] - 2.2) < 0.02, m)
    if font:
        ctx.check("阅读字体只作用于正文", "AppReadingFont" in m["font"] and "AppReadingFont" not in m["ui"], m)
    await page.js("""[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText.trim()==='保存设置').click()""")
    await asyncio.sleep(1.0)
    saved = ctx.api("/api/settings")
    ctx.check("保存写入后端", saved.get("messageLineHeight") == 2.2 and saved.get("readingFont") == font)
    await page.goto("/")
    await ctx.enter(page, ctx.fixtures["LONG"])
    m = await page.js(metric)
    ctx.check("刷新后仍生效", abs(m["lh"] / m["fs"] - 2.2) < 0.02, m)
    code = await page.js("""(() => { const c=document.querySelector('.message-reading-content'); const e=document.createElement('code'); e.textContent='x'; c.appendChild(e); const f=getComputedStyle(e).fontFamily; e.remove(); return f; })()""")
    ctx.check("代码保持等宽", "AppReadingFont" not in code, code)
    await ctx.open_settings(page)
    await page.js(f"{D}.globalDraft.messageLineHeight = null; {D}.globalDraft.readingFont = null; 1")
    await asyncio.sleep(0.3)
    await page.js("""[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText.trim()==='保存设置').click()""")
    await asyncio.sleep(1.0)
    m = await page.js(metric)
    ctx.check("恢复默认", m["lh"] == base["lh"] and m["font"] == base["font"], m)
    await ctx.close(page)


async def check_sidebar(ctx):
    """侧栏：卡片无边框，简介不被切半行"""
    page = await ctx.page()
    info = await page.js("""(() => { const a=document.querySelector('aside'); const cards=[...a.querySelectorAll('.group')].filter(e=>e.offsetParent!==null); const bordered=cards.filter(e=>getComputedStyle(e).borderTopWidth!=='0px'&&getComputedStyle(e).borderTopStyle!=='none'); const clamp=[...a.querySelectorAll('.line-clamp-2')].slice(0,8).map(e=>{const lh=parseFloat(getComputedStyle(e).lineHeight); return +(e.clientHeight/lh).toFixed(2);}); return {cards:cards.length, bordered:bordered.length, clamp}; })()""")
    ctx.check("卡片无边框", info["bordered"] == 0 and info["cards"] > 0, info)
    ctx.check("简介整行显示", all(abs(x - round(x)) < 0.06 for x in info["clamp"]), info["clamp"])
    await page.shot("sidebar")
    await ctx.close(page)


async def check_delete(ctx):
    """删除消息：原地确认，超时和失焦复原，再点才删除"""
    page = await ctx.page()
    chat = ctx.fixtures["MID"]
    await ctx.enter(page, chat)
    button = "[...document.querySelectorAll('.inline-confirm')].filter(b=>b.offsetParent!==null).pop()"
    count = lambda: len(ctx.api(f"/api/chats/{chat}")["messages"])
    before = count()
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.1)
    armed = await page.js(f"({{t:{button}.innerText.trim(), a:{button}.classList.contains('inline-confirm--armed')}})")
    ctx.check("第一次点击变确认", armed == {"t": "确认？", "a": True}, armed)
    ctx.check("第一次点击不删除", count() == before)
    await asyncio.sleep(3.2)
    ctx.check("3 秒后复原", (await page.js(f"{button}.innerText.trim()")) == "删除")
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.05)
    await page.js(f"{button}.blur()")
    await asyncio.sleep(0.05)
    ctx.check("失焦复原", (await page.js(f"{button}.innerText.trim()")) == "删除")
    await page.js(f"{button}.focus(); {button}.click()")
    await asyncio.sleep(0.05)
    await page.js(f"{button}.click()")
    await asyncio.sleep(0.9)
    ctx.check("第二次点击才删除", count() == before - 1, (before, count()))
    await ctx.close(page)


async def send_message(page, text):
    await page.js(f"""(() => {{ const t=document.querySelector('textarea[placeholder^="发送消息"]'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,{json.dumps(text)}); t.dispatchEvent(new Event('input',{{bubbles:true}})); }})()""")
    await asyncio.sleep(0.2)
    await page.js("""[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='发送' && b.offsetParent!==null).click()""")


async def check_follow(ctx):
    """流式跟底：向上滚能解除，向下滚不解除，回到底部恢复，结束后在底部"""
    ctx.mock_state.tps = 60

    async def scenario(name, action, expect_following):
        page = await ctx.page()
        await ctx.enter(page, ctx.fixtures["SHORT"])
        await send_message(page, "沙箱测试 " + name)
        await page.wait_for(f"{C}.isGenerating", 5)
        await page.wait_for("""(() => { const el=__chat().setupState.messageListRef.scrollRef; const rows=[...el.querySelector('.max-w-4xl').children].filter(x=>x.classList.contains('group')); return (rows[rows.length-1].querySelector('.prose')?.innerText||'').length>10; })()""", 25)
        await asyncio.sleep(0.3)
        await page.js(cdp.DISMISS)
        if action:
            await action(page)
        await asyncio.sleep(0.6)
        trace = []
        for _ in range(4):
            trace.append(await page.js(DIST))
            await asyncio.sleep(0.4)
        for _ in range(60):
            if not await page.js(f"{C}.isGenerating"):
                break
            await asyncio.sleep(0.5)
        await asyncio.sleep(1.0)
        final = await page.js(DIST)
        if expect_following:
            ctx.check(f"{name}: 跟到底", all(d <= 2 for d in trace) and final <= 2, (trace, final))
        else:
            ctx.check(f"{name}: 不再跟底", trace[0] > 100 and trace[-1] > trace[0] and final > 100, (trace, final))
        await cdp.close_page(ctx.cdp_port, page)

    async def up_and_back(page):
        await page.wheel(-300)
        await asyncio.sleep(0.5)
        await page.wheel(3000)

    await scenario("不操作", None, True)
    await scenario("向上滚 120", lambda p: p.wheel(-120), False)
    await scenario("向上滚 800", lambda p: p.wheel(-800), False)
    await scenario("向下滚", lambda p: p.wheel(120), True)
    await scenario("向上再滚回底", up_and_back, True)
    ctx.mock_state.tps = 1500


async def check_version(ctx):
    """切版本：正文按方向滑入，整行不动，减少动态效果时不滑"""
    page = await ctx.page()
    await ctx.enter(page, ctx.fixtures["SHORT"])
    await page.js("""[...document.querySelectorAll('button')].filter(b=>b.innerText.trim()==='重写'&&b.offsetParent!==null).pop().click()""")
    for _ in range(40):
        await asyncio.sleep(0.4)
        await page.js(cdp.DISMISS)
        if not await page.js(f"{C}.isGenerating"):
            break
    await asyncio.sleep(0.8)
    has_versions = await page.js("""document.querySelectorAll('button[aria-label^="上一个版本"]').length""")
    ctx.check("重写后有版本箭头", has_versions >= 1, has_versions)
    if not has_versions:
        await ctx.close(page)
        return
    probe = r"""(dir) => { const b=[...document.querySelectorAll(`button[aria-label^="${dir<0?'上一个':'下一个'}版本"]`)].pop(); const row=b.closest('.group'); const el=row.querySelector('.message-reading-content'); const a0=row.getBoundingClientRect(); window.__log=[]; b.click(); const t0=performance.now(); const tick=()=>{ const s=getComputedStyle(el); const m=new DOMMatrix(s.transform); window.__log.push([+(+s.opacity).toFixed(2), +m.m41.toFixed(1), Math.round(row.getBoundingClientRect().left-a0.left)]); if(performance.now()-t0<320) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }"""
    for direction, name in ((1, "下一个"), (-1, "上一个")):
        await page.js(f"({probe})({direction})")
        await asyncio.sleep(0.5)
        log = await page.js("window.__log")
        moving = [x for x in log if abs(x[1]) > 0.5]
        ctx.check(f"{name}版本滑入", moving and (moving[0][1] > 0) == (direction > 0) and log[0][0] < 1 and log[-1][0] == 1 and abs(log[-1][1]) < 0.5, log[:3])
        ctx.check(f"{name}版本整行不动", all(x[2] == 0 for x in log))
    await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    await page.js(f"({probe})(1)")
    await asyncio.sleep(0.4)
    log = await page.js("window.__log")
    ctx.check("减少动态效果时不滑", all(abs(x[1]) < 0.5 and x[0] == 1 for x in log), log[:2])
    await ctx.close(page)


BUILT_SCROLLER = "document.querySelector('.drawer-panel .drawer-scroll.p-6')"
BUILT_LIST = "[...document.querySelectorAll('.drawer-panel .drawer-scroll')].find(e=>e.querySelector(':scope > [draggable=true]'))"
BUILT_GEOMETRY = f"""(() => {{ const s={BUILT_SCROLLER}, l={BUILT_LIST}; const items=[...l.children].filter(c=>c.getAttribute('draggable')==='true'); const last=items[items.length-1];
  const sr=s.getBoundingClientRect(), lr=l.getBoundingClientRect(), ir=last.getBoundingClientRect(); const bottom=sr.top+s.clientTop+s.clientHeight;
  const hit=(y)=>{{const e=document.elementFromPoint(ir.left+ir.width/2,y); return !!e&&(e===last||last.contains(e));}};
  return {{count:items.length, scrollTop:Math.round(s.scrollTop), overflowX:s.scrollWidth-s.clientWidth, listTop:Math.round(lr.top-sr.top), lastGap:Math.round(bottom-ir.bottom), bottomHit:hit(ir.bottom-2)}}; }})()"""


def click_text(root, text):
    return f"""(() => {{ const b=[...{root}.querySelectorAll('button')].filter(x=>x.offsetParent!==null).find(x=>x.innerText.trim()==={json.dumps(text)}); if(!b) throw new Error('没有按钮 '+{json.dumps(text)}); b.click(); }})()"""


def prefixed_blur_rules(css):
    """找出声明了 -webkit-backdrop-filter、却没有标准 backdrop-filter 的规则。

    Chromium 不认带前缀的写法，这样的规则在构建后没有模糊。按声明的属性名判断，transition 的值里出现这个词不算。
    """
    found = []
    frames = [{"prelude": "", "props": []}]
    buffer = []
    quote = None
    parens = 0
    i = 0

    def flush_declaration():
        text = "".join(buffer).strip()
        buffer.clear()
        if ":" in text:
            frames[-1]["props"].append(text.split(":", 1)[0].strip().lower())

    while i < len(css):
        ch = css[i]
        if quote:
            buffer.append(ch)
            if ch == "\\":
                buffer.append(css[i + 1:i + 2])
                i += 1
            elif ch == quote:
                quote = None
        elif css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = len(css) if end < 0 else end + 1
        elif ch in "\"'":
            quote = ch
            buffer.append(ch)
        elif ch == "(":
            parens += 1
            buffer.append(ch)
        elif ch == ")":
            parens = max(0, parens - 1)
            buffer.append(ch)
        elif parens:
            buffer.append(ch)
        elif ch == "{":
            frames.append({"prelude": "".join(buffer).strip(), "props": []})
            buffer.clear()
        elif ch == ";":
            flush_declaration()
        elif ch == "}":
            flush_declaration()
            frame = frames.pop() if len(frames) > 1 else frames[0]
            if "-webkit-backdrop-filter" in frame["props"] and "backdrop-filter" not in frame["props"]:
                found.append(" > ".join(f["prelude"] for f in frames[1:] + [frame]))
        else:
            buffer.append(ch)
        i += 1
    return found


def built_css_files(ctx):
    return sorted(glob.glob(os.path.join(ctx.built_dir, "assets", "**", "*.css"), recursive=True))


def check_prefixed_blur(ctx):
    samples = (
        (".a{-webkit-backdrop-filter:blur(2px)}", [".a"]),
        (".a{-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}", []),
        (".a{backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px)}", []),
        (".a{transition:-webkit-backdrop-filter .2s,backdrop-filter .2s}", []),
        ("@media (min-width:1px){.b{-webkit-backdrop-filter:none}}", ["@media (min-width:1px) > .b"]),
        (""".c{background:url("a;{b.png");color:red;-webkit-backdrop-filter:blur(1px)}.d{color:red}""", [".c"]),
    )
    wrong = [(css, prefixed_blur_rules(css)) for css, expected in samples if prefixed_blur_rules(css) != expected]
    ctx.check("模糊规则扫描器自检", not wrong, wrong)
    files = built_css_files(ctx)
    rules = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            rules.extend(prefixed_blur_rules(f.read()))
    print(f"  记录  {len(files)} 个 CSS 文件里，只带 -webkit- 前缀的模糊规则 {len(rules)} 条")
    for rule in rules:
        print(f"    {rule}")
    ctx.check("构建后没有只带 -webkit- 前缀的模糊规则", files and not rules, f"{len(rules)} 条")


COMBO_TOGGLE = "document.querySelector('[aria-label=\"展开供应商列表\"]')"
COMBO_PANEL = "document.querySelector('[aria-label=\"搜索供应商\"]')?.closest('.rounded-xl')"
COMBO_STATE = f"""(() => {{
  const panel = {COMBO_PANEL};
  if (!panel) return {{open: false}};
  const nested = [];
  for (let a = panel.parentElement; a; a = a.parentElement) {{
    const c = getComputedStyle(a);
    if (c.backdropFilter !== 'none' || c.maskImage !== 'none' || +c.opacity < 1 || c.filter !== 'none') nested.push(a.className.toString().slice(0, 40));
  }}
  const items = [...panel.querySelectorAll('button')].filter(b => b.querySelector('.truncate'));
  const rows = items.map(b => {{
    const name = b.querySelector('.truncate');
    const kids = [...b.children].map(c => Math.round(c.getBoundingClientRect().top));
    return {{text: name.textContent.trim(), w: Math.round(name.getBoundingClientRect().width), lines: new Set(kids).size, over: b.scrollWidth - b.clientWidth}};
  }});
  const r = panel.getBoundingClientRect();
  return {{open: true, blur: getComputedStyle(panel).backdropFilter, nested, count: rows.length,
    hidden: rows.filter(x => x.w < 24).map(x => x.text).slice(0, 5),
    notThree: rows.filter(x => x.lines !== 3).map(x => x.text).slice(0, 5),
    over: rows.filter(x => x.over > 0).map(x => x.text).slice(0, 5),
    inView: r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth}};
}})()"""


async def check_preset_combobox(ctx, page, count):
    """预设名称下拉：在抽屉里嵌套的 backdrop-filter 不生效，所以面板必须在抽屉之外；每项三行，厂商名不能被标签挤没"""
    found = False
    for index in range(count):
        await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]')[{index}].click()")
        await asyncio.sleep(0.3)
        if await page.js(f"!!{COMBO_TOGGLE}"):
            found = True
            break
    ctx.check("有带供应商下拉的预设", found)
    if not found:
        return
    await page.js(f"{BUILT_SCROLLER}.scrollTop=0")
    await page.js(f"{COMBO_TOGGLE}.click()")
    await asyncio.sleep(0.5)
    state = await page.js(COMBO_STATE)
    ctx.check("供应商下拉打开", state.get("open"), state)
    if not state.get("open"):
        return
    ctx.check("下拉面板有模糊，且外层没有会让它失效的效果", "blur(" in state["blur"] and not state["nested"], {"blur": state["blur"], "nested": state["nested"]})
    ctx.check(f"{state['count']} 个供应商的名字都显示出来", state["count"] > 20 and not state["hidden"], state["hidden"])
    ctx.check("每项是三行：名字、协议和缓存、地址", not state["notThree"], state["notThree"])
    ctx.check("下拉项没有横向溢出，面板在视口内", not state["over"] and state["inView"], state)
    await page.shot("built-preset-combobox")
    await page.js("document.querySelector('[aria-label=\"搜索供应商\"]').focus()")
    await page.key("Escape", 27)
    await asyncio.sleep(0.4)
    after = await page.js(f"({{combo: !!{COMBO_PANEL}, drawer: getComputedStyle(document.querySelector('.drawer-wrapper')).visibility}})")
    ctx.check("Esc 只关下拉，不关设置", not after["combo"] and after["drawer"] == "visible", after)



async def check_built(ctx):
    """构建产物：压缩后的 CSS 才是用户看到的，开发服务器测不出模糊失效。这里没有 Vue 实例，只能操作 DOM"""
    page = await cdp.open_page(ctx.cdp_port, ctx.serve_built(), ctx.shots_dir, 1536, 800)
    check_prefixed_blur(ctx)
    await page.goto("/")
    panel = "document.querySelector('.drawer-panel')"
    style = f"""(() => {{ const p=getComputedStyle({panel}), w=getComputedStyle(document.querySelector('.drawer-wrapper')); return {{blur:p.backdropFilter, bg:p.backgroundColor, moving:p.transform!=='matrix(1, 0, 0, 1, 0, 0)', root:+w.opacity, vis:w.visibility}}; }})()"""
    closed = await page.js(style)
    ctx.check("关闭时抽屉不可见", closed["vis"] == "hidden", closed)
    await page.js(click_text("document", "设置"))
    await asyncio.sleep(0.1)
    opening = await page.js(style)
    ctx.check("滑入时外层不淡入，模糊全程有效", opening["moving"] and opening["root"] == 1 and "blur(12px)" in opening["blur"], opening)
    await asyncio.sleep(1)
    opened = await page.js(style)
    ctx.check("构建后抽屉有模糊", "blur(12px)" in opened["blur"], opened)
    await page.shot("built-drawer")

    await page.js("""(() => { const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>x.innerText.includes('外观与数据')); if(b.getAttribute('aria-expanded')!=='true') b.click(); })()""")
    await asyncio.sleep(0.5)
    slider = "[...document.querySelectorAll('input[type=range]')].find(r=>r.closest('.settings-field')?.innerText.includes('透明度'))"
    await page.js(f"{slider}.scrollIntoView({{block:'center'}})")
    await asyncio.sleep(0.4)
    box = await page.js(f"(() => {{ const r={slider}.getBoundingClientRect(); return {{x:r.left,y:r.top+r.height/2,w:r.width,v:+{slider}.value}}; }})()")
    x = box["x"] + box["w"] * box["v"] / 100
    await page.mouse("mouseMoved", x, box["y"])
    await page.mouse("mousePressed", x, box["y"], button="left", clickCount=1)
    await asyncio.sleep(0.35)
    dragging = await page.js(style)
    ctx.check("拖背景滑块时模糊让位", dragging["blur"] == "none" and dragging["bg"] == "rgba(0, 0, 0, 0)", dragging)
    await page.mouse("mouseReleased", x, box["y"], button="left", clickCount=1)
    await asyncio.sleep(0.45)
    ctx.check("松手后模糊恢复", "blur(12px)" in (await page.js(style))["blur"])

    await page.js(click_text(panel, "API 预设"))
    await asyncio.sleep(0.6)
    count = (await page.js(BUILT_GEOMETRY))["count"]
    bad, tops = [], set()
    for index in range(count):
        await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]')[{index}].click()")
        await asyncio.sleep(0.3)
        for where in ("0", "Math.min(300,(el.scrollHeight-el.clientHeight)/2)", "el.scrollHeight"):
            await page.js(f"(() => {{ const el={BUILT_SCROLLER}; el.scrollTop={where}; }})()")
            await asyncio.sleep(0.12)
            await page.js(f"{BUILT_LIST}.scrollTop=1e6")
            await asyncio.sleep(0.08)
            geometry = await page.js(BUILT_GEOMETRY)
            tops.add(geometry["listTop"])
            if geometry["overflowX"] > 0 or geometry["lastGap"] < 0 or not geometry["bottomHit"]:
                bad.append((index, where[:5], geometry))
    ctx.check(f"{count} 个预设：右栏任意位置都能滚到最后一项，没有横向溢出", not bad, bad[:3])
    ctx.check("右栏滚到底时列表不被顶走", len(tops) == 1, sorted(tops))
    await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]')[{count - 1}].click()")
    await asyncio.sleep(0.3)
    await page.js(f"{BUILT_SCROLLER}.scrollTop=0; {BUILT_LIST}.scrollTop=1e6")
    await asyncio.sleep(0.3)
    await page.shot("built-presets")
    await check_preset_combobox(ctx, page, count)
    await ctx.close(page)


HINT_TOGGLES = "[...document.querySelectorAll('.drawer-panel .settings-hint-toggle')].filter(b => b.offsetParent)"
OPEN_ACCORDIONS = """(() => {
  let n = 0;
  for (let round = 0; round < 4; round++) {
    const closed = [...document.querySelectorAll('.drawer-panel button[aria-expanded=false]')].filter(b => b.offsetParent && !b.classList.contains('settings-hint-toggle') && !b.getAttribute('aria-label')?.includes('供应商'));
    if (!closed.length) break;
    closed.forEach(b => { b.click(); n++; });
  }
  return n;
})()"""
HINT_PROBE = """(async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const panel = document.querySelector('.drawer-panel');
  const toggles = %s;
  const bad = [];
  for (const b of toggles) {
    const host = b.closest('.settings-field, .settings-hint') || b.parentElement.parentElement;
    const more = host.querySelector('.settings-hint-more');
    const name = (b.getAttribute('aria-label') || '') + '|' + (host.innerText || '').trim().slice(0, 16);
    if (!more) { bad.push(['没有展开区', name]); continue; }
    const before = more.getBoundingClientRect().height;
    b.click();
    await wait(380);
    const r = more.getBoundingClientRect();
    const text = more.innerText.trim();
    const pr = panel.getBoundingClientRect();
    if (before > 1) bad.push(['收起时就有高度', name, before]);
    if (r.height < 12 || text.length < 4) bad.push(['点开后没有内容', name, r.height, text]);
    if (r.right > pr.right + 1 || r.left < pr.left - 1 || more.scrollWidth > more.clientWidth + 1) bad.push(['展开后横向出界', name]);
    if (b.getAttribute('aria-expanded') !== 'true') bad.push(['aria-expanded 没变', name]);
    b.click();
    await wait(380);
    if (more.getBoundingClientRect().height > 1) bad.push(['再点收不回去', name]);
  }
  return {count: toggles.length, bad};
})()""" % HINT_TOGGLES


async def check_drawer_details(ctx):
    """设置抽屉的细节（构建产物）：每个 ⓘ 都能点开和收回；供应商下拉在窄屏、选中、滚动、关抽屉时的行为"""
    for width, height in ((1536, 800), (420, 800)):
        page = await cdp.open_page(ctx.cdp_port, ctx.serve_built(), ctx.shots_dir, width, height)
        await page.goto("/")
        if width < 768:
            # 窄屏下侧栏盖住主区，先收起才点得到设置
            await page.js("document.querySelector('[aria-label*=\"收起\"]')?.click()")
            await asyncio.sleep(0.4)
        await page.js(click_text("document", "设置"))
        await asyncio.sleep(1)
        panel = "document.querySelector('.drawer-panel')"
        total = 0
        for tab in ("全局设置", "API 预设", "当前会话"):
            await page.js(click_text(panel, tab))
            await asyncio.sleep(0.5)
            await page.js(OPEN_ACCORDIONS)
            await asyncio.sleep(0.6)
            result = await page.js(HINT_PROBE)
            total += result["count"]
            ctx.check(f"{width} 宽「{tab}」：{result['count']} 个 ⓘ 都能点开、有内容、不出界、能收回", not result["bad"], result["bad"][:4])
            overflow = await page.js(f"(() => {{ const el=document.querySelector('.drawer-panel .drawer-scroll.p-6') || {panel}; return el.scrollWidth - el.clientWidth; }})()")
            ctx.check(f"{width} 宽「{tab}」：没有横向滚动", overflow <= 1, overflow)
        ctx.check(f"{width} 宽：三个标签页一共找到的 ⓘ 不少于 10 个", total >= 10, total)

        await page.js(click_text(panel, "API 预设"))
        await asyncio.sleep(0.5)
        count = await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]').length")
        found = False
        for index in range(count):
            await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]')[{index}].click()")
            await asyncio.sleep(0.3)
            if await page.js(f"!!{COMBO_TOGGLE}"):
                found = True
                break
        if not found:
            ctx.check(f"{width} 宽：有带供应商下拉的预设", False)
            await ctx.close(page)
            continue
        await page.js(f"{COMBO_TOGGLE}.scrollIntoView({{block:'center'}})")
        await asyncio.sleep(0.3)
        await page.js(f"{COMBO_TOGGLE}.click()")
        await asyncio.sleep(0.5)
        state = await page.js(COMBO_STATE)
        ctx.check(f"{width} 宽：下拉在视口内、三行、名字都在、不溢出", state.get("open") and state["inView"] and not state["hidden"] and not state["notThree"] and not state["over"], state)
        await page.shot(f"combobox-{width}")

        geometry = "(() => { const p=%s.getBoundingClientRect(), i=%s.closest('.relative').getBoundingClientRect(); return {gapBelow: Math.round(p.top - i.bottom), gapAbove: Math.round(i.top - p.bottom), right: Math.round(p.right - i.right), wide: p.width > i.width + 1, inView: p.left >= 0 && p.right <= innerWidth}; })()" % (COMBO_PANEL, COMBO_TOGGLE)
        before = await page.js(geometry)
        await page.js(f"(() => {{ const el={BUILT_SCROLLER}; el.scrollTop += 40; }})()")
        await asyncio.sleep(0.3)
        after = await page.js(geometry)
        # 输入框比面板最小宽度窄时，面板会比输入框宽，这时只要求留在视口内
        attached = lambda g: (g["gapBelow"] == 6 or g["gapAbove"] == 6) and g["inView"] and (abs(g["right"]) <= 1 or g["wide"])
        ctx.check(f"{width} 宽：下拉贴着输入框，抽屉滚动后仍然贴着", attached(before) and attached(after), {"before": before, "after": after})

        fields = "(() => { const f=[...document.querySelectorAll('.drawer-panel .settings-field')].filter(x=>x.offsetParent); const v=l=>f.find(x=>x.querySelector('.settings-label')?.innerText.trim().startsWith(l))?.querySelector('input')?.value; return {name: v('预设名称'), url: v('API 基础地址')}; })()"
        target = await page.js(f"(() => {{ const b=[...{COMBO_PANEL}.querySelectorAll('button')].find(x=>x.innerText.includes('DeepInfra')); b.scrollIntoView({{block:'center'}}); const r=b.getBoundingClientRect(); return {{x:r.left+r.width/2, y:r.top+r.height/2}}; }})()")
        await asyncio.sleep(0.2)
        target = await page.js(f"(() => {{ const b=[...{COMBO_PANEL}.querySelectorAll('button')].find(x=>x.innerText.includes('DeepInfra')); const r=b.getBoundingClientRect(); return {{x:r.left+r.width/2, y:r.top+r.height/2}}; }})()")
        await page.mouse("mouseMoved", target["x"], target["y"])
        await page.mouse("mousePressed", target["x"], target["y"], button="left", clickCount=1)
        await page.mouse("mouseReleased", target["x"], target["y"], button="left", clickCount=1)
        await asyncio.sleep(0.5)
        chosen = await page.js(fields)
        ctx.check(f"{width} 宽：用鼠标选 DeepInfra 后名称和地址都填上，下拉关闭",
                  chosen["name"] == "DeepInfra" and chosen["url"] == "https://api.deepinfra.com/v1/openai" and not await page.js(f"!!{COMBO_PANEL}"), chosen)

        await page.js(f"{COMBO_TOGGLE}.click()")
        await asyncio.sleep(0.4)
        await page.js("(() => { const i=document.querySelector('[aria-label=\"搜索供应商\"]'); i.focus(); })()")
        for ch in "qianfan":
            await page.send("Input.dispatchKeyEvent", type="char", text=ch)
        await asyncio.sleep(0.3)
        filtered = await page.js(COMBO_STATE)
        ctx.check(f"{width} 宽：在下拉里打字能筛选（qianfan 只剩 1 项），按键没有被全局快捷键吃掉", filtered.get("count") == 1, filtered.get("count"))
        await page.key("Tab", 9)
        await asyncio.sleep(0.1)
        focused = await page.js(f"({{inPanel: !!{COMBO_PANEL}?.contains(document.activeElement), tag: document.activeElement?.tagName, text: (document.activeElement?.innerText || '').slice(0, 12)}})")
        ctx.check(f"{width} 宽：Tab 后焦点落在下拉里的筛选结果上", focused["inPanel"] and focused["tag"] == "BUTTON", focused)
        # 按钮靠 keypress 触发点击，只发 keyDown 不算数
        await page.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text=chr(13))
        await page.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await asyncio.sleep(0.5)
        keyboard = await page.js(fields)
        ctx.check(f"{width} 宽：Tab 到筛选结果按回车能选中", keyboard["url"] == "https://qianfan.baidubce.com/v2", keyboard)

        if width >= 768:
            # 手填官方地址、不从下拉选：仍然是 API Key 预设，不能被当成要登录的订阅预设
            await page.js("(() => { const b=[...document.querySelectorAll('.drawer-panel button')].filter(x=>x.offsetParent).find(x=>x.innerText.includes('新建')); if(!b) throw new Error('没有新建按钮'); b.click(); })()")
            await asyncio.sleep(0.5)
            url_input = "[...document.querySelectorAll('.drawer-panel .settings-field')].filter(x=>x.offsetParent).find(x=>x.querySelector('.settings-label')?.innerText.trim().startsWith('API 基础地址')).querySelector('input')"
            key_state = "(() => { const f=[...document.querySelectorAll('.drawer-panel .settings-field')].filter(x=>x.offsetParent); return {key: f.some(x=>x.querySelector('.settings-label')?.innerText.trim()==='API Key' && x.querySelector('input')), login: [...document.querySelectorAll('.drawer-panel button')].some(b=>b.offsetParent && /登录/.test(b.innerText))}; })()"
            wrong = []
            for typed in ("https://api.openai.com/v1", "https://api.x.ai/v1"):
                await page.js(set_input(url_input, typed))
                await asyncio.sleep(0.4)
                got = await page.js(key_state)
                if not got["key"] or got["login"]:
                    wrong.append((typed, got))
            ctx.check("手填 OpenAI / xAI 官方地址的预设显示 API Key 输入框，不显示登录", not wrong, wrong)
            await page.js(set_input(url_input, "https://example.invalid/v1"))
            await asyncio.sleep(0.3)
            ctx.check("对照：其他地址显示 API Key 输入框", (await page.js(key_state))["key"])

        await page.js(f"{COMBO_TOGGLE}.click()")
        await asyncio.sleep(0.4)
        close = await page.js("(() => { const b=document.querySelector('.drawer-panel .icon-button'); const r=b.getBoundingClientRect(); return {x:r.left+r.width/2, y:r.top+r.height/2}; })()")
        await page.mouse("mouseMoved", close["x"], close["y"])
        await page.mouse("mousePressed", close["x"], close["y"], button="left", clickCount=1)
        await page.mouse("mouseReleased", close["x"], close["y"], button="left", clickCount=1)
        await asyncio.sleep(0.8)
        leftover = await page.js(f"({{combo: !!{COMBO_PANEL}, body: document.querySelectorAll('body > .preset-combobox-panel').length}})")
        ctx.check(f"{width} 宽：点抽屉的关闭按钮时，下拉不会留在页面上", not leftover["combo"] and leftover["body"] == 0, leftover)
        await ctx.close(page)


VERTEX_FAKE_KEY_BODY = "UiCheckFakePrivateKeyBody0123456789abcdefghijklmnopqrstuvwxyzABCDEF"
VERTEX_FAKE_ACCOUNT = json.dumps({
    "type": "service_account",
    "project_id": "ui-check-project",
    "private_key_id": "0123456789abcdef0123456789abcdef01234567",
    "private_key": "-----BEGIN PRIVATE KEY-----\n" + VERTEX_FAKE_KEY_BODY + "\n-----END PRIVATE KEY-----\n",
    "client_email": "ui-check@ui-check-project.iam.gserviceaccount.com",
    "client_id": "100000000000000000000",
    "token_uri": "https://oauth2.googleapis.com/token",
})
VERTEX_BOX = "document.querySelector('.drawer-panel [data-vertex-service-account]')"
VERTEX_STATE = f"""(() => {{
  const box = {VERTEX_BOX};
  if (!box) return {{present: false}};
  const value = label => box.querySelector(`input[aria-label="${{label}}"]`)?.value ?? null;
  const fields = [...document.querySelectorAll('.drawer-panel .settings-field')].filter(x => x.offsetParent);
  const labels = fields.map(x => x.querySelector('.settings-label')?.innerText.trim()).filter(Boolean);
  return {{present: true, importing: !!box.querySelector('textarea[aria-label="粘贴服务账号 JSON"]'),
    email: value('服务账号邮箱'), key: value('私钥'), project: value('项目 ID'), location: value('位置'),
    error: box.querySelector('[role=alert]')?.innerText.trim() || '',
    apiKeyField: labels.includes('API Key'), duplicated: labels.filter(l => l.startsWith('项目 ID') || l.startsWith('位置')).length,
    text: box.innerText}};
}})()"""


async def check_vertex_account(ctx):
    """Vertex 服务账号预设（构建产物）：导入 JSON 后拆成邮箱、私钥、项目 ID、位置；位置由用户填；保存后私钥不回到前端"""
    page = await cdp.open_page(ctx.cdp_port, ctx.serve_built(), ctx.shots_dir, 1536, 900)
    await page.goto("/")
    await page.js(click_text("document", "设置"))
    await asyncio.sleep(1)
    panel = "document.querySelector('.drawer-panel')"
    await page.js(click_text(panel, "API 预设"))
    await asyncio.sleep(0.5)
    await page.js("(() => { const b=[...document.querySelectorAll('.drawer-panel button')].filter(x=>x.offsetParent).find(x=>x.innerText.includes('新建')); b.click(); })()")
    await asyncio.sleep(0.5)
    await page.js(f"{COMBO_TOGGLE}.click()")
    await asyncio.sleep(0.4)
    picked = await page.js(f"(() => {{ const b=[...{COMBO_PANEL}.querySelectorAll('button')].find(x=>x.innerText.includes('Gemini，服务账号')); if(!b) return false; b.click(); return true; }})()")
    ctx.check("供应商下拉里有「Google Vertex AI（Gemini，服务账号）」", picked)
    if not picked:
        await ctx.close(page)
        return
    await asyncio.sleep(0.5)
    state = await page.js(VERTEX_STATE)
    ctx.check("选中后显示导入界面，不显示 API Key 输入框", state.get("present") and state["importing"] and not state["apiKeyField"], state)

    paste = f"{VERTEX_BOX}.querySelector('textarea')"
    await page.js(set_input(paste, '{"type": "authorized_user", "client_id": "x"}'))
    await page.js(f"{paste}.dispatchEvent(new FocusEvent('blur'))")
    await asyncio.sleep(0.3)
    bad = await page.js(VERTEX_STATE)
    ctx.check("对照：粘贴不是服务账号的 JSON 时报错，不导入", bad["importing"] and "service_account" in bad["error"] and bad["email"] is None, bad)

    await page.js(set_input(paste, VERTEX_FAKE_ACCOUNT))
    await asyncio.sleep(0.4)
    loaded = await page.js(VERTEX_STATE)
    ctx.check("导入后显示邮箱、私钥状态、项目 ID、位置四项",
              not loaded["importing"] and loaded["email"] == "ui-check@ui-check-project.iam.gserviceaccount.com" and "已导入" in (loaded["key"] or "")
              and loaded["project"] == "ui-check-project" and loaded["location"] == "", loaded)
    ctx.check("私钥正文不显示在界面上", VERTEX_FAKE_KEY_BODY not in loaded["text"] and VERTEX_FAKE_KEY_BODY not in (loaded["key"] or ""))
    ctx.check("位置没填时提示必填", "必填" in loaded["text"], loaded["text"][-80:])
    ctx.check("项目 ID 和位置只出现一次（高级区不重复显示）", loaded["duplicated"] == 2, loaded["duplicated"])

    await page.js(set_input(f"{VERTEX_BOX}.querySelector('input[aria-label=\"位置\"]')", "asia-southeast1"))
    await asyncio.sleep(0.3)
    filled = await page.js(VERTEX_STATE)
    ctx.check("填了位置后必填提示消失", filled["location"] == "asia-southeast1" and "必填" not in filled["text"], filled["text"][-80:])
    await page.shot("vertex-account")

    await page.js(click_text(panel, "保存设置"))
    await asyncio.sleep(1.5)
    saved = await page.js("""(async () => {
      const raw = await (await fetch('/api/settings')).text();
      const preset = JSON.parse(raw).apiPresets.find(p => p.providerId === 'vertex-gemini');
      return {raw, preset};
    })()""")
    preset = saved["preset"] or {}
    ctx.check("保存后的预设：服务账号鉴权、Gemini 协议、项目和位置都在",
              preset.get("authStyle") == "vertex_service_account" and preset.get("protocol") == "gemini_generate_content"
              and (preset.get("providerParams") or {}) == {"project": "ui-check-project", "location": "asia-southeast1"},
              {k: preset.get(k) for k in ("authStyle", "protocol", "providerParams", "baseUrl")})
    ctx.check("设置接口返回的内容里没有私钥正文，邮箱还在", VERTEX_FAKE_KEY_BODY not in saved["raw"] and "ui-check@ui-check-project" in saved["raw"])

    await page.goto("/")
    await page.js(click_text("document", "设置"))
    await asyncio.sleep(1)
    await page.js(click_text(panel, "API 预设"))
    await asyncio.sleep(0.5)
    count = await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]').length")
    reopened = {}
    for index in range(count - 1, -1, -1):
        await page.js(f"{BUILT_LIST}.querySelectorAll(':scope > [draggable=true]')[{index}].click()")
        await asyncio.sleep(0.3)
        reopened = await page.js(VERTEX_STATE)
        if reopened.get("present"):
            break
    ctx.check("刷新后再打开：四项还在，私钥显示为已保存",
              reopened.get("present") and not reopened["importing"] and reopened["email"] == "ui-check@ui-check-project.iam.gserviceaccount.com"
              and "已保存" in (reopened["key"] or "") and reopened["project"] == "ui-check-project" and reopened["location"] == "asia-southeast1", reopened)

    await page.js(f"[...{VERTEX_BOX}.querySelectorAll('button')].find(b=>b.innerText.includes('更换')).click()")
    await asyncio.sleep(0.3)
    replacing = await page.js(VERTEX_STATE)
    await page.js(f"[...{VERTEX_BOX}.querySelectorAll('button')].find(b=>b.innerText.includes('取消')).click()")
    await asyncio.sleep(0.3)
    back = await page.js(VERTEX_STATE)
    ctx.check("点「更换」进入导入界面，取消后原账号还在", replacing["importing"] and not back["importing"] and back["email"] == reopened.get("email"), {"replacing": replacing.get("importing"), "back": back.get("email")})
    await ctx.close(page)


CHECKS = {
    "first_load": check_first_load,
    "entry": check_entry,
    "search": check_search,
    "settings": check_settings,
    "built": check_built,
    "drawer": check_drawer_details,
    "vertex": check_vertex_account,
    "core": dom_checks.check_core,
    "modals": dom_checks.check_modals,
    "dev_built": dom_checks.check_dev_built,
    "motion": check_motion,
    "sidebar": check_sidebar,
    "background": check_background,
    "reading": check_reading,
    "saves": check_saves,
    "delete": check_delete,
    "follow": check_follow,
    "version": check_version,
    "themes": dom_checks.check_themes,
    "viewports": dom_checks.check_viewports,
    "long_chat": dom_checks.check_long_chat,
    "errors": dom_checks.check_errors,
    "secrets": dom_checks.check_secrets,
}


async def run(ctx, only):
    for name, fn in CHECKS.items():
        if name not in only:
            continue
        print(f"\n== {name}: {(fn.__doc__ or '').strip()}")
        try:
            await fn(ctx)
        except Exception as error:
            ctx.check(f"{name} 没有跑完", False, repr(error)[:300])
    failed = [name for name, ok in ctx.results if not ok]
    print(f"\n合计 {len(ctx.results)} 项，失败 {len(failed)}")
    for name in failed:
        print(f"  失败：{name}")
    return failed
