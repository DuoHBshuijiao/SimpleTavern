"""Check assistant controls and Settings drawer motion in the production build."""

import asyncio
import json
from pathlib import Path

import dom_checks as dom


PANEL = 'document.querySelector("aside[aria-label=聊天助手]")'
OPEN_ASSISTANT = "[...document.querySelectorAll('button[aria-label=打开聊天助手]')].find(e=>e.getClientRects().length).click()"
DRAWER = 'document.querySelector(".drawer-panel")'
OPEN_DRAWER = "$click(document, '设置')"
CLOSE_DRAWER = f"{DRAWER}.querySelector('[aria-label=关闭设置抽屉]').click()"
MODEL_DIALOG = "$modal('聊天助手设置')"
EFFORT_GROUP = f"{MODEL_DIALOG}?.querySelector('[role=radiogroup][aria-label=思考深度]')"
SETTINGS_ICON = "button[aria-label=聊天助手设置]"


async def open_assistant(page):
    await page.js(OPEN_ASSISTANT)
    await page.wait_for(f"{PANEL} && !{PANEL}.inert")


async def check_assistant_model_surface(ctx):
    """Two entry points, scoped capabilities, the draft controls and an actual assistant request."""
    settings = ctx.api('/api/settings')
    assistant = ctx.api('/api/assistant/settings')
    model, luna = 'deepseek-v4-pro', 'gpt-6-luna'
    preset = {'id': 'assistant-model-ui', 'name': '助手测试连接', 'baseUrl': ctx.mock_state.tts_url.replace('/v1', '/assistant-check/v1'),
              'apiKey': 'ui-assistant-model-key', 'protocol': 'openai_compatible_chat', 'providerId': 'deepseek', 'models': [model]}
    subscription = {**preset, 'id': 'assistant-luna-ui', 'name': 'Luna 能力预览', 'models': [luna],
                    'protocol': 'openai_responses', 'providerId': 'openai-chatgpt'}
    priority = {**subscription, 'id': 'assistant-fast-ui', 'name': '官方 Fast 连接', 'models': ['gpt-5.4'], 'providerId': 'openai'}
    page = card = None

    def write(path, value, method='PUT'):
        status, _, data = dom.request(ctx, method, path, value)
        if status != 200:
            raise RuntimeError(f'{method} {path} returned {status}')
        return json.loads(data)

    async def model_dialog():
        await page.js(f"{PANEL}.querySelector('{SETTINGS_ICON}').click()")
        await page.wait_for(EFFORT_GROUP)

    async def click_with_mouse(element):
        point = await page.js(f"""(() => {{
          const target = {element}; target.scrollIntoView({{block: 'nearest'}});
          const rect = target.getBoundingClientRect();
          return [rect.left + rect.width / 2, rect.top + rect.height / 2];
        }})()""")
        await page.mouse('mouseMoved', *point)
        await page.mouse('mousePressed', *point, button='left', buttons=1, clickCount=1)
        await page.mouse('mouseReleased', *point, button='left', clickCount=1)

    async def choose_model(scope, preset_name, model_name):
        opener = f"$btn({scope}, '选择助手模型')"
        listbox = "document.querySelector('[role=listbox][aria-label=助手模型]')"
        focused_search = f"document.activeElement === {listbox}?.parentElement.querySelector('input')"
        await click_with_mouse(opener)
        await page.wait_for(focused_search, 3)
        await asyncio.sleep(.32)
        ctx.check('真实鼠标点击空态按钮后，下拉保持打开且搜索框保持焦点', await page.js(focused_search))
        await page.key('Escape', 27)
        await page.wait_for(f"!{listbox}")
        ctx.check('Esc 关闭下拉并把焦点交还空态按钮', await page.js(f'document.activeElement === {opener}'))

        await click_with_mouse(opener)
        await page.wait_for(focused_search)
        await click_with_mouse(f"{scope}.querySelector('.assistant-empty-state p')")
        await page.wait_for(f"!{listbox}")
        ctx.check('点击下拉外部仍可关闭模型选择器', True)

        await click_with_mouse(opener)
        await page.wait_for(focused_search)
        await page.send('Input.insertText', text=model_name)
        option = f"[...{listbox}.children].find(el=>el.firstElementChild?.textContent.trim() === '{preset_name}')?.querySelector('[role=option]')"
        await page.wait_for(option)
        await click_with_mouse(f'({option})')

    try:
        dom.update_settings(ctx, llm={**settings['llm'], 'defaultModel': ''}, reasoningEffort='high',
                            apiPresets=[preset, subscription, priority], streamEnabled=True, themeMode='light', themeId='teal')
        blank = {**assistant, 'model': None, 'presetId': None, 'reasoningEffort': None, 'temperature': None, 'fastMode': None}
        write('/api/assistant/settings', blank)
        card = write('/api/characters', {'name': '助手设置验收角色', 'firstMessage': ''}, 'POST')['id']
        chat = write('/api/chats', {'characterId': card, 'title': '助手设置验收会话'}, 'POST')['id']
        ctx.fixtures['ASSIST_UI'] = chat
        write(f'/api/chats/{chat}/messages', {'role': 'assistant', 'content': '【最后一条开头 ASSIST_UI】'}, 'POST')

        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900, reduce_motion=True)
        await dom.enter_chat(ctx, page, 'ASSIST_UI')
        await open_assistant(page)
        await page.wait_for(f"$btn({PANEL}, '选择助手模型')")
        ctx.check('主聊天空态表达当前会话任务，助手设置使用齿轮', await page.js(
            f"{PANEL}.innerText.includes('总结当前会话') && !!{PANEL}.querySelector('.lucide-settings')"))
        await choose_model(PANEL, preset['name'], model)
        await page.wait_for(f"!$btn({PANEL}, '选择助手模型')")
        ctx.check('选择模型后主助手使用对应预设', ctx.api('/api/assistant/settings')['presetId'] == preset['id'])

        await model_dialog()
        model_info = f"{MODEL_DIALOG}.querySelector('.assistant-model-summary').innerText"
        temp = f"{MODEL_DIALOG}.querySelector('input[aria-label=温度]')"
        fast = f"{MODEL_DIALOG}.querySelector('[role=switch][aria-label=\"Fast 模式\"]')"
        checked = f"{EFFORT_GROUP}.querySelector('[aria-checked=true]')"
        ctx.check('显示实际模型、预设和共享作用范围', await page.js(
            f"['{model}', '{preset['name']}', '主聊天助手和角色工作区共用'].every(s=>{model_info}.includes(s))"))
        ctx.check('沿用全局高档时提示温度被忽略，Fast 不可用且没有价格提示', await page.js(
            f"{checked}.innerText === '高' && {temp}.disabled && {temp}.placeholder === '使用模型默认值' && {fast}.disabled && "
            f"{MODEL_DIALOG}.innerText.includes('请求会忽略温度') && !{MODEL_DIALOG}.innerText.includes('2×')"))

        await page.js(f"{checked}.focus()")
        await page.key('ArrowLeft', 37)
        ctx.check('方向键移动焦点和档位，尚未保存', await page.js(
            f"document.activeElement === {checked} && {checked}.innerText !== '高' && !!$btn({MODEL_DIALOG}, '恢复沿用全局')")
            and ctx.api('/api/assistant/settings')['reasoningEffort'] is None)
        await page.js(f"$click({MODEL_DIALOG}, '取消')")
        await page.wait_for(f'!{MODEL_DIALOG}')
        await model_dialog()
        ctx.check('取消后恢复继承的高档', await page.js(f"{checked}.innerText === '高' && !$btn({MODEL_DIALOG}, '恢复沿用全局')"))

        await page.js(f"[...{EFFORT_GROUP}.querySelectorAll('[role=radio]')].find(btn=>btn.innerText === '关闭').click()")
        await page.wait_for(f'!{temp}.disabled')
        await page.js(f"$type({temp}, '0.4')")
        drag = await page.js(f"""(() => {{
          const selected = {checked}.getBoundingClientRect();
          const target = [...{EFFORT_GROUP}.querySelectorAll('[role=radio]')].find(btn=>btn.innerText === '高').getBoundingClientRect();
          return {{x: selected.left + selected.width / 2, y: selected.top + selected.height / 2,
            width: selected.width, target: target.left + target.width / 2}};
        }})()""")
        grip = f"{MODEL_DIALOG}.querySelector('.model-control-effort-grip')"
        await page.mouse('mousePressed', drag['x'], drag['y'], button='left', buttons=1, clickCount=1)
        await page.wait_for(grip)
        pressed = await page.js(f'{grip}.getBoundingClientRect().toJSON()')
        movements = []
        for ratio in (.2, .4, .6, .8):
            await page.mouse('mouseMoved', drag['x'] + (drag['target'] - drag['x']) * ratio, drag['y'], button='left', buttons=1)
            movements.append(await page.js(f'{grip}.getBoundingClientRect().left'))
            await page.shot(f'assistant-effort-drag-{int(ratio * 10)}')
        await page.mouse('mouseReleased', drag['target'], drag['y'], button='left', clickCount=1)
        await page.wait_for(f"!{grip} && {checked}.innerText === '高'")
        await page.shot('assistant-effort-drag-release')
        ctx.check('胶囊按下缩小 2.5 px，拖动连续，松手吸附，温度草稿保留',
                  abs(drag['width'] - pressed['width'] - 2.5) < .2 and all(a < b for a, b in zip(movements, movements[1:]))
                  and await page.js(f"{temp}.value === '0.4' && {temp}.disabled")
                  and ctx.api('/api/assistant/settings')['temperature'] is None, [pressed, movements])
        await page.js(f"$click({MODEL_DIALOG}, '保存')")
        await page.wait_for(f'!{MODEL_DIALOG}')
        updated = ctx.api('/api/assistant/settings')
        ctx.check('保存后助手高档和温度都写入设置', updated['reasoningEffort'] == 'high' and updated['temperature'] == .4)

        seen = len(ctx.mock_state.seen)
        await page.js(f"$type({PANEL}.querySelector('textarea'), '用测试连接生成回覆')")
        await page.wait_for(f"!$btn({PANEL}, '发送').disabled")
        await page.js(f"$click({PANEL}, '发送')")
        await page.wait_for(f"{PANEL}.innerText.includes('收音机的声音调小')")
        requests = [entry for entry in ctx.mock_state.seen[seen:] if entry['path'] == '/assistant-check/v1/chat/completions']
        ctx.check('实际助手请求使用所选连接和高档，且省略温度', bool(requests) and all(
            entry['model'] == model and entry['auth'] == 'Bearer ui-assistant-model-key' and entry['effort'] == 'high'
            and entry['temperature'] is None for entry in requests))

        await model_dialog()
        await page.js(f"$click({MODEL_DIALOG}, '恢复沿用全局'); $click({MODEL_DIALOG}, '保存')")
        await page.wait_for(f'!{MODEL_DIALOG}')
        ctx.check('恢复沿用全局可实际清除思考深度覆盖', ctx.api('/api/assistant/settings')['reasoningEffort'] is None)
        await ctx.close(page)
        page = None

        write('/api/assistant/settings', blank)
        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900, reduce_motion=True)
        await dom.enter_chat(ctx, page, 'ASSIST_UI')
        await page.js("document.querySelector('[data-character-id] button[aria-label=编辑角色]').click()")
        editor = "$modal('编辑角色')"
        await page.wait_for(f"{editor}?.querySelector('.assistant-empty-icon')")
        ctx.check('角色右栏空态使用主题色 SVG 和独立的角色卡文案', await page.js(f"""(() => {{
          const icon = {editor}.querySelector('.assistant-empty-icon svg');
          const sample = document.createElement('span'); sample.style.color = 'var(--color-brand)'; document.body.append(sample);
          const ok = getComputedStyle(icon).color === getComputedStyle(sample).color && {editor}.innerText.includes('完善角色卡');
          sample.remove(); return ok;
        }})()"""))
        await choose_model(editor, subscription['name'], luna)
        await page.wait_for(f"!$btn({editor}, '选择助手模型')")
        await page.js(f"{editor}.querySelector('{SETTINGS_ICON}').click()")
        await page.wait_for(EFFORT_GROUP)
        ctx.check('角色编辑器使用同一助手设置，Luna 档位按连接能力过滤', await page.js(
            f"{model_info}.includes('{subscription['name']}') && [...{EFFORT_GROUP}.querySelectorAll('[role=radio]')]"
            ".map(el=>el.innerText).join(',') === '关闭,低,中,高,极高,Max'"))
        await page.send('Emulation.setDeviceMetricsOverride', width=360, height=770, deviceScaleFactor=1, mobile=False)
        select = f"{MODEL_DIALOG}.querySelector('.assistant-effort-select button')"
        await page.wait_for(f"{select}.getClientRects().length && !{EFFORT_GROUP}.getClientRects().length")
        await page.js(f"{select}.click()")
        await page.wait_for("document.querySelector('[role=listbox][aria-label=思考深度]')")
        ctx.check('短宽设置窗口改用可打开的下拉，避免档位文字挤压', True)
        await page.shot('assistant-effort-compact')
        await ctx.close(page)
        page = None

        write('/api/assistant/settings', {**blank, 'model': 'gpt-5.4', 'presetId': priority['id']})
        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900, reduce_motion=True)
        await dom.enter_chat(ctx, page, 'ASSIST_UI')
        await open_assistant(page)
        await model_dialog()
        await page.wait_for(f'!{fast}.disabled')
        ctx.check('连接支持 Fast 时显示计费提示，切换只更新草稿', await page.js(
            f"{fast}.click(); {MODEL_DIALOG}.innerText.includes('约 2× 计费')")
            and ctx.api('/api/assistant/settings')['fastMode'] is None)
        await page.js(f"$click({MODEL_DIALOG}, '保存')")
        await page.wait_for(f'!{MODEL_DIALOG}')
        ctx.check('支持的 Fast 草稿在保存后生效', ctx.api('/api/assistant/settings')['fastMode'] is True)
    finally:
        if page:
            await ctx.close(page)
        if card:
            dom.request(ctx, 'DELETE', f'/api/characters/{card}')
        ctx.fixtures.pop('ASSIST_UI', None)
        dom.request(ctx, 'PUT', '/api/assistant/settings', assistant)
        dom.request(ctx, 'PUT', '/api/settings', settings)


async def check_assistant_settings_dock(ctx):
    """Verify both horizontal slide directions and the sequential portrait handoff."""
    settings = ctx.api('/api/settings')
    fixture = ctx.fixtures['SHORT']
    data = Path(ctx.shots_dir).parent / 'data' / 'chats'
    chat_dir = next(path.parent for path in data.rglob('chat.json') if path.parent.name == fixture)
    history = chat_dir / 'assistant_chat.json'
    previous = history.read_bytes() if history.exists() else None
    history.write_text(json.dumps({'messages': [
        {'id': f'ui-assist-dock-{index}', 'role': 'assistant', 'content': f'助手验收记录 {index}\n\n' * 5}
        for index in range(12)
    ]}), encoding='utf-8')
    page = None

    async def motion(action):
        return await page.js(f"""new Promise(resolve => {{
          const panel = {PANEL}, drawer = {DRAWER}, start = performance.now(), frames = [];
          {action};
          requestAnimationFrame(function collect(now) {{
            const a = panel.getBoundingClientRect(), d = drawer.getBoundingClientRect();
            const y = a.top + 44, hit = document.elementFromPoint(a.right - 22, y);
            frames.push([Math.round(now-start), d.left, a.left, panel.contains(hit), panel.inert,
              drawer.closest('.drawer-wrapper').classList.contains('is-open')]);
            if (now-start < 400) requestAnimationFrame(collect); else resolve(frames);
          }});
        }})""")

    launchers = "[...document.querySelectorAll('button[aria-label=打开聊天助手]')]"
    fab = f"{launchers}.find(button=>button.classList.contains('chat-fab-surface'))"
    agent = f"{launchers}.find(button=>button.classList.contains('chat-toolbar-button'))"
    hidden = f"{launchers}.every(button=>button.inert && getComputedStyle(button).visibility === 'hidden')"
    close_assistant = f"{PANEL}.querySelector('[aria-label=关闭]').click()"

    try:
        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900)
        await dom.enter_chat(ctx, page, 'SHORT')
        await open_assistant(page)
        await asyncio.sleep(.36)
        ctx.check('助手面板生产样式使用主题模糊，展开后悬浮入口退出绘制和键盘顺序', await page.js(f"""(() => {{
          const style = getComputedStyle({PANEL}), token = style.getPropertyValue('--glass-blur-panel').trim();
          return style.backdropFilter === `blur(${{token}})` && parseFloat(token) > 0 && {hidden};
        }})()"""))
        incoming = await motion(OPEN_DRAWER)
        final = await page.js(f"""(() => {{const a = {PANEL}.getBoundingClientRect(), d = {DRAWER}.getBoundingClientRect();
          return [a.left-d.right, a.top-d.top, {DRAWER}.getAttribute('aria-modal')]; }})()""")
        ctx.check('横屏设置从窗口右侧滑到助手左侧，留 16 px 间距并对齐顶部',
                  incoming[0][1] >= 1277 and len({round(frame[1]) for frame in incoming}) >= 6 and final == [16, 0, None]
                  and all(a[1] >= b[1] - 1 for a, b in zip(incoming, incoming[1:])), [incoming[:3], final])
        ctx.check('横屏进场时助手位置稳定，鼠标命中始终属于助手',
                  all(abs(frame[2] - incoming[-1][2]) <= 1 and frame[3] and not frame[4] for frame in incoming))
        ctx.check('设置遮罩横跨窗口并铺到助手下面，助手仍可操作', await page.js(f"""(() => {{
          const panel = {PANEL}, rect = panel.getBoundingClientRect();
          const shade = document.querySelector('.drawer-wrapper .drawer-backdrop');
          const bounds = shade.getBoundingClientRect();
          return bounds.left === 0 && bounds.right === innerWidth && bounds.top === 0 && bounds.bottom === innerHeight
            && Number(getComputedStyle(shade).opacity) > 0
            && document.elementFromPoint(innerWidth - 2, innerHeight - 2) === shade
            && panel.contains(document.elementFromPoint(rect.right - 24, rect.top + 24));
        }})()"""))
        outgoing = await motion(CLOSE_DRAWER)
        ctx.check('横屏设置原路退到窗口外，着陆和起始位置连续',
                  outgoing[-1][1] >= 1280 and abs(outgoing[0][1]-incoming[-1][1]) < 48
                  and len({round(frame[1]) for frame in outgoing}) >= 6
                  and all(b[1] >= a[1] - 1 and a[3] for a, b in zip(outgoing, outgoing[1:])), outgoing[:4])
        await page.js(close_assistant)
        await page.wait_for(f"getComputedStyle({fab}).visibility === 'visible' && !{fab}.inert")
        ctx.check('助手退场后悬浮入口恢复', await page.js(f'{PANEL}.getBoundingClientRect().left >= innerWidth'))
        await page.js("document.querySelector('[aria-label=切换侧边栏]').click()")
        await page.wait_for(f"{agent} && getComputedStyle({agent}).visibility === 'visible'")
        await page.js(f'{agent}.click()')
        await page.wait_for(f'!{PANEL}.inert')
        ctx.check('侧栏收起时打开助手，Agent 入口也隐藏且退出键盘顺序', await page.js(hidden))
        await page.js(close_assistant)
        await page.wait_for(f"getComputedStyle({agent}).visibility === 'visible' && !{agent}.inert")
        ctx.check('助手退场后 Agent 恢复', await page.js(f'{PANEL}.getBoundingClientRect().left >= innerWidth'))
        await ctx.close(page)
        page = None

        page = await dom.open_app(ctx, ctx.serve_built(), 460, 870)
        await dom.enter_chat(ctx, page, 'SHORT')
        await open_assistant(page)
        await page.wait_for(f"{PANEL}.innerText.includes('助手验收记录 11')")
        await asyncio.sleep(.36)
        scroller = f"{PANEL}.querySelector('.custom-scrollbar')"
        draft = f"{PANEL}.querySelector('textarea')"
        await page.js(f"$type({draft}, '竖屏切换保留这条草稿'); {scroller}.scrollTop=120")
        enter = await motion(OPEN_DRAWER)
        await page.wait_for('$drawerOpen()')
        ctx.check('竖屏等助手退到窗口外后再打开设置', any(frame[4] and not frame[5] for frame in enter)
                  and all(frame[2] >= 460 for frame in enter if frame[5]), enter[-6:])
        await asyncio.sleep(.35)
        leave = await motion(CLOSE_DRAWER)
        await page.wait_for(f'!$drawerOpen() && !{PANEL}.inert')
        ctx.check('竖屏设置退场后恢复助手，保留历史、草稿和滚动位置',
                  all(frame[1] >= 460 for frame in leave if not frame[4])
                  and await page.js(f"{draft}.value === '竖屏切换保留这条草稿' && {scroller}.scrollTop === 120 && {PANEL}.innerText.includes('助手验收记录 11')"))
        ctx.check('竖屏从设置返回助手时，展开入口仍然隐藏', await page.js(hidden))

        await dom.settings_open(page)
        await page.js(f"$click({DRAWER}, '连接与默认模型')")
        await page.wait_for("document.querySelector('#settings-panel-global [role=switch][aria-label=流式传输]')?.getClientRects().length")
        await page.js("document.querySelector('#settings-panel-global [role=switch][aria-label=流式传输]').click()")
        await page.key('Escape', 27)
        await page.wait_for("document.querySelector('.app-notify-panel')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '取消')")
        ctx.check('Esc 触发的放弃确认被取消时，设置仍打开、助手仍暂时隐藏', await page.js(f'$drawerOpen() && {PANEL}.inert'))
        await page.js(f"$click({DRAWER}, '取消')")
        await page.wait_for("document.querySelector('.app-notify-panel')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
        await page.wait_for(f'!$drawerOpen() && !{PANEL}.inert')
        ctx.check('确定放弃后恢复助手，原设置与助手草稿保留',
                  ctx.api('/api/settings')['streamEnabled'] == settings['streamEnabled']
                  and await page.js(f"{draft}.value === '竖屏切换保留这条草稿'"))
        await dom.settings_open(page)
        await page.js(f"$click({DRAWER}, '保存设置')")
        await page.wait_for(f'!$drawerOpen() && !{PANEL}.inert')
        ctx.check('保存退出设置也恢复助手和原滚动位置', await page.js(f'{scroller}.scrollTop === 120'))
        await page.js(f"{PANEL}.querySelector('[aria-label=关闭]').click()")
        await dom.settings_open(page)
        await page.key('Escape', 27)
        await page.wait_for('!$drawerOpen()')
        await asyncio.sleep(.38)
        ctx.check('从主聊天进入设置时，关闭设置回到主聊天', await page.js(f'{PANEL}.inert'))
    finally:
        if page:
            await ctx.close(page)
        if previous is None:
            history.unlink(missing_ok=True)
        else:
            history.write_bytes(previous)
        dom.request(ctx, 'PUT', '/api/settings', settings)
