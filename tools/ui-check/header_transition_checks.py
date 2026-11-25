"""Observe the header and member strip frame by frame during a real chat switch."""
import json

import dom_checks as dom


SAMPLE = """() => {
  const header = document.querySelector('main header');
  const glass = header?.querySelector('.theme-header-bg');
  const strip = header?.querySelector('.chat-header-groupstrip-content')
    ?? header?.querySelector('.overflow-x-auto')?.parentElement;
  const style = strip && getComputedStyle(strip);
  return {
    height: header?.getBoundingClientRect().height ?? 0,
    bottom: header?.getBoundingClientRect().bottom ?? 0,
    glassBottom: glass?.getBoundingClientRect().bottom ?? 0,
    opacity: style ? Number(style.opacity) : null,
    offset: style && style.transform !== 'none' ? new DOMMatrixReadOnly(style.transform).m42 : 0,
  };
}"""


async def switch_and_sample(page, chat_id, title):
    clicked = f'document.querySelector(\'[data-sidebar-chat-id="{chat_id}"]\')'
    return await page.js(f"""(async () => {{
      const sample = {SAMPLE};
      const frames = [sample()];
      {clicked}.click();
      const started = performance.now();
      let changed;
      while (performance.now() - started < 2800) {{
        await new Promise(requestAnimationFrame);
        if (!document.querySelector('main header')?.innerText.includes({json.dumps(title)})) continue;
        changed ??= performance.now();
        frames.push(sample());
        if (performance.now() - changed >= 460) break;
      }}
      return frames;
    }})()""")


async def check_chat_header_switch(ctx):
    """群聊与单聊切换时，顶栏高度和成员出入场同时变化"""
    url = ctx.serve_built()
    single = ctx.api(f"/api/chats/{ctx.fixtures['LONG']}")
    character_id = single['characterId']
    other = next(card['id'] for card in ctx.api('/api/characters') if card['id'] != character_id)
    # 进入群聊时如果所选角色不在群里，侧栏会切换角色，原单聊也会从历史列表消失。
    status, _, payload = dom.request(ctx, 'POST', '/api/chats', {
        'characterId': character_id, 'isGroup': True, 'title': '顶栏切换验收群聊',
        'memberIds': [character_id, other],
    })
    if status != 200:
        raise RuntimeError(f'创建顶栏验收群聊失败：HTTP {status}')
    group = json.loads(payload)
    saved = ctx.api('/api/settings')
    opening_group = f'document.querySelector(\'[data-sidebar-chat-id="{group["id"]}"]\')'

    try:
        for theme, width, height, reduced in [('light', 1100, 515, False), ('dark', 1440, 900, True)]:
            dom.update_settings(ctx, themeMode=theme)
            page = await dom.open_app(ctx, url, width, height, reduce_motion=reduced)
            try:
                await dom.enter_chat(ctx, page, "LONG")
                await page.wait_for(opening_group)
                await page.js(f'{opening_group}.click()')
                await page.wait_for(f"document.querySelector('main header h2')?.innerText === {json.dumps(group['title'])}")
                await page.wait_for(f"(() => {{ const state = ({SAMPLE})(); return state.opacity === 1 && state.offset === 0; }})()")
                await page.wait_for(f"""document.querySelector('aside [data-sidebar-chat-id="{single["id"]}"]')""")
                exit_frames = await switch_and_sample(page, single['id'], single['title'])
                enter_frames = await switch_and_sample(page, group['id'], group['title'])
                tall, short = exit_frames[0]['height'], exit_frames[-1]['height']
                ctx.check(f'{theme} 群聊和单聊的终态高度正确',
                          tall - short > 20 and exit_frames[-1]['opacity'] is None
                          and enter_frames[-1]['opacity'] == 1 and abs(enter_frames[-1]['height'] - tall) < 1,
                          (tall, short, enter_frames[-1]))

                if reduced:
                    ctx.check('减弱动态下直接切换高度，成员没有滑动或淡入淡出',
                              all(short - 1 <= f['height'] <= tall + 1 and f['offset'] == 0
                                  and f['opacity'] in (None, 1)
                                  and min(abs(f['height'] - short), abs(f['height'] - tall)) < 1
                                  for f in exit_frames + enter_frames))
                    continue

                exit_middle = [f for f in exit_frames if short + 1 < f['height'] < tall - 1]
                enter_middle = [f for f in enter_frames if short + 1 < f['height'] < tall - 1]
                ctx.check('群成员向上淡出，同时顶栏收矮',
                          len(exit_middle) >= 3 and any(f['offset'] < -1 and 0 < (f['opacity'] or 0) < 0.99
                                                       for f in exit_middle),
                          {'direction': sorted(set(round(f['offset'], 1) for f in exit_frames)),
                           'intermediate': len(exit_middle)})
                last_member_frame = next((f for f in reversed(exit_frames) if f['opacity'] is not None), exit_frames[0])
                ctx.check('移除群成员行时顶栏已经收合', abs(last_member_frame['height'] - short) < 3, last_member_frame)
                ctx.check('切回群聊时顶栏展开并保留成员入场',
                          len(enter_middle) >= 3 and any(f['offset'] > 0 and 0 < (f['opacity'] or 0) < 0.99
                                                        for f in enter_middle), len(enter_middle))
                ctx.check('磨砂下缘逐帧与顶栏高度同步',
                          all(abs(f['glassBottom'] - f['bottom']) < 1 for f in exit_frames + enter_frames))
                ctx.note('顶栏切换高度与退出方向', {'expanded': tall, 'collapsed': short,
                         'exitIntermediateFrames': len(exit_middle), 'enterIntermediateFrames': len(enter_middle),
                         'memberExitOffsetMin': round(min(f['offset'] for f in exit_frames), 2)})
            finally:
                await ctx.close(page)
    finally:
        dom.request(ctx, 'DELETE', f"/api/chats/{group['id']}")
        dom.request(ctx, 'PUT', '/api/settings', saved)


async def check_composer_sidebar_spacing(ctx):
    """侧栏开合时，输入卡片下方的提示与底部留白随原有动效恢复。"""
    page = await dom.open_app(ctx, ctx.serve_built(), width=1280, height=800)
    toggle = "document.querySelector('[aria-label=切换侧边栏]')"
    shell = "document.querySelector('.chat-input-shell')"
    hint = f"{shell}.querySelector('.chat-input-footer-hint')"
    measure = fr"""(() => {{
      const shell = {shell}, hint = {hint};
      const card = shell.querySelector('.chat-input-card-morph');
      const box = card.getBoundingClientRect();
      const style = getComputedStyle(hint);
      const draft = card.querySelector('textarea');
      const draftStyle = getComputedStyle(draft);
      return {{gap: innerHeight - box.bottom, hintGap: hint.getBoundingClientRect().top - box.bottom,
        cardHeight: box.height, lineHeight: parseFloat(draftStyle.lineHeight),
        draftTextHeight: draft.clientHeight - parseFloat(draftStyle.paddingTop) - parseFloat(draftStyle.paddingBottom),
        hintHeight: hint.getBoundingClientRect().height, hintText: hint.textContent.trim(), opacity: Number(style.opacity),
        shellPadding: parseFloat(getComputedStyle(shell).paddingBottom), rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
        margin: parseFloat(getComputedStyle(shell).marginTop),
        cardHasShortcut: card.innerText.split('\n').some(line => line.trim() === 'Ctrl + Enter 发送')}};
    }})()"""
    try:
        await dom.enter_chat(ctx, page, "LONG")
        opened = await page.js(measure)
        ctx.check("空草稿按两行实际正文高度起步",
                  abs(opened["draftTextHeight"] - 2 * opened["lineHeight"]) <= 1, opened)
        reserved = opened["shellPadding"] + opened["hintGap"] + opened["hintHeight"]
        ctx.check("侧栏展开时提示位于卡片下方，并垫高输入卡片",
                  opened["hintText"] == "Ctrl + Enter 发送" and opened["opacity"] == 1
                  and opened["hintGap"] > 0 and abs(opened["gap"] - reserved) <= 1
                  and not opened["cardHasShortcut"], opened)
        await page.shot("composer-sidebar-open")

        await page.js(f"{toggle}.click()")
        await page.wait_for(f"{shell}.classList.contains('chat-input-shell--sink') && getComputedStyle({hint}).opacity === '0'")
        closed = await page.js(measure)
        expected_shift = opened["rem"] * 1.75
        ctx.check("侧栏收起时提示淡出，卡片按原距离下沉并保留底部留白",
                  abs(opened["gap"] - closed["gap"] - expected_shift) <= 1
                  and abs(closed["margin"] + expected_shift) <= 1
                  and abs(opened["cardHeight"] - closed["cardHeight"]) <= 1
                  and closed["gap"] >= opened["rem"] * 1.2
                  and not closed["cardHasShortcut"], closed)
        await page.shot("composer-sidebar-closed")

        await page.js(f"{toggle}.click()")
        await page.wait_for(f"!{shell}.classList.contains('chat-input-shell--sink') && getComputedStyle({hint}).opacity === '1'")
        reopened = await page.js(measure)
        ctx.check("重新展开侧栏后提示与卡片底部距离复原",
                  abs(reopened["gap"] - opened["gap"]) <= 1 and reopened["hintText"] == opened["hintText"],
                  reopened)
    finally:
        await ctx.close(page)
