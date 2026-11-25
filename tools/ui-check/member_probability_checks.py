"""Exercise selection contrast and the group member probability controls on the built UI."""

import asyncio
import json

import dom_checks as dom


MODAL = "$modal('成员设置')"
PROBABILITY = f"{MODAL}?.querySelector('input[aria-label=参与概率]')"
SLIDER = f"{MODAL}?.querySelector('[role=slider][aria-label=参与概率滑条]')"
TOP_P = f"[...{MODAL}.querySelectorAll('.settings-field')].find(field=>field.querySelector('.settings-label')?.textContent.trim()==='Top P (覆写)')?.querySelector('input')"


async def enter_group_settings(ctx, page):
    group_id = ctx.fixtures['group']
    row = f"document.querySelector('[data-sidebar-chat-id={json.dumps(group_id)}]')"
    await page.wait_for(row)
    await page.js(f'{row}.click()')
    settings = "$btn(document.querySelector('main header'), '群聊')"
    await page.wait_for(settings)
    await page.js(f'{settings}.click()')
    await page.wait_for("$modal('群聊设置')")


async def open_member_settings(page):
    button = "$btn($modal('群聊设置'), '详情设置')"
    await page.wait_for(button)
    await page.js(f'{button}.click()')
    await page.wait_for(MODAL)


async def check_member_probability(ctx):
    """Typing keeps an editable draft; the bar renders continuous feedback and commits 5% stops."""
    previous_settings = ctx.api('/api/settings')
    path = f"/api/chats/{ctx.fixtures['group']}"
    original_members = ctx.api(path).get('memberSettings') or {}
    member = ctx.api(path)['memberIds'][0]
    fixture = {**original_members, member: {**original_members.get(member, {}), 'probability': 1}}
    dom.request(ctx, 'PUT', path, {'memberSettings': fixture})
    page = None

    async def typed(text):
        await page.js(f'{PROBABILITY}.focus()')
        await page.key('a', 65, modifiers=2)
        await page.send('Input.insertText', text=text)

    async def click_track(fraction):
        rect = await page.js(f'{SLIDER}.getBoundingClientRect().toJSON()')
        x, y = rect['left'] + rect['width'] * fraction, rect['top'] + rect['height'] / 2
        await page.mouse('mousePressed', x, y, button='left', buttons=1, clickCount=1)
        await page.mouse('mouseReleased', x, y, button='left', clickCount=1)

    try:
        dom.update_settings(ctx, themeMode='light', themeId='teal')
        page = await dom.open_app(ctx, ctx.serve_built(), 1280, 900)
        await enter_group_settings(ctx, page)
        await open_member_settings(page)

        results = await page.js(f"""(() => {{
          const root = document.documentElement, original = root.dataset.theme, input = {TOP_P};
          const text = {MODAL}.querySelector('.modal-title');
          try {{
            return {json.dumps(dom.THEMES)}.map(theme => {{
              root.dataset.theme = theme;
              return [theme, ...[input, text].map(el => {{
                const selected = getComputedStyle(el, '::selection');
                const foreground = $rgb(selected.color), fill = $rgb(selected.backgroundColor);
                return [$contrast(foreground, fill), $contrast(fill, $rgb(getComputedStyle(input).backgroundColor))];
              }})];
            }});
          }} finally {{ root.dataset.theme = original; }}
        }})()""")
        ctx.check('七个浅色主题的选区文字、选区与普通输入底色对比均清晰',
                  all(text >= 4.5 and fill >= 3 for _, *samples in results for text, fill in samples), results)

        await page.js(f'{PROBABILITY}.focus()')
        await page.key('End', 35)
        await page.key('Backspace', 8)
        ctx.check('单按 Backspace 可清空概率，焦点留在输入框',
                  await page.js(f"{PROBABILITY}.value === '' && document.activeElement === {PROBABILITY}"))
        await page.send('Input.insertText', text='-0.4')
        ctx.check('负数可完整输入，编辑中保留原文', await page.js(f"{PROBABILITY}.value === '-0.4'"))
        await page.key('Tab', 9)
        await page.wait_for(f"{PROBABILITY}.value === '0'")
        ctx.check('负数失焦后回填 0', await page.js(f"{SLIDER}.getAttribute('aria-valuenow') === '0'"))
        await typed('1.27')
        ctx.check('大于 1 的数编辑中保留原文', await page.js(f"{PROBABILITY}.value === '1.27'"))
        await page.key('Tab', 9)
        await page.wait_for(f"{PROBABILITY}.value === '1'")
        ctx.check('大于 1 的数失焦后回填 1', await page.js(f"{SLIDER}.getAttribute('aria-valuenow') === '100'"))

        await typed('0.333')
        await page.key('Tab', 9)
        ctx.check('手输小数失焦后保留原精度', await page.js(f"{PROBABILITY}.value === '0.333'"))
        await page.js(f'{PROBABILITY}.focus()')
        await page.key('a', 65, modifiers=2)
        await page.key('Backspace', 8)
        await page.key('Tab', 9)
        ctx.check('空值退出后恢复默认的 100%', await page.js(f"{PROBABILITY}.value === '1'"))

        await typed('0.433')
        await page.js(f"{SLIDER}.scrollIntoView({{block:'center'}})")
        await asyncio.sleep(.24)
        await click_track(.623)
        await page.wait_for(f"{PROBABILITY}.value === '0.6'")
        ctx.check('编辑中直接点条，按最近 0.05 选中 60% 并同步输入框',
                  await page.js(f"{SLIDER}.getAttribute('aria-valuenow') === '60'"))

        rect = await page.js(f'{SLIDER}.getBoundingClientRect().toJSON()')
        left, width, y = rect['left'], rect['width'], rect['top'] + rect['height'] / 2
        await page.mouse('mousePressed', left + width * .6, y, button='left', buttons=1, clickCount=1)
        widths = []
        for index, point in enumerate((.632, .669, .693), 1):
            await page.mouse('mouseMoved', left + width * point, y, button='left', buttons=1)
            widths.append(await page.js(f"{SLIDER}.firstElementChild.firstElementChild.getBoundingClientRect().width / {width}"))
            await page.shot(f'member-probability-drag-{index}')
        ctx.check('拖动时连续跟随实际指针位置，未提前吸附到档位',
                  all(abs(actual - target) < .006 for actual, target in zip(widths, (.632, .669, .693))), widths)
        await page.mouse('mouseReleased', left + width * .693, y, button='left', clickCount=1)
        await page.wait_for(f"{PROBABILITY}.value === '0.7'")
        await asyncio.sleep(.3)
        await page.shot('member-probability-drag-4')
        ctx.check('松手吸附到 70%，只更新成员设置草稿',
                  await page.js(f"{SLIDER}.getAttribute('aria-valuenow') === '70'")
                  and ctx.api(path)['memberSettings'][member]['probability'] == 1)
        await page.key('ArrowLeft', 37)
        ctx.check('滑条支持键盘 0.05 步进', await page.js(f"{PROBABILITY}.value === '0.65'"))

        await page.js(f"$click({MODAL}, '保存')")
        await page.wait_for(f'!{MODAL}')
        ctx.check('保存后写入群聊成员概率', ctx.api(path)['memberSettings'][member]['probability'] == .65)
        await open_member_settings(page)
        await typed('0.2')
        await page.js(f"$click({MODAL}, '取消')")
        await page.wait_for(f'!{MODAL}')
        await open_member_settings(page)
        ctx.check('取消后重新打开恢复已保存概率', await page.js(f"{PROBABILITY}.value === '0.65'"))
    finally:
        if page:
            await ctx.close(page)
        dom.request(ctx, 'PUT', path, {'memberSettings': original_members})
        dom.request(ctx, 'PUT', '/api/settings', previous_settings)
