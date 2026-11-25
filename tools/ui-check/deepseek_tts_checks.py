"""Drive saved DeepSeek presets, audition and message playback in the built UI."""

import asyncio
import json

import dom_checks as dom


async def wait_asset(ctx, chat_path, match, previous=None):
    for _ in range(65):
        chat = await asyncio.to_thread(ctx.api, chat_path)
        for item in reversed(chat['messages']):
            asset = item.get('ttsAudioAssetId')
            if match(item) and asset and asset != previous:
                return asset
        await asyncio.sleep(0.15)
    return None


async def check_deepseek_tts(ctx):
    """已保存预设试听、手动朗读、切换音色和新回复自动朗读。"""
    saved = ctx.api('/api/settings')
    fixture = 'DEEPSEEK'
    preset = {'id': 'ui-deepseek', 'name': 'DeepSeek 朗读验收', 'baseUrl': ctx.mock_state.tts_url,
              'apiKey': 'local-tts-fixture', 'presetKind': 'tts', 'ttsProvider': 'deepseek'}
    model_preset = {'id': 'ui-deepseek-fixture-model', 'name': '自动朗读测试模型', 'baseUrl': ctx.mock_state.tts_url,
                    'apiKey': 'local-chat-fixture', 'modelCandidates': ['mock'], 'models': ['mock'],
                    'protocol': 'openai_compatible_chat'}
    ctx.mock_state.tts_calls.clear()

    def write(method, path, body):
        status, _, detail = dom.request(ctx, method, path, body)
        if status != 200:
            raise RuntimeError(f'{method} {path}: {detail.decode()[:200]}')
        return json.loads(detail)

    def configure(voice, scope='off'):
        write('PUT', chat_path, {'overrides': {
            'presetId': model_preset['id'], 'params': {'model': 'mock'},
            'tts': {'presetId': preset['id'], 'voiceByCharacterId': {character_id: voice}, 'autoReadScope': scope},
        }})

    page = None
    character_id = None
    try:
        dom.update_settings(ctx, ttsEnabled=True, apiPresets=[*saved.get('apiPresets', []), model_preset, preset])
        character_id = write('POST', '/api/characters', {'name': 'DeepSeek 朗读测试角色', 'firstMessage': ''})['id']
        chat_id = write('POST', '/api/chats', {'characterId': character_id, 'title': 'DeepSeek 朗读测试会话'})['id']
        ctx.fixtures[fixture] = chat_id
        chat_path = f'/api/chats/{chat_id}'
        updated = write('POST', chat_path + '/messages', {
            'role': 'assistant', 'content': f'【最后一条开头 {fixture}】请朗读这一段。', 'characterId': character_id,
        })
        tail_id = updated['messages'][-1]['id']
        configure('stella')
        page = await dom.open_app(ctx, ctx.serve_built(), reduce_motion=True)
        await dom.settings_open(page)
        await page.js("$click(document,'API 预设')")
        row = f"""[...document.querySelectorAll('[draggable=true]')].find(e=>e.textContent.includes({json.dumps(preset['name'])}))"""
        await page.wait_for(row)
        await page.js(f"{row}.click()")
        await page.wait_for("document.querySelector('button[aria-label=试听海星]')")
        controls = await page.js("""(() => {const drawer=document.querySelector('.drawer-panel');
          return !!drawer.querySelector('button[aria-label=试听暗潮]') && !drawer.innerText.includes('模型列表')
                 && !drawer.innerText.includes('音色复刻') && !drawer.innerText.includes('音色设计');})()""")
        ctx.check('DeepSeek 预设显示两个内置音色与支持的控件', controls)
        await page.js("document.querySelector('button[aria-label=试听海星]').click()")
        await page.wait_for("document.querySelector('audio[aria-label=音色试听]')?.readyState >= 2")
        ctx.check('试听合成并加载了可播放的音频', [call.get('voice_id') for call in ctx.mock_state.tts_calls] == ['stella'])
        await page.shot('deepseek-tts-preview')
        await page.key('Escape', 27)
        await page.wait_for('!$drawerOpen()')
        await dom.enter_chat(ctx, page, fixture)
        await page.js("$click($rows().at(-1),'朗读')")
        first = await wait_asset(ctx, chat_path, lambda item: item['id'] == tail_id)
        ctx.check('手动朗读绑定完整音频', bool(first) and ctx.mock_state.tts_calls[-1].get('voice_id') == 'stella', first)

        await dom.settings_open(page)
        await page.js("$click(document, '当前会话')")
        await page.js("$click(document.querySelector('.drawer-panel'), '文字转语音')")
        preset_trigger = "document.querySelector('button[role=combobox][aria-label=\"TTS 预设\"]')"
        voice_label = 'DeepSeek 朗读测试角色的朗读音色'
        voice_trigger = f"document.querySelector('button[role=combobox][aria-label=\"{voice_label}\"]')"
        await page.wait_for(f"{preset_trigger}?.textContent.includes({json.dumps(preset['name'])})")
        await page.js(f"{preset_trigger}.click()")
        await page.wait_for("document.querySelector('[role=listbox][aria-label=\"TTS 预设\"] [aria-selected=true]')")
        await page.key('Escape', 27)
        await page.wait_for(f"{voice_trigger}?.textContent.includes('海星')")
        for label in ('选择音色', '暗潮'):
            await page.js(f"{voice_trigger}.scrollIntoView({{block:'center'}}); {voice_trigger}.click()")
            option = (f"[...document.querySelectorAll('[role=listbox][aria-label=\"{voice_label}\"] [role=option]')]"
                      f".find(option => option.textContent.trim() === {json.dumps(label)})")
            await page.wait_for(option)
            await page.js(f"{option}.click()")
            await page.wait_for(f"{voice_trigger}?.textContent.trim() === {json.dumps(label)}")
        await page.js("$click(document.querySelector('[role=radiogroup][aria-label=自动朗读范围]'), '角色')")
        await page.js("$click(document, '保存设置')")
        await page.wait_for('!$drawerOpen()')
        await page.js("$click($rows().at(-1),'朗读')")
        second = await wait_asset(ctx, chat_path, lambda item: item['id'] == tail_id, previous=first)
        ctx.check('切换成暗潮后手动朗读使用新的音频', bool(second) and ctx.mock_state.tts_calls[-1].get('voice_id') == 'tide', second)

        before = {item['id'] for item in ctx.api(chat_path)['messages']}
        calls = len(ctx.mock_state.tts_calls)
        await dom.send_in_chat(page, '这是一次模拟自动朗读验证。')
        automatic = await wait_asset(ctx, chat_path, lambda item: item['role'] == 'assistant' and item['id'] not in before)
        ctx.check('新回复自动合成并绑定暗潮音频',
                  bool(automatic) and len(ctx.mock_state.tts_calls) > calls and ctx.mock_state.tts_calls[-1].get('voice_id') == 'tide',
                  automatic)
    finally:
        if page:
            await ctx.close(page)
        dom.request(ctx, 'PUT', '/api/settings', saved)
        ctx.fixtures.pop(fixture, None)
        if character_id:
            dom.request(ctx, 'DELETE', f'/api/characters/{character_id}')
