"""Regression coverage for the reported chat and settings issues in the production build."""

import json

import dom_checks as dom


async def check_preset_disclosure(ctx):
    """窄屏预设先显示连接和模型，按需查看高级设置和请求诊断。"""
    saved = ctx.api("/api/settings")
    first = {"id": "ui-compact-deepseek", "name": "DeepSeek 测试预设", "providerId": "deepseek",
             "baseUrl": "https://api.deepseek.com", "apiKey": "local-ui-fixture", "protocol": "openai_responses",
             "models": ["deepseek-v4-pro"], "promptCache": {"mode": "explicit"}}
    second = {**first, "id": "ui-compact-other", "name": "另一测试预设", "providerId": None,
              "baseUrl": ctx.mock_state.tts_url, "protocol": "openai_compatible_chat", "models": ["mock"]}
    page = None

    def open_preset(name):
        return f"[...document.querySelectorAll('[draggable=true]')].find(e=>e.textContent.includes({json.dumps(name)}))"

    details = '''(name => [...document.querySelectorAll('.drawer-panel summary')]
      .find(e => e.getClientRects().length && e.textContent.trim() === name))'''
    advanced = f"{details}('高级设置')"
    preview = f"{details}('请求预览')"
    technical = f"{details}('技术详情')"
    try:
        dom.update_settings(ctx, apiPresets=[first, second, *saved["apiPresets"]])
        page = await dom.open_app(ctx, ctx.serve_built(), width=430, height=1024, reduce_motion=True)
        await dom.settings_open(page)
        await page.js("$click(document,'API 预设')")
        row = open_preset(first["name"])
        await page.wait_for(row)
        await page.js(row + ".click()")
        await page.wait_for("document.querySelector('.drawer-panel')?.innerText.includes('deepseek-v4-pro')")
        collapsed = await page.js(f"""(() => {{
          const panel = document.querySelector('.drawer-panel');
          return {advanced}?.parentElement.open === false && {preview}?.parentElement.open === false
            && panel.innerText.includes('获取模型')
            && !['能力来源', '提示词缓存', '显式缓存标记', 'V4.1 Flash', '删除所选'].some(text=>panel.innerText.includes(text));
        }})()""")
        ctx.check("窄屏连接页默认收起高级内容和诊断", collapsed)
        if not collapsed:
            return
        ctx.check("窄屏预设列表随连接表单正常滚动", await page.js(f"""(() => {{
          const list = {row}.parentElement.parentElement;
          const formHeading = document.querySelector('.drawer-panel .preset-editor-heading');
          return formHeading?.textContent.trim() === {json.dumps(first['name'])} && getComputedStyle(list).position !== 'sticky'
            && list.getBoundingClientRect().bottom <= formHeading.getBoundingClientRect().top;
        }})()"""))
        await page.shot("preset-connection-collapsed")

        await page.js(f"{advanced}.focus()")
        await page.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
        await page.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await page.wait_for(f"{advanced}.parentElement.open")
        valid = await page.js(f"""(() => {{const panel = {advanced}.parentElement;
          return !!panel.querySelector('button[aria-label=回传思考内容]')
            && !!$btn(panel, '缓存指南') && !panel.innerText.includes('标记要缓存的消息')
            && panel.scrollWidth <= panel.clientWidth + 1;
        }})()""")
        ctx.check("键盘可展开高级设置，只展示适用选项且无横向溢出", valid)
        await page.js(f"{advanced}.click(); {preview}.click()")
        await page.wait_for(f"{preview}.parentElement.querySelector('dl')?.innerText.includes('OpenAI Responses')")
        await page.wait_for(technical)
        ctx.check("请求预览先显示协议、思考深度与缓存", await page.js(
            f"{technical}.parentElement.open === false && !{preview}.parentElement.innerText.includes('能力来源')"))
        await page.js(f"{technical}.click(); {preview}.parentElement.querySelector('dl').scrollIntoView({{block:'center'}})")
        ctx.check("技术详情展开后可读", await page.js(f"{technical}.parentElement.innerText.includes('能力来源')"))
        await page.shot("preset-request-preview")

        await page.js(open_preset(second["name"]) + ".click()")
        await page.wait_for(f"{preview}.parentElement.open === false")
        await page.js(f"{preview}.click()")
        await page.wait_for(f"{preview}.parentElement.querySelector('dl')?.innerText.includes('OpenAI Chat Completions')")
        ctx.check("切换预设后预览使用当前模型", await page.js(
            f"{preview}.parentElement.innerText.includes('mock') && !{preview}.parentElement.innerText.includes('deepseek-v4-pro')"))
    finally:
        if page:
            await ctx.close(page)
        dom.request(ctx, "PUT", "/api/settings", saved)


async def check_preset_session_binding(ctx):
    """预设文字与键盘入口，及会话读数、草稿和真实请求的连接一致。"""
    saved = ctx.api("/api/settings")
    model = "ui-shared-connection-model"
    first = {"id": "binding-first", "name": "长名称预设：青碧角色对话与故事叙事专用模型",
             "baseUrl": ctx.mock_state.tts_url.replace("/v1", "/binding-first/v1"), "apiKey": "ui-binding-first",
             "protocol": "openai_compatible_chat", "models": [model]}
    second = {**first, "id": "binding-second", "name": "候补模型连接",
              "baseUrl": ctx.mock_state.tts_url.replace("/v1", "/binding-second/v1"), "apiKey": "ui-binding-second"}
    voice = {**first, "id": "binding-voice", "name": "长名称语音预设：旁白和角色语音", "presetKind": "tts"}
    fixture = "BINDING"
    page = card_id = None

    def write(method, path, payload):
        status, _, detail = dom.request(ctx, method, path, payload)
        if status != 200:
            raise RuntimeError(f"{method} {path}: {detail.decode()[:160]}")
        return json.loads(detail)

    try:
        dom.update_settings(ctx, streamEnabled=True, apiPresets=[first, second, voice],
                            llm={**saved["llm"], "defaultModel": model},
                            generationDefaults={"temperature": .7, "top_p": .9, "max_tokens": 2048, "context_size": 8192})
        card_id = write("POST", "/api/characters", {"name": "连接检查角色", "firstMessage": ""})["id"]
        chat = write("POST", "/api/chats", {"characterId": card_id, "title": "会话连接与继承检查"})
        ctx.fixtures[fixture] = chat["id"]
        path = f"/api/chats/{chat['id']}"
        write("POST", path + "/messages", {"role": "assistant", "content": f"【最后一条开头 {fixture}】"})

        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900, reduce_motion=True)
        await dom.enter_chat(ctx, page, fixture)
        await dom.settings_open(page)
        await page.js("$click(document, 'API 预设')")
        row = f"[...document.querySelectorAll('[draggable=true]')].find(r=>r.textContent.includes({json.dumps(first['name'])}))"
        choice = f"{row}.querySelector('.preset-choice')"
        await page.wait_for(choice)
        await page.js(f"{row}.parentElement.previousElementSibling.querySelector('button').focus()")
        await page.key("Tab", 9)
        ctx.check("Tab 从新建进入预设名称按钮", await page.js(f"document.activeElement === {choice}"))
        await page.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
        await page.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await page.wait_for(f"{choice}.getAttribute('aria-current') === 'true'")
        ctx.check("键盘选中的预设在详情显示完整名称及独立的服务类型字段", await page.js(f"""(() => {{
          const toggle = document.querySelector('[role=switch][aria-label="作为 TTS 服务"]');
          const heading = document.querySelector('.preset-editor-heading');
          const type = toggle?.closest('.settings-field')?.parentElement.closest('.settings-field');
          return heading.textContent.trim() === {json.dumps(first['name'])} &&
            type?.innerText.includes('服务类型 · 模型服务') && !type.innerText.includes('预设名称');
        }})()"""))
        geometry = f"""(() => {{
          const name = {choice}.querySelector('.preset-choice-name');
          const r = name.getBoundingClientRect(), button = {row}.querySelector('button[aria-label^=删除预设]');
          const s = getComputedStyle(name), d = button.getBoundingClientRect();
          return {{text: [r.left, r.top, r.width, r.height], lines: s.webkitLineClamp,
                    lineHeight: parseFloat(s.lineHeight), overlay: d.left < r.right, visible: getComputedStyle(button).opacity}};
        }})()"""
        await page.mouse("mouseMoved", 8, 8)
        before = await page.js(geometry)
        point = await page.js(f"""(() => {{const r = {choice}.getBoundingClientRect(); return [r.left + 8, r.top + 8]}})()""")
        await page.mouse("mouseMoved", *point)
        await page.wait_for(f"getComputedStyle({row}.querySelector('button[aria-label^=删除预设]')).opacity === '1'")
        after = await page.js(geometry)
        ctx.check("超长预设名用两行，悬停删除按钮覆盖卡片且文字不重排",
                  before["visible"] == "0" and after["overlay"] and before["text"] == after["text"]
                  and after["lines"] == "2" and abs(after["text"][3] - 2 * after["lineHeight"]) <= 1,
                  [before, after])
        await page.js("""[...document.querySelectorAll('.preset-choice')].find(e=>e.textContent.includes('旁白和角色语音')).click()""")
        ctx.check("切换语音预设后详情类型和提供商同步", await page.js(
            "document.querySelector('.preset-editor-heading').textContent.includes('旁白和角色语音') && "
            "document.querySelector('#settings-panel-presets').innerText.includes('服务类型 · 语音服务') && "
            "document.querySelector('#settings-panel-presets').innerText.includes('TTS 提供商')"))

        async def open_session():
            await dom.settings_open(page)
            await page.js("$click(document, '当前会话')")
            await page.wait_for("document.querySelector('.session-current-connection')")

        async def select_second_model():
            await page.js("document.querySelector('button[aria-label=模型覆盖]').click()")
            option = """[...document.querySelectorAll('[role=listbox][aria-label=模型覆盖] > div')]
              .find(g => g.firstElementChild?.textContent.trim() === '候补模型连接')?.querySelector('[role=option]')"""
            await page.wait_for(option)
            await page.js(f"({option}).click()")
            await page.wait_for("document.querySelector('.session-draft-connection')?.textContent.includes('候补模型连接')")

        await page.js("$click(document, '当前会话')")
        await page.wait_for("document.querySelector('.session-current-connection')")
        ctx.check("会话头部显示真实模型匹配的第一预设，字段显示全局读数", await page.js(f"""(() => {{
          const region = document.querySelector('[aria-label="当前会话的模型与连接"]');
          const field = document.querySelector('input[aria-label=上下文长度]').closest('.settings-field');
          return region.innerText.includes('会话连接与继承检查') && region.innerText.includes({json.dumps(first['name'])})
            && field.innerText.includes('沿用全局 · 8192 tokens');
        }})()"""))
        await select_second_model()
        ctx.check("同模型的候补预设只出现在保存后读数",
                  await page.js(f"document.querySelector('.session-current-connection').textContent.includes({json.dumps(first['name'])})")
                  and not ctx.api(path)["overrides"].get("presetId"))
        await page.js("$click(document.querySelector('.drawer-panel'), '取消')")
        await page.wait_for("document.querySelector('.app-notify-panel')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
        await page.wait_for("!$drawerOpen()")
        await open_session()
        ctx.check("取消后模型和连接恢复到已保存设置", await page.js(
            "!document.querySelector('.session-draft-connection') && document.querySelector('.session-current-connection').textContent.includes('叙事专用模型')"))

        await select_second_model()
        await page.js("""$type(document.querySelector('input[aria-label=上下文长度]'), '0');
          $type(document.querySelector('input[aria-label=Temperature]'), '0.4');""")
        ctx.check("0 关闭会话上下文限制，数值覆盖标明保存后生效",
                  await page.js("""document.querySelector('input[aria-label=上下文长度]').closest('.settings-field').innerText.includes('保存后 · 已关闭') &&
                   document.querySelector('input[aria-label=Temperature]').closest('.settings-field').innerText.includes('保存后 · 会话覆盖 · 0.4')"""))
        await page.js("$click(document.querySelector('.drawer-panel'), '保存设置')")
        await page.wait_for("!$drawerOpen()")
        overrides = ctx.api(path)["overrides"]
        ctx.check("保存后持久化候补预设、温度与显式关闭的上下文限制",
                  overrides["presetId"] == second["id"] and overrides["params"]["context_size"] == 0
                  and overrides["params"]["temperature"] == .4, overrides["params"])
        requests_before = len(ctx.mock_state.seen)
        await dom.send_in_chat(page, "验收实际使用的候补连接")
        await page.wait_for("($rows().at(-1)?.innerText.match(/收音机的声音调小/g) ?? []).length === 2")
        ctx.check("实际生成请求发往读数显示的候补预设", any(
            event["path"] == "/binding-second/v1/chat/completions" and event["auth"] == "Bearer ui-binding-second"
            for event in ctx.mock_state.seen[requests_before:]))

        await open_session()
        await page.js("""$click(document.getElementById('settings-panel-chat'), '恢复沿用全局');
           $type(document.querySelector('input[aria-label=上下文长度]'), '');
           $type(document.querySelector('input[aria-label=Temperature]'), '');""")
        await page.js("$click(document.querySelector('.drawer-panel'), '保存设置')")
        await page.wait_for("!$drawerOpen()")
        overrides = ctx.api(path)["overrides"]
        ctx.check("清除覆盖后模型、预设、温度和上下文恢复继承",
                  overrides["presetId"] is None and all(overrides["params"][field] is None for field in ("model", "temperature", "context_size")),
                  overrides["params"])
    finally:
        if page:
            await ctx.close(page)
        if card_id:
            dom.request(ctx, "DELETE", f"/api/characters/{card_id}")
        ctx.fixtures.pop(fixture, None)
        dom.request(ctx, "PUT", "/api/settings", saved)


async def check_luna_reasoning(ctx):
    """旧会话打开模型面板后显示可用的六档，并选中实际使用的低档。"""
    saved = ctx.api("/api/settings")
    models = ["gpt-6-luna", *(f"ui-list-model-{i:02d}" for i in range(18))]
    preset = {"id": "ui-luna-reasoning", "name": "Luna 检查", "models": models,
              "providerId": "openai-chatgpt", "baseUrl": "https://api.openai.com/v1", "protocol": "openai_responses"}
    fixture = "LUNA"
    card = page = None

    def write(method, path, body):
        status, _, detail = dom.request(ctx, method, path, body)
        if status != 200:
            raise RuntimeError(f"{method} {path}: {detail.decode()[:200]}")
        return json.loads(detail)

    async def scroll_content(selector):
        x, y = await page.js(f"""(() => {{
          const el = {selector}, r = el.getBoundingClientRect();
          el.scrollTop = 0;
          return [r.left + r.width / 2, r.top + r.height / 2];
        }})()""")
        await page.wheel(100, x=x, y=y)
        await page.wait_for(f"{selector}.scrollTop > 0", 3)
        scroll = await page.js(f"{selector}.scrollTop")
        await page.js(f"{selector}.scrollTop = 0")
        return scroll

    try:
        dom.update_settings(ctx, apiPresets=[preset, *saved["apiPresets"]], reasoningEffort="medium")
        card = write("POST", "/api/characters", {"name": "Luna 检查角色", "firstMessage": ""})
        chat = write("POST", "/api/chats", {"characterId": card["id"], "title": "Luna 检查会话"})
        ctx.fixtures[fixture] = chat["id"]
        chat_path = f"/api/chats/{chat['id']}"
        write("PUT", chat_path, {"overrides": {"presetId": preset["id"],
                                             "params": {"model": "gpt-6-luna", "reasoningEffort": "minimal"}}})
        write("POST", chat_path + "/messages", {"role": "assistant", "content": f"【最后一条开头 {fixture}】"})
        page = await dom.open_app(ctx, ctx.serve_built(), width=1100, height=450, reduce_motion=True)
        await dom.enter_chat(ctx, page, fixture)
        await page.js("document.querySelector('.model-control-trigger').click()")
        panel = "document.querySelector('[aria-label=模型控制面板]')"
        group = f"{panel}?.querySelector('[role=radiogroup][aria-label=思考深度]')"
        selected = f"{group}?.querySelector('[aria-checked=true]')"
        await page.wait_for(selected)
        await page.wait_for("performance.getEntriesByType('resource').some(e => e.name.endsWith('/api/llm/resolve-preview'))")
        await page.wait_for(f"!{panel}?.querySelector('.animate-spin')")
        data = await page.js(f"""(() => {{
          const options = [...{group}.querySelectorAll('[role=radio]')];
          return {{choices: options.map(e => e.textContent.trim()),
                   selected: {selected}?.textContent.trim(),
                   diagnosis: {panel}.innerText.includes('协议：')}};
        }})()""")
        ctx.check("Luna 显示六档，最高档标为 Max", data["choices"] == ["关闭", "低", "中", "高", "极高", "Max"], data)
        stored = ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"]
        ctx.check("打开旧会话显示有效低档，保留原会话设置", data["selected"] == "低" and stored == "minimal",
                  {"displayed": data["selected"], "stored": stored})
        ctx.check("聊天模型面板移除重复的请求诊断", not data["diagnosis"], data)
        await page.wait_for(f"Number(getComputedStyle({panel}.closest('.select-dropdown')).opacity) >= .99")
        await page.shot("luna-reasoning")
        read_panel = f"""(() => {{
          const root = {panel}, popup = root.closest('.select-dropdown').getBoundingClientRect();
          const list = root.querySelector('.model-control-list'), search = root.querySelector('input');
          const scrollers = [root, ...root.querySelectorAll('*')].filter(e =>
            /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 1);
          return {{top: popup.top, bottom: popup.bottom, viewport: innerHeight, searchTop: search.getBoundingClientRect().top,
            listHeight: list.clientHeight, oneList: scrollers.length === 1 && scrollers[0] === list,
            gutter: list.offsetWidth - list.clientWidth}};
        }})()"""
        fit = await page.js(read_panel)
        ctx.check("1100×450 浮层完整显示搜索和控件，模型只有一个足够浏览的滚动区",
                  fit["top"] >= 7 and fit["bottom"] <= fit["viewport"] and fit["searchTop"] >= fit["top"]
                  and fit["listHeight"] >= 75 and fit["oneList"] and fit["gutter"] >= 8, fit)
        moved = await scroll_content(f"{panel}.querySelector('.model-control-list')")
        ctx.check("滚轮在浮层内滚动模型列表", moved > 0, moved)

        coords = await page.js(f"""(() => {{
          const center = (button) => {{
            const r = button.getBoundingClientRect();
            return [r.left + r.width / 2, r.top + r.height / 2];
          }};
          const points = [...{group}.querySelectorAll('[role=radio]')].map(center);
          return {{low: points[1], middle: points[2], max: points.at(-1),
                   width: {selected}.getBoundingClientRect().width, height: {selected}.getBoundingClientRect().height}};
        }})()""")
        grip = "document.querySelector('.radio-tags-drag-thumb')"
        await page.wait_for(grip)
        resting_cursor = await page.js(f"getComputedStyle({selected}).cursor")
        await page.mouse("mousePressed", *coords["low"], button="left", buttons=1, clickCount=1)
        await page.wait_for(f"{grip}.classList.contains('radio-tags-drag-thumb--pressed')")
        pressed_cursor = await page.js(f"getComputedStyle({selected}).cursor")
        pressed = await page.js(f"[{grip}.getBoundingClientRect().width, {grip}.getBoundingClientRect().height, {grip}.getBoundingClientRect().left]")
        delta = round((coords["middle"][0] - coords["low"][0]) / 4)
        await page.mouse("mouseMoved", coords["low"][0] + delta, coords["low"][1], button="left", buttons=1)
        slid = await page.js(f"{grip}.getBoundingClientRect().left - {pressed[2]}")
        ctx.check("胶囊按住缩小 2–3 px，档位未切换前也连续跟手",
                  2 <= coords["width"] - pressed[0] <= 3 and 2 <= coords["height"] - pressed[1] <= 3
                  and abs(slid - delta) <= 1 and await page.js(f"{selected}.textContent.trim() === '低'"),
                  {"pressed": pressed[:2], "shift": slid, "mouseDelta": delta})
        await page.mouse("mouseMoved", *coords["max"], button="left", buttons=1)
        await page.wait_for(f"{selected}?.textContent.trim() === 'Max'")
        ctx.check("思考深度悬停、按住和拖动时都使用点击指针",
                  resting_cursor == pressed_cursor == await page.js(f"getComputedStyle({selected}).cursor") == "pointer")
        stored = ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"]
        ctx.check("拖动选中档位即时预览，松手前保留原设置", stored == "minimal", stored)
        await page.mouse("mouseReleased", *coords["max"], button="left", buttons=0, clickCount=1)
        trigger = "document.querySelector('.model-control-trigger')"
        await page.wait_for(f"{trigger}.getAttribute('aria-label').includes('思考：Max（会话）')")
        ctx.check("松手保存离散档位", ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"] == "max")

        ctx.check("拖动结束后焦点跟随选中的档位", await page.js(f"document.activeElement === {selected}"))
        await page.key("ArrowRight", 39)
        await page.key("ArrowRight", 39)
        await page.key("ArrowRight", 39)
        await page.wait_for(f"{trigger}.getAttribute('aria-label').includes('思考：中（会话）')")
        ctx.check("连续按键按档位切换并保存最终值", ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"] == "medium")
        count_previews = "performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/llm/resolve-preview')).length"
        previews_before = await page.js(count_previews)
        await page.js(f"""window.__effortSpinnerSeen = false;
          new MutationObserver(() => {{
            window.__effortSpinnerSeen ||= Boolean({panel}.querySelector('.animate-spin'));
          }}).observe({panel}, {{childList:true, subtree:true}});""")
        await page.mouse("mousePressed", *coords["max"], button="left", buttons=1, clickCount=1)
        await page.mouse("mouseReleased", *coords["max"], button="left", buttons=0, clickCount=1)
        await page.wait_for(f"{trigger}.getAttribute('aria-label').includes('思考：Max（会话）')")
        ctx.check("点击档位按钮仍可直接设置", ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"] == "max")
        await page.wait_for(f"{count_previews} > {previews_before}")
        ctx.check("思考能力预览继续更新，面板没有闪出加载图标", not await page.js("window.__effortSpinnerSeen"))

        await page.mouse("mousePressed", *coords["max"], button="left", buttons=1, clickCount=1)
        await page.mouse("mouseMoved", *coords["middle"], button="left", buttons=1)
        await page.wait_for(f"{selected}?.textContent.trim() === '中'")
        await page.mouse("mouseMoved", *coords["max"], button="left", buttons=1)
        await page.mouse("mouseReleased", *coords["max"], button="left", buttons=0, clickCount=1)
        ctx.check("拖回原档位后保持原设置", ctx.api(chat_path)["overrides"]["params"]["reasoningEffort"] == "max")

        await page.js(f"$click({panel}, '恢复沿用全局')")
        await page.wait_for(f"{trigger}.getAttribute('aria-label').includes('思考：中（全局）')")
        ctx.check("恢复沿用全局后清除会话覆盖", ctx.api(chat_path)["overrides"]["params"].get("reasoningEffort") is None)

        search = f"{panel}.querySelector('input[aria-label=搜索模型]')"
        await page.js(f"$type({search}, 'ui-list-model-1'); {search}.focus()")
        await page.key("ArrowDown", 40)
        await page.key("ArrowDown", 40)
        ctx.check("搜索方向键移动到第二个匹配模型", await page.js(f"""(() => {{
          const active = document.getElementById({search}.getAttribute('aria-activedescendant'));
          return active?.textContent.trim() === 'ui-list-model-11' && document.activeElement === {search};
        }})()"""))
        await page.key("Enter", 13)
        await page.wait_for(f"{trigger}.getAttribute('aria-label').includes('ui-list-model-11')")
        ctx.check("Enter 选中对应模型和连接", ctx.api(chat_path)["overrides"]["params"]["model"] == "ui-list-model-11"
                  and ctx.api(chat_path)["overrides"]["presetId"] == preset["id"])
        await page.key("Escape", 27)
        ctx.check("Esc 关闭模型面板并返回触发器",
                  await page.js(f"{trigger}.getAttribute('aria-expanded') === 'false' && document.activeElement === {trigger}"))
        await page.wait_for(f"!{panel}")

        editor = "document.querySelector('.chat-draft-textarea')"
        read_editor = f"""(() => {{
          const el = {editor};
          const thumb = getComputedStyle(el, '::-webkit-scrollbar-thumb');
          return {{height: el.clientHeight, scroll: el.scrollHeight, gutter: el.offsetWidth - el.clientWidth,
                   thumbColor: thumb.backgroundColor,
                   toolbarGap: el.closest('.chat-input-card-morph').getBoundingClientRect().bottom
                     - {trigger}.getBoundingClientRect().bottom}};
        }})()"""
        empty = await page.js(read_editor)
        two_lines = json.dumps("第一行\n第二行")
        await page.js(f"$type({editor}, {two_lines})")
        two = await page.js(read_editor)
        sample = json.dumps("第一行\n第二行\n第三行")
        await page.js(f"$type({editor}, {sample})")
        middle = await page.js(read_editor)
        draft = "\n".join(f"长草稿第 {i} 行" for i in range(1, 21))
        await page.js(f"$type({editor}, {json.dumps(draft)})")
        long = await page.js(read_editor)
        ctx.check("两行以内输入区等高，增加第三行开始增高，超过上限后可滚动",
                  empty["height"] == two["height"] < middle["height"] < long["height"] < 130 and long["scroll"] > long["height"]
                  and long["gutter"] >= 8 and long["thumbColor"] != "rgba(0, 0, 0, 0)"
                  and abs(long["toolbarGap"] - empty["toolbarGap"]) <= 2,
                  [empty, two, middle, long])
        await page.shot("desktop-short-long-draft")
        send_contrast = """(() => {const b = document.querySelector('.chat-action-button--primary');
          const s = getComputedStyle(b); return $contrast($rgb(s.color), $rgb(s.backgroundColor));})()"""
        ctx.check("暗色发送按钮文字对比达到 4.5:1", await page.js(send_contrast) >= 4.5)

        dom.update_settings(ctx, themeMode="light")
        await dom.goto_app(page)
        await dom.enter_chat(ctx, page, fixture)
        await page.js(f"$type({editor}, {json.dumps(draft)}); {trigger}.click()")
        await page.wait_for(f"{panel} && Number(getComputedStyle({panel}.closest('.select-dropdown')).opacity) >= .99")
        bright = await page.js(read_panel)
        ctx.check("亮色短窗口也保留搜索和有实际宽度的同一个滚动区",
                  bright["top"] >= 7 and bright["oneList"] and bright["gutter"] >= 8, bright)
        await page.shot("desktop-short-model-light")
        await page.key("Escape", 27)
        await page.wait_for(f"!{panel}")
        bright = await page.js(read_editor)
        ctx.check("亮色长草稿滚动条可见，发送按钮文字对比达到 4.5:1",
                  bright["gutter"] >= 8 and bright["scroll"] > bright["height"] and await page.js(send_contrast) >= 4.5, bright)
        await page.shot("desktop-short-long-draft-light")
        moved = await scroll_content(editor)
        ctx.check("滚轮在可编辑区域内滚动长草稿", moved > 0, moved)
    finally:
        if page:
            await ctx.close(page)
        if card:
            dom.request(ctx, "DELETE", f"/api/characters/{card['id']}", None)
        dom.request(ctx, "PUT", "/api/settings", saved)


async def check_chat_followup(ctx):
    """Unsaved keys, model controls, message actions, error layers, groups and Janitor Bridge."""
    saved = ctx.api("/api/settings")
    models = [f"ui-regression-model-{index}" for index in range(1, 8)]
    preset = {"id": "ui-nov23-draft", "name": "开发验收预设", "models": models,
              "baseUrl": ctx.mock_state.tts_url.replace("/v1", "/draft/v1"), "apiKey": "draft-invalid-key"}
    chat_preset = {**preset, "id": "ui-nov23-chat", "name": "聊天验收预设", "baseUrl": ctx.mock_state.tts_url}
    page = None
    card = None
    fixture = "NOV23"
    ctx.mock_state.draft_model_key_checks.clear()

    def write(method, path, body):
        status, _, detail = dom.request(ctx, method, path, body)
        if status != 200:
            raise RuntimeError(f"{method} {path}: {detail.decode()[:200]}")
        return json.loads(detail)

    try:
        dom.update_settings(ctx, streamEnabled=True, apiPresets=[chat_preset, preset, *saved["apiPresets"]],
                            llm={**saved["llm"], "usedModels": models})
        card = write("POST", "/api/characters", {
            "name": "回归测试角色：这是用于检查长角色卡排版的名字",
            "description": "这段角色简介会换行，以便核对编辑和删除胶囊出现前后的文字区域宽度是否相同。" * 2,
            "firstMessage": "",
        })
        chat = write("POST", "/api/chats", {"characterId": card["id"], "title": "回归测试会话"})
        ids = {"characterId": card["id"], "memberIds": [card["id"]]}
        for index in range(6):
            write("POST", "/api/chats", {**ids, "isGroup": True, "title": f"回归测试群聊 {index}"})
        ctx.fixtures[fixture] = chat["id"]
        chat_path = f"/api/chats/{chat['id']}"
        write("PUT", chat_path, {"overrides": {"presetId": chat_preset["id"], "params": {"model": models[0]}}})
        history = write("POST", chat_path + "/messages", {"role": "assistant", "content": f"【最后一条开头 {fixture}】回归测试。"})
        memory_anchor = history["messages"][-1]["id"]
        write("PUT", chat_path, {"overrides": {"presetId": chat_preset["id"], "params": {"model": models[0]},
                                             "longTermMemory": "设置草稿测试记忆", "prompt": "保存前提示词"}})

        page = await dom.open_app(ctx, ctx.serve_built(), width=1120, reduce_motion=True)
        await dom.enter_chat(ctx, page, fixture)
        character = f"""document.querySelector('[data-character-id="{card['id']}"]')"""
        role_layout = f"""(() => {{
          const card = {character};
          const text = card.querySelector('.sidebar-role-text');
          const box = text.getBoundingClientRect(), button = text.querySelector('button');
          const leading = document.createRange(); leading.selectNodeContents(button);
          const capsule = card.querySelector('.sidebar-role-capsule');
          return {{x: box.x, y: box.y, width: box.width, height: box.height, textWidth: leading.getBoundingClientRect().width,
            padding: getComputedStyle(text).paddingInlineEnd, opacity: getComputedStyle(capsule).opacity,
            overlaid: capsule.getBoundingClientRect().left < box.right}};
        }})()"""
        await page.mouse("mouseMoved", 8, 8)
        before = await page.js(role_layout)
        point = await page.js(f"""(() => {{
          const rect = {character}.getBoundingClientRect(); return [rect.left + 22, rect.top + 20];
        }})()""")
        await page.mouse("mouseMoved", *point)
        await page.wait_for(f"getComputedStyle({character}.querySelector('.sidebar-role-capsule')).opacity === '1'")
        after = await page.js(role_layout)
        ctx.check("角色卡悬停操作胶囊盖在内容上，标题和简介范围不变",
                  before["opacity"] == "0" and after["overlaid"]
                  and all(before[key] == after[key] for key in ("x", "y", "width", "height", "textWidth", "padding")),
                  [before, after])
        await page.shot("role-card-hover-overlay")
        await page.mouse("mouseMoved", 8, 8)
        group_selector = "[...document.querySelectorAll('aside span.truncate')].filter(e=>e.textContent.trim().startsWith('回归测试群聊'))"
        expand = "document.querySelector('aside button[aria-expanded][aria-label^=展开其余]')"
        await page.wait_for(expand)
        ctx.check("群聊默认折叠到不超过四条", 0 < await page.js(group_selector + ".length") <= 4)
        await page.js(expand + ".click()")
        ctx.check("展开可访问六条新增群聊", await page.js(group_selector + ".length") == 6)
        await page.js("document.querySelector('aside button[aria-label=收起群聊]').click()")

        await page.js("document.querySelector('.model-control-trigger').click()")
        await page.wait_for("document.querySelector('[aria-label=模型控制面板]')")
        result = await page.js("""(() => {
          const panel = document.querySelector('[aria-label=模型控制面板]');
          const list = panel.querySelector('.model-control-list');
          const recent = list.querySelector('[role=group][aria-label=最近使用]');
          const count = recent?.querySelectorAll('[role=option]').length;
          const labelX = (text) => {
            const element = [...panel.querySelectorAll('span,div')].find(e =>
              [...e.childNodes].some(node=>node.nodeType===Node.TEXT_NODE && node.textContent.trim()===text));
            const node = [...element.childNodes].find(node=>node.nodeType===Node.TEXT_NODE && node.textContent.trim()===text);
            const range = document.createRange();
            range.setStart(node, node.textContent.indexOf(text));
            range.setEnd(node, node.textContent.indexOf(text)+text.length);
            return range.getBoundingClientRect().left;
          };
          const left = ['思考', '思考深度', 'Fast 模式'].map(labelX);
          const selected = [...list.querySelectorAll('[aria-selected=true]')];
          return {count, icons:panel.querySelectorAll('.lucide-brain').length, alignment: Math.max(...left) - Math.min(...left),
            selected: selected.map(e => e.parentElement.getAttribute('aria-label'))};
        })()""")
        ctx.check("模型面板仅显示最近五个模型", result["count"] == 5, result)
        ctx.check("只保留一个思考图标，思考、思考深度和 Fast 模式文字左对齐",
                  result["icons"] == 1 and result["alignment"] <= 1, result)
        ctx.check("最近使用的重复模型仅在实际连接组标为已选", result["selected"] == [chat_preset["name"]], result)
        await page.wait_for("Number(getComputedStyle(document.querySelector('[aria-label=模型控制面板]').closest('.select-dropdown')).opacity) >= .99")
        await page.shot("nov23-model-panel")
        await page.key("Escape", 27)

        await dom.settings_open(page)
        await page.js("$click(document,'API 预设')")
        row = f"[...document.querySelectorAll('[draggable=true]')].find(e=>e.textContent.includes({json.dumps(preset['name'])}))"
        await page.wait_for(row)
        await page.js(f"{row}.click()")
        fetch_models = "$click(document.querySelector('.drawer-panel'), '获取模型')"
        await page.js(fetch_models)
        await page.wait_for("document.querySelector('.app-notify-panel')?.innerText.includes('获取模型失败')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
        await page.wait_for("!document.querySelector('.app-notify-panel')")
        key_field = "[...document.querySelectorAll('button[aria-label=\"显示 API Key\"]')].find(e=>e.offsetParent).parentElement.querySelector('input')"
        await page.js(f"$type({key_field}, 'draft-valid-key')")
        await page.wait_for(key_field + ".value === 'draft-valid-key'")
        await page.js(fetch_models)
        await page.wait_for("document.querySelector('[aria-labelledby=model-selector-title]') || document.querySelector('.app-notify-panel')")
        ctx.check("模型目录先拒绝旧密钥，再接受草稿密钥",
                  ctx.mock_state.draft_model_key_checks == [False, True], ctx.mock_state.draft_model_key_checks)
        await page.wait_for("document.querySelector('[aria-labelledby=model-selector-title]')?.innerText.includes('mock')")
        saved_preset = next(item for item in ctx.api("/api/settings")["apiPresets"] if item["id"] == preset["id"])
        ctx.check("更换草稿密钥后可立即获取模型，保存值保持原样", saved_preset["apiKey"] == "draft-invalid-key")
        await page.js("document.querySelector('button[aria-label=关闭模型选择弹窗]').click()")
        await page.wait_for("!document.querySelector('#model-selector-title')")
        await page.key("Escape", 27)
        await page.wait_for("document.querySelector('.app-notify-panel')?.innerText.includes('放弃未保存更改')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
        await page.wait_for("!$drawerOpen()")

        drawer = "document.querySelector('.drawer-panel')"
        prompt = f"{drawer}.querySelector('textarea[placeholder=留空则使用角色默认提示词]')"
        anchor_hint = f"{drawer}.querySelector('.memory-anchor-hint')"
        original_prompt = "保存前提示词"
        original_anchor = None
        for action, next_anchor in [("从已存记忆处截断", memory_anchor), ("恢复完整上下文", None)]:
            for commit in (False, True):
                await dom.settings_open(page)
                await page.js("$click(document, '当前会话')")
                await page.wait_for(f"{prompt} && {prompt}.offsetParent")
                if not await page.js(f"{prompt}.value === {json.dumps(original_prompt)} && !!{anchor_hint} === {json.dumps(bool(original_anchor))}"):
                    raise RuntimeError("重开的会话设置与持久化的草稿基线不一致")
                updated_prompt = f"{action}后保存的提示词"
                await page.js(f"$type({prompt}, {json.dumps(updated_prompt)}); $click({drawer}, {json.dumps(action)})")
                await page.wait_for(f"!!{anchor_hint} === {json.dumps(bool(next_anchor))}")
                before_save = ctx.api(chat_path)["overrides"]
                ctx.check(f"{action}仅修改草稿并显示未保存状态",
                          before_save["prompt"] == original_prompt and before_save.get("contextStartMessageId") == original_anchor
                          and await page.js(f"{drawer}.innerText.includes('有未保存修改')"), before_save.get("contextStartMessageId"))
                if commit:
                    await page.js(f"$click({drawer}, '保存设置')")
                    original_prompt, original_anchor = updated_prompt, next_anchor
                else:
                    await page.js(f"$click({drawer}, '取消')")
                    await page.wait_for("document.querySelector('.app-notify-panel')?.innerText.includes('放弃未保存更改')")
                    await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
                await page.wait_for("!$drawerOpen()")
                saved_override = ctx.api(chat_path)["overrides"]
                ctx.check(f"{action}后{'保存两处改动' if commit else '取消两处改动'}",
                          saved_override["prompt"] == original_prompt and saved_override.get("contextStartMessageId") == original_anchor
                          and saved_override.get("presetId") == chat_preset["id"]
                          and saved_override["params"]["model"] == models[0],
                          {key: saved_override.get(key) for key in ("prompt", "contextStartMessageId", "presetId")})
        await dom.settings_open(page)
        await page.js("$click(document, '当前会话')")
        await page.wait_for(f"{prompt} && {prompt}.offsetParent")
        ctx.check("重开设置确认恢复完整上下文和提示词均已保存",
                  await page.js(f"{prompt}.value === {json.dumps(original_prompt)} && !{anchor_hint}"))
        await page.key("Escape", 27)
        await page.wait_for("!$drawerOpen()")

        ctx.mock_state.tps = 400
        ctx.mock_state.reply_override = (
            "- **流式标题：**已收到完整标题。\n\n" + ("余下的正文继续输出。" * 55)
            + "\n\n来源： [本地排版验收](http://127.0.0.1/reading)"
        )
        await dom.send_in_chat(page, "验证生成中的操作锁定和生成后的缓存信息。")
        await page.wait_for("$btn($rows()[0], '编辑')?.disabled")
        heading = "$rows().at(-1)?.querySelector('.stream-markdown li strong')?.textContent === '流式标题'"
        await page.wait_for(heading)
        ctx.check("流式输出中中文列表标题已加粗", await page.js("$btn($rows()[0], '编辑')?.disabled"))
        await page.wait_for("$rows().at(-1)?.querySelector('.message-context-usage') && !$btn($rows()[0], '编辑')?.disabled")
        ctx.check("流式完成后加粗格式保持一致", await page.js(heading))
        ctx.mock_state.reply_override = None
        ctx.mock_state.tps = 700
        layout_probe = """(() => {const row = $rows().at(-1);
          const footer = row.querySelector('.message-footer');
          const usage = row.querySelector('.message-context-usage');
          const toolbar = row.querySelector('.message-action-toolbar');
          const s = getComputedStyle(usage), u = usage.getBoundingClientRect(), t = toolbar.getBoundingClientRect();
          const origin = footer.getBoundingClientRect();
          const labelStart = (el) => {
            const range = document.createRange(); range.selectNodeContents(el);
            return range.getBoundingClientRect().left;
          };
          const actions = row.querySelector('.message-action-toolbar').getBoundingClientRect();
          return {
            format: usage.textContent.trim() === '12.4K 上下文  已缓存 10.5K' &&
            s.backgroundColor === 'rgba(0, 0, 0, 0)' && s.borderTopWidth === '0px' &&
            !row.innerText.includes('生成详情'),
            size: parseFloat(s.fontSize), centerDelta: Math.abs((u.top + u.bottom - t.top - t.bottom) / 2),
            textDelta: Math.abs(labelStart(usage) - labelStart($btn(row, '重写'))),
            clearsToolbar: labelStart(usage) >= t.right + 3,
            positions: [actions.left - origin.left, actions.top - origin.top, u.left - origin.left, u.top - origin.top],
            interactive: ['分支','重写','编辑','删除'].every(text=>{const button=$btn(row,text);return button && !button.disabled})
          };
        })()"""
        await page.mouse("mouseMoved", 1, 1)
        layout = await page.js(layout_probe)
        ctx.check("用量文字与工具栏同排，归位时对齐首个操作文字，字号 10 px",
                  layout["format"] and layout["interactive"] and layout["size"] == 10
                  and layout["centerDelta"] <= 1 and layout["textDelta"] <= 1, layout)
        hover_point = await page.js("""(() => {
          const row = $rows().at(-1);
          const bubble = row.querySelector('.message-bubble');
          bubble.scrollIntoView({block:'center', behavior:'instant'});
          const r = bubble.getBoundingClientRect();
          return [r.left + r.width/2, r.top + r.height/2];
        })()""")
        await page.mouse("mouseMoved", *hover_point)
        await page.wait_for("$rows().at(-1).matches(':hover')")
        moved = await page.js(layout_probe)
        ctx.check("悬停时用量移到操作区右侧，工具栏位置固定",
                  moved["clearsToolbar"] and moved["centerDelta"] <= 1
                  and moved["positions"][:2] == layout["positions"][:2], moved)
        await page.mouse("mouseMoved", 1, 1)
        await page.wait_for("!$rows().at(-1).matches(':hover')")
        ctx.check("离开消息后用量归位", (await page.js(layout_probe))["positions"] == layout["positions"])
        await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "no-preference"}])
        ctx.check("用量以单条无延时的贝塞尔曲线过渡",
                  await page.js("""(() => {
                    const usage = $rows().at(-1).querySelector('.message-context-usage');
                    const style = getComputedStyle(usage);
                    return style.transitionProperty === 'transform' && style.transitionDelay === '0s'
                      && style.transitionTimingFunction.startsWith('cubic-bezier(');
                  })()"""))
        await page.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        sources = "$rows().at(-1).querySelector('.message-web-source-toggle')"
        await page.wait_for(sources)
        await page.js(f"{sources}.click()")
        opened = await page.js(layout_probe)
        ctx.check("展开来源后读数和常用按钮位置稳定", opened["positions"] == layout["positions"], opened)
        await page.js(f"{sources}.click()")

        ctx.mock_state.fault = "http401"
        await dom.send_in_chat(page, "验证错误弹层和行内重试。")
        await page.wait_for("document.querySelector('button[aria-label=关闭错误提示]') && $btn($rows().at(-1),'重试')")
        retry = await page.js("""(() => {const row=$rows().at(-1), retry=$btn(row,'重试'), edit=$btn(row,'编辑');
          return retry.parentElement===edit.parentElement && retry.classList.contains('btn-ghost');
        })()""")
        ctx.check("重试与编辑同一行并使用同款操作按钮", retry)
        await dom.settings_open(page)
        layer = await page.js("""(() => {
          const close = document.querySelector('button[aria-label=关闭错误提示]');
          const panel = close.closest('.surface-panel'), rect=close.getBoundingClientRect();
          return getComputedStyle(panel).backdropFilter.includes('blur(')
            && close.contains(document.elementFromPoint(rect.x + rect.width/2, rect.y + rect.height/2));
        })()""")
        ctx.check("错误提示在设置抽屉上方且背景模糊", layer)
        await page.shot("nov23-error-drawer")
        await page.key("Escape", 27)
        await page.wait_for("!$drawerOpen()")
        await page.js("document.querySelector('button[aria-label=关闭错误提示]')?.click()")
        ctx.mock_state.fault = None
        await page.js("$click($rows().at(-1), '重试')")
        await page.wait_for("$rows().at(-1)?.querySelector('.message-context-usage')")
        ctx.check("恰好 10000 保留整数，较小的计数不加单位", await page.js(
            "$rows().at(-1).querySelector('.message-context-usage').textContent.trim() === '10000 上下文  已缓存 12'"))

        web_search_button = "document.querySelector('button[aria-label=网络搜索]:enabled')"
        await page.wait_for(web_search_button)
        await page.js(web_search_button + ".click()")
        pressed = web_search_button + ".getAttribute('aria-pressed')"
        await page.wait_for(f"{pressed} === 'true'")
        ctx.check("开启聊天联网只切换地球按钮", await page.js(
            "!document.querySelector('[aria-label=会话联网来源]') && !document.querySelector('.chat-input-morph-wrap')?.innerText.includes('联网来源')"))
        await page.js(web_search_button + ".click()")
        await page.wait_for(f"{pressed} === 'false'")

        await page.js("""window.__ST_JANITOR_BRIDGE_INSTALLED__ = true;
          window.__ST_JANITOR_BRIDGE_VERSION__ = '0.1.10'; $click(document, '更多操作');""")
        import_button = "[...document.querySelectorAll('[role=menuitem]')].find(e=>e.querySelector('.header-more-menu__label')?.textContent.trim()==='导入会话')"
        await page.wait_for(import_button)
        await page.js(import_button + ".click()")
        await page.wait_for("$modal('导入')")
        status = await page.js("""(() => { const modal=$modal('导入'), button=$btn(modal,'打开并抓取');
          return button.disabled && modal.innerText.includes('0.1.10') && modal.innerText.includes('0.1.11')
            && modal.innerText.includes('extensions/simpletavern-janitor-bridge') && !!modal.querySelector('a[href*=github]');
        })()""")
        ctx.check("旧版 Janitor Bridge 阻止跳转并显示安装入口及目录", status)
        await page.js("""window.__ST_JANITOR_BRIDGE_VERSION__='0.1.11';
          window.dispatchEvent(new Event('simpletavern:janitor-bridge-ready'));""")
        await page.wait_for("!$btn($modal('导入'),'打开并抓取')?.disabled")
        handoff = await page.js("""(() => {
          const modal = $modal('导入');
          window.open = (url) => { window.janitorCaptureUrl = new URL(url); };
          $type(modal.querySelector('input[placeholder*="/characters/"]'), 'https://janitorai.com/characters/fixture');
          $click(modal, '打开并抓取');
          const target = window.janitorCaptureUrl;
          return target?.searchParams.get('_st_char_html')==='1'
            && target.searchParams.get('_st_app_base')===location.origin;
        })()""")
        ctx.check("检测到新版本后可打开抓取", handoff)
    finally:
        ctx.mock_state.fault = None
        ctx.mock_state.tps = 1500
        ctx.mock_state.reply_override = None
        if page:
            await ctx.close(page)
        ctx.fixtures.pop(fixture, None)
        if card:
            dom.request(ctx, "DELETE", f"/api/characters/{card['id']}")
        dom.request(ctx, "PUT", "/api/settings", saved)
