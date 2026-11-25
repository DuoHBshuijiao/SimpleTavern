"""Drive the built application through settings, real image loads and system preference changes."""

import asyncio
import base64
import io
import json
from pathlib import Path
import urllib.request
import zipfile

import dom_checks as dom


SCHEME = "document.documentElement.dataset.colorScheme"
MODE_TRIGGER = "document.querySelector('button[aria-label=外观模式]')"
EMULATED_GPU = r"""(() => {
  const noop = () => {};
  const pass = {setPipeline:noop,setBindGroup:noop,draw:noop,end:noop};
  const device = {
    createBindGroupLayout:()=>({}),createPipelineLayout:()=>({}),createBuffer:()=>({destroy:noop}),
    createShaderModule:()=>({getCompilationInfo:async()=>({messages:[]})}),
    createRenderPipeline:()=>({}),createBindGroup:()=>({}),
    createCommandEncoder:()=>({beginRenderPass:()=>pass,finish:()=>({})}),
    queue:{writeBuffer:noop,submit:noop},addEventListener:noop,removeEventListener:noop,destroy:noop,
  };
  Object.defineProperty(navigator,'gpu',{configurable:true,value:{
    requestAdapter:async()=>({requestDevice:async()=>device}),getPreferredCanvasFormat:()=>'bgra8unorm',
  }});
  window.GPUBufferUsage ??= {UNIFORM:64,COPY_DST:8};
  const originalContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(kind,...args) {
    if(kind==='webgpu') return {configure:noop,unconfigure:noop,getCurrentTexture:()=>({createView:()=>({})})};
    return originalContext.call(this,kind,...args);
  };
})()"""


async def upload_color(page, color):
    return await page.js(f"""(async () => {{
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 4;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = {json.dumps(color)}; ctx.fillRect(0, 0, 4, 4);
      const body = new FormData(); body.append('file', await new Promise(resolve => canvas.toBlob(resolve)), 'test.png');
      const response = await fetch('/api/page-backgrounds', {{method: 'POST', body}});
      if (!response.ok) throw Error(await response.text());
      return (await response.json()).filename;
    }})()""")


def upload_wallpaper(ctx, image):
    boundary = 'simpletavern-wallpaper-fixture'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="sample.webp"\r\n'
            'Content-Type: image/webp\r\n\r\n').encode() + image.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(ctx.api_url + '/api/page-backgrounds', data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request) as response:
        return json.load(response)['filename']


async def check_appearance_modes(ctx):
    """亮暗设置、系统偏好、静态图回退、七个色系、窄屏预览与保存。"""
    saved = ctx.api('/api/settings')
    page = await dom.open_app(ctx, ctx.serve_built(), reduce_motion=True)
    files = []
    shader = None
    try:
        for color in ('#fff', '#18181b', '#777', 'transparent'):
            files.append(await upload_color(page, color))
        light, dark, middle, transparent = files

        old_settings = {key: value for key, value in saved.items() if key != 'themeMode'}
        status, _, raw = dom.request(ctx, 'PUT', '/api/settings', old_settings)
        ctx.check('旧设置缺少明暗模式时默认暗色', status == 200 and json.loads(raw).get('themeMode') == 'dark')
        await dom.goto_app(page)
        ctx.check('旧设置在页面使用暗色', await page.js(SCHEME) == 'dark')
        backup = io.BytesIO()
        with zipfile.ZipFile(backup, 'w') as archive:
            archive.writestr('settings.json', json.dumps(old_settings))
        encoded = base64.b64encode(backup.getvalue()).decode()
        dom.update_settings(ctx, themeMode='light')
        imported = await page.js(f"""(async () => {{
          const bytes = Uint8Array.from(atob({json.dumps(encoded)}), c=>c.charCodeAt(0));
          const body = new FormData(); body.append('file', new Blob([bytes]), 'legacy-settings.zip');
          return (await fetch('/api/import', {{method:'POST',body}})).ok;
        }})()""")
        ctx.check('恢复旧设置备份后使用暗色', imported and ctx.api('/api/settings').get('themeMode') == 'dark')

        for name, image, opacity, expected in (
            ('白图', light, 1, 'light'), ('深色图', dark, 1, 'dark'), ('中间亮度', middle, 1, 'dark'),
            ('透明图', transparent, 1, 'dark'), ('隐藏图片', light, 0, 'dark'), ('缺图', 'missing.png', 1, 'dark'),
        ):
            dom.update_settings(ctx, themeMode='background', pageBackgroundImage=image,
                                pageBackgroundOpacity=opacity, webgpuBackgroundEnabled=False)
            await page.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-color-scheme', 'value': 'light'}])
            await dom.goto_app(page)
            actual = await page.js(SCHEME)
            ctx.check(f'跟随背景 · {name}', actual == expected, actual)

        for sample, expected in (('浅色背景.webp', 'light'), ('深色背景.webp', 'dark')):
            image = Path(__file__).resolve().parents[3] / sample
            if image.is_file():
                filename = upload_wallpaper(ctx, image)
                files.append(filename)
                dom.update_settings(ctx, pageBackgroundImage=filename, pageBackgroundOpacity=0.3)
                await dom.goto_app(page)
                ctx.check(f'跟随背景 · {sample}', await page.js(SCHEME) == expected)
                await page.shot(f'appearance-wallpaper-{expected}')

        dom.update_settings(ctx, themeMode='system')
        await dom.goto_app(page)
        ctx.check('系统偏好亮色生效', await page.js(SCHEME) == 'light')
        await page.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-color-scheme', 'value': 'dark'}])
        try:
            await page.wait_for(f"{SCHEME}==='dark'", 3)
        except TimeoutError:
            pass
        ctx.check('系统偏好变化实时生效', await page.js(SCHEME) == 'dark', await page.js(SCHEME))

        gpu = await page.send('Page.addScriptToEvaluateOnNewDocument', source=EMULATED_GPU)
        status, _, raw = dom.request(ctx, 'POST', '/api/shader-presets')
        if status != 200:
            raise RuntimeError(f'创建 WebGPU 验收预设失败 {status}')
        shader = json.loads(raw)['filename']
        dom.update_settings(ctx, themeMode='background', pageBackgroundImage=light, pageBackgroundOpacity=0.3,
                            webgpuBackgroundEnabled=True, webgpuBackgroundActivePresetId='appearance-check',
                            webgpuBackgroundPresets=[{'id': 'appearance-check', 'name': '检查', 'wgslFile': shader}])
        await dom.goto_app(page)
        drawn = await page.js("!![...document.querySelectorAll('canvas')].find(e=>e.style.visibility==='visible')")
        ctx.check('WebGPU 开始绘制后亮色图片停止参与判定', drawn and await page.js(SCHEME) == 'dark', drawn)
        dom.update_settings(ctx, webgpuBackgroundEnabled=False)
        await dom.goto_app(page)
        ctx.check('关闭 WebGPU 后重新按静态图判定', await page.js(SCHEME) == 'light')
        await page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=gpu['identifier'])

        delayed = await page.send('Page.addScriptToEvaluateOnNewDocument', source=rf"""(() => {{
          const decode = HTMLImageElement.prototype.decode;
          HTMLImageElement.prototype.decode = async function() {{
            await decode.call(this);
            if (this.src.includes({json.dumps(light)})) await new Promise(resolve=>{{window.releaseWallpaper=resolve;}});
          }};
        }})()""")
        await dom.goto_app(page)
        await page.wait_for("window.releaseWallpaper")
        await dom.settings_open(page)
        await ctx.expand_appearance(page)
        await page.js(f"{MODE_TRIGGER}.click()")
        await page.wait_for("document.querySelector('[role=listbox][aria-label=外观模式]')")
        await page.js("[...document.querySelectorAll('[role=listbox][aria-label=外观模式] [role=option]')].find(item=>item.textContent.trim()==='固定暗色').click()")
        await page.js("window.releaseWallpaper()")
        await asyncio.sleep(0.2)
        ctx.check('已切换模式时，迟到的亮图解码不会覆盖暗色预览', await page.js(SCHEME) == 'dark')
        await page.key('Escape', 27)
        await page.wait_for("document.querySelector('.app-notify-panel')")
        await page.js("$click(document.querySelector('.app-notify-panel'),'确定')")
        await page.wait_for(f"{SCHEME}==='light' && !$drawerOpen()")
        await page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=delayed['identifier'])

        accents = set()
        for theme in dom.THEMES:
            dom.update_settings(ctx, themeId=theme, themeMode='light', pageBackgroundImage=light, pageBackgroundOpacity=0.3)
            await dom.goto_app(page)
            result = await page.js("""(() => {const root = document.documentElement, style = getComputedStyle(root);
              const input = document.querySelector('textarea');
              return {theme: root.dataset.theme, mode: style.colorScheme, accent: style.getPropertyValue('--color-brand').trim(),
                body: $contrast($rgb(style.color), $rgb(style.backgroundColor)),
                muted: $contrast($rgb(style.getPropertyValue('--color-text-muted')), $rgb(style.backgroundColor)),
                inputMode: input ? getComputedStyle(input).colorScheme : style.colorScheme};})()""")
            accents.add(result['accent'])
            ctx.check(f'{theme} 亮色正文、次要文字和原生控件', result['theme'] == theme and result['mode'] == 'light'
                      and result['inputMode'] == 'light' and result['body'] >= 4.5 and result['muted'] >= 4.5, result)
        ctx.check('亮色下七个色系保留独立强调色', len(accents) == 7, sorted(accents))
        if await page.js(SCHEME) != 'light':
            ctx.check('窄屏设置能预览、取消和保存明暗模式', False, '应用未实现亮色外观')
            return

        await page.send('Emulation.setDeviceMetricsOverride', width=420, height=800, deviceScaleFactor=1, mobile=False)
        await dom.settings_open(page)
        await ctx.expand_appearance(page)
        await page.wait_for(MODE_TRIGGER)
        contrast = await page.js(f"""(() => {{
          const select = {MODE_TRIGGER};
          const scheme = document.querySelector('button[aria-label=界面色系]');
          select.focus();
          const style = getComputedStyle(select);
          const background = $rgb(style.backgroundColor);
          const edgeFree = (e) => {{
            const cs = getComputedStyle(e);
            return ['Top', 'Right', 'Bottom', 'Left'].every(side =>
              parseFloat(cs['border' + side + 'Width']) === 0 || $rgb(cs['border' + side + 'Color'])[3] === 0);
          }};
          return {{text: $contrast($rgb(style.color), background),
                   edgeFree: edgeFree(select) && edgeFree(scheme),
                   focus: $contrast($rgb(style.outlineColor), background),
                   focused: document.activeElement === select && style.outlineStyle === 'solid'
                     && style.outlineWidth === '2px' && style.outlineOffset === '2px',
                   overflow: document.documentElement.scrollWidth > innerWidth}};
        }})()""")
        ctx.check('窄屏亮色选择器的边框与键盘焦点轮廓独立', contrast['text'] >= 4.5 and contrast['edgeFree']
                  and contrast['focus'] >= 3 and contrast['focused'] and not contrast['overflow'], contrast)

        await page.key('ArrowDown', 40)
        await page.wait_for(f"{MODE_TRIGGER}.getAttribute('aria-expanded') === 'true'")
        await page.wait_for("(() => {const panel = document.querySelector('[role=listbox][aria-label=外观模式]')?.closest('.select-dropdown'); return panel && Number(getComputedStyle(panel).opacity) >= 0.99;})()")
        await page.key('ArrowDown', 40)
        active = await page.js(f"""(() => {{
          const trigger = {MODE_TRIGGER};
          const option = document.getElementById(trigger.getAttribute('aria-activedescendant'));
          const panel = document.getElementById(trigger.getAttribute('aria-controls'));
          const style = getComputedStyle(trigger);
          const activeStyle = option && getComputedStyle(option);
          return {{hasActive: !!option && option.dataset.active === 'true',
                    selected: panel?.querySelector('[aria-selected=true]')?.textContent.trim(),
                    active: option?.textContent.trim(),
                    marker: activeStyle?.outlineStyle === 'solid' && activeStyle.outlineWidth === '2px'
                      && activeStyle.outlineOffset === '-2px' && style.outlineStyle === 'none',
                    openBorder: $rgb(style.borderTopColor)[3],
                    openShadow: style.boxShadow,
                    popoverBorder: $rgb(getComputedStyle(panel.closest('.select-dropdown')).borderTopColor)[3]}};
        }})()""")
        ctx.check('展开态的焦点轮廓只在活动项，已选项仍独立标记', active['hasActive'] and active['marker']
                  and active['selected'] != active['active'] and active['openBorder'] == 0
                  and active['openShadow'] == 'none' and active['popoverBorder'] == 0, active)
        await page.shot('appearance-mode-dropdown-light-narrow')
        await page.key('Escape', 27)
        ctx.check('Esc 只关下拉，焦点回到外观模式', await page.js(
            f"$drawerOpen() && document.activeElement === {MODE_TRIGGER} && {MODE_TRIGGER}.getAttribute('aria-expanded') === 'false'"))

        async def choose_dark():
            await page.js(f"{MODE_TRIGGER}.focus()")
            await page.key('ArrowDown', 40)
            await page.key('End', 35)
            await page.wait_for(f"document.getElementById({MODE_TRIGGER}.getAttribute('aria-activedescendant'))?.textContent.trim()==='固定暗色'")
            await page.key('Enter', 13)
            await page.wait_for(f"{SCHEME}==='dark'")

        await choose_dark()
        ctx.check('暗色草稿实时预览但尚未持久化', ctx.api('/api/settings').get('themeMode') == 'light')
        await page.key('Escape', 27)
        await page.wait_for("document.querySelector('.app-notify-panel')?.textContent.includes('放弃未保存更改')")
        ctx.check('传送到 body 的确认框随草稿暗色', await page.js("getComputedStyle(document.querySelector('.app-notify-panel')).colorScheme") == 'dark')
        await page.js("$click(document.querySelector('.app-notify-panel'),'确定')")
        await page.wait_for(f"{SCHEME}==='light' && !$drawerOpen()")
        ctx.check('取消后恢复已保存亮色', ctx.api('/api/settings').get('themeMode') == 'light')
        await dom.settings_open(page)
        await ctx.expand_appearance(page)
        await page.shot('appearance-light-narrow')
        await choose_dark()
        await page.js("$click(document,'保存设置')")
        await page.wait_for('!$drawerOpen()')
        await dom.goto_app(page)
        ctx.check('保存后重载保留固定暗色', ctx.api('/api/settings').get('themeMode') == 'dark'
                  and await page.js(SCHEME) == 'dark')
    finally:
        dom.request(ctx, 'PUT', '/api/settings', saved)
        for filename in files:
            dom.request(ctx, 'DELETE', '/api/page-backgrounds/' + filename)
        if shader:
            dom.request(ctx, 'DELETE', '/api/shader-presets/' + shader)
        await ctx.close(page)


async def check_settings_navigation_and_ranges(ctx):
    """设置页签、折叠焦点和三条外观滑条通过实际操作验收。"""
    saved = ctx.api('/api/settings')
    page = await dom.open_app(ctx, ctx.serve_built(), 1100, 515, reduce_motion=True)
    wallpaper = None
    scroll = "document.querySelector('.drawer-scroll')"
    click_tab = "id => document.getElementById('settings-tab-' + id).click()"
    opacity = "document.querySelector('input[aria-label=透明度]')"
    blur = "document.querySelector('input[aria-label=模糊]')"
    line_height = "document.querySelector('input[aria-label=消息行高]')"
    preview = "document.querySelector('img[alt=页面背景预览]')"
    try:
        wallpaper = await upload_color(page, '#808c98')
        dom.update_settings(ctx, pageBackgroundImage=wallpaper, pageBackgroundOpacity=.3, pageBackgroundBlurPx=0,
                            messageLineHeight=None, webgpuBackgroundEnabled=False)
        await dom.goto_app(page)
        await dom.enter_chat(ctx, page, "LONG")
        await dom.settings_open(page)
        await page.js("document.getElementById('settings-tab-global').focus()")
        await page.key("ArrowRight", 39)
        ctx.check("方向键移动页签焦点，Enter 激活之前仍显示原面板", await page.js("""(() => {
          const active = document.activeElement;
          return active.id === 'settings-tab-presets' && active.getAttribute('aria-selected') === 'false' &&
            document.getElementById('settings-tab-global').getAttribute('aria-selected') === 'true';
        })()"""))
        await page.key("Enter", 13)
        await page.wait_for("document.getElementById('settings-tab-presets').getAttribute('aria-selected') === 'true'")
        await page.key("Tab", 9)
        ctx.check("激活页签后 Tab 进入关联内容", await page.js(
            "document.getElementById('settings-panel-presets').contains(document.activeElement)"))
        await page.js(f"({click_tab})('global')")
        connection = """[...document.querySelectorAll('#settings-panel-global .settings-accordion > button')]
          .find(b => b.innerText.includes('连接与默认模型'))"""
        await page.js(f"({connection}).focus()")
        await page.key("Tab", 9)
        ctx.check("折叠区保留结构，内部字段退出键盘顺序", await page.js(f"""(() => {{
          const trigger = {connection};
          const content = document.getElementById(trigger.getAttribute('aria-controls'));
          return trigger.getAttribute('aria-expanded') === 'false' && content.inert && !content.contains(document.activeElement);
        }})()"""))
        await ctx.expand_appearance(page)
        await page.js(f"{scroll}.scrollTop = 240")
        global_scroll = await page.js(f"{scroll}.scrollTop")
        await page.js(f"({click_tab})('chat')")
        ctx.check("首次进入当前会话从顶部开始", await page.js(f"{scroll}.scrollTop === 0"))
        await page.js(f"{scroll}.scrollTop = 100")
        chat_scroll = await page.js(f"{scroll}.scrollTop")
        await page.js(f"({click_tab})('global')")
        returned_global = await page.js(f"{scroll}.scrollTop")
        await page.js(f"({click_tab})('chat')")
        returned_chat = await page.js(f"{scroll}.scrollTop")
        ctx.check("返回时分别恢复全局和当前会话的滚动位置",
                  global_scroll > 0 and chat_scroll > 0 and returned_global == global_scroll and returned_chat == chat_scroll,
                  [global_scroll, returned_global, chat_scroll, returned_chat])
        await page.js(f"({click_tab})('global')")
        await page.wait_for(preview)
        ctx.check("界面与字体在上，宽抽屉内壁纸与两条滑条并排，高级背景初始折叠", await page.js(f"""(() => {{
          const image = {preview}.getBoundingClientRect(), slider = {opacity}.getBoundingClientRect();
          const advanced = [...document.querySelectorAll('.settings-accordion > button')].find(b => b.textContent.trim() === '高级背景');
          return {line_height}.compareDocumentPosition({preview}) & Node.DOCUMENT_POSITION_FOLLOWING
            ? slider.left >= image.right + 8 && {blur}.getBoundingClientRect().top > slider.top
              && advanced.getAttribute('aria-expanded') === 'false'
            : false;
        }})()"""))

        await page.js(f"{opacity}.scrollIntoView({{block:'center'}})")
        point = await page.js(f"""(() => {{
          const r = {opacity}.getBoundingClientRect(); return [r.left, r.top + r.height / 2, r.width];
        }})()""")
        left, y, width = point
        x = left + width * .7
        await page.mouse("mouseMoved", x, y)
        await page.mouse("mousePressed", x, y, button="left", buttons=1, clickCount=1)
        await page.wait_for(f"{opacity}.valueAsNumber > 55 && document.querySelector('.drawer-wrapper').classList.contains('is-adjusting-background')")
        await page.mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=1)
        await page.wait_for("!document.querySelector('.drawer-wrapper').classList.contains('is-adjusting-background')")
        clicked = await page.js(f"{opacity}.valueAsNumber")
        thumb = left + 7 + (width - 14) * clicked / 100
        await page.mouse("mouseMoved", thumb, y)
        await page.mouse("mousePressed", thumb, y, button="left", buttons=1, clickCount=1)
        await page.wait_for("document.querySelector('.drawer-wrapper').classList.contains('is-adjusting-background')")
        await page.mouse("mouseMoved", thumb + width * .12, y, button="left", buttons=1)
        await page.wait_for(f"{opacity}.valueAsNumber > {clicked}")
        await page.mouse("mouseReleased", thumb + width * .12, y, button="left", buttons=0, clickCount=1)
        await page.wait_for("!document.querySelector('.drawer-wrapper').classList.contains('is-adjusting-background')")
        ctx.check("点击轨道和拖动都更新读数与壁纸预览，松手恢复设置页",
                  await page.js(f"""Math.abs(Number(document.querySelector('.page-background-image').style.opacity) - {opacity}.valueAsNumber / 100) < .01
                    && {opacity}.style.getPropertyValue('--appearance-range-progress') === {opacity}.value + '%'"""))
        await page.key("Tab", 9)
        await page.js(f"{blur}.focus()")
        await page.key("ArrowRight", 39)
        ctx.check("模糊可用方向键逐步调节，并显示像素与键盘焦点", await page.js(f"""(() => {{
          const css = getComputedStyle({blur});
          return {blur}.valueAsNumber === 1 && {blur}.getAttribute('aria-valuetext') === '1 像素' &&
            css.outlineStyle === 'solid' && css.outlineWidth === '2px' &&
            document.querySelector('.page-background-image').style.filter.includes('1px');
        }})()"""))
        await page.js(f"{line_height}.focus()")
        await page.key("End", 35)
        await page.key("ArrowLeft", 37)
        ctx.check("消息行高使用数值读数和原有步进", await page.js(
            f"{line_height}.valueAsNumber === 2.35 && {line_height}.getAttribute('aria-valuetext') === '2.35 倍'"))

        await page.send('Emulation.setDeviceMetricsOverride', width=420, height=770, deviceScaleFactor=1, mobile=False)
        await page.wait_for(f"{opacity}.getBoundingClientRect().top >= {preview}.getBoundingClientRect().bottom")
        ctx.check("窄抽屉内预览和滑条上下排布，没有横向滚动", await page.js(
            f"{scroll}.scrollWidth <= {scroll}.clientWidth + 1"))
        await page.js("$click(document.querySelector('.drawer-panel'), '取消')")
        await page.wait_for("document.querySelector('.app-notify-panel')")
        await page.js("$click(document.querySelector('.app-notify-panel'), '确定')")
        await page.wait_for("!$drawerOpen()")
        persisted = ctx.api('/api/settings')
        ctx.check("取消恢复已保存的透明度、模糊和消息行高",
                  persisted["pageBackgroundOpacity"] == .3 and not persisted["pageBackgroundBlurPx"]
                  and persisted["messageLineHeight"] is None and await page.js(
                      "Number(document.querySelector('.page-background-image').style.opacity) === .3"))
        await page.send('Emulation.setDeviceMetricsOverride', width=1100, height=515, deviceScaleFactor=1, mobile=False)
        await dom.settings_open(page)
        ctx.check("关闭再打开时从页签顶部开始", await page.js(f"{scroll}.scrollTop === 0"))
        await ctx.expand_appearance(page)
        await page.js(f"{blur}.focus()")
        await page.key("ArrowRight", 39)
        await page.js("$click(document.querySelector('.drawer-panel'), '保存设置')")
        await page.wait_for("!$drawerOpen()")
        ctx.check("保存后写入调节值并保留实际预览",
                  ctx.api('/api/settings')["pageBackgroundBlurPx"] == 1 and await page.js(
                      "document.querySelector('.page-background-image').style.filter.includes('1px')"))
    finally:
        dom.request(ctx, 'PUT', '/api/settings', saved)
        if wallpaper:
            dom.request(ctx, 'DELETE', '/api/page-backgrounds/' + wallpaper)
        await ctx.close(page)


async def check_focus_indicators(ctx):
    """深浅色的关闭按钮、下拉和输入框共用键盘焦点轮廓。"""
    saved = ctx.api('/api/settings')
    url = ctx.serve_built()
    close = "document.querySelector('button[aria-label=关闭设置抽屉]')"
    composer = "document.querySelector('.chat-input-card-morph textarea')"
    geometry = {}
    probe = """(control, surface = control) => {
      const style = getComputedStyle(control);
      return {focused: control.matches(':focus-visible'),
        line: [style.outlineStyle, style.outlineWidth, style.outlineOffset],
        hasDot: style.backgroundImage.includes('radial-gradient'),
        contrast: $contrast($rgb(style.outlineColor), $rgb(getComputedStyle(surface).backgroundColor))};
    }"""
    try:
        for mode in ('light', 'dark'):
            dom.update_settings(ctx, themeId='teal', themeMode=mode)
            page = await dom.open_app(ctx, url, 1280, 900, reduce_motion=True)
            try:
                await page.wait_for(composer)
                await page.key('Tab', 9)
                text_area = await page.js(f"""(() => {{
                  const field = {composer};
                  const shell = field.closest('.chat-input-card-morph');
                  document.activeElement.blur();
                  const before = [getComputedStyle(field).boxShadow, getComputedStyle(shell).boxShadow];
                  field.focus({{preventScroll:true}});
                  const after = [getComputedStyle(field).boxShadow, getComputedStyle(shell).boxShadow];
                  return {{...({probe})(field, shell), oneRing: before.every((shadow, i) => shadow === after[i])}};
                }})()""")
                ctx.check(f'{mode} 聊天输入区仅编辑区显示焦点轮廓',
                          text_area['focused'] and not text_area['hasDot'] and text_area['oneRing']
                          and text_area['line'] == ['solid', '2px', '2px'], text_area)
                await page.shot(f'focus-{mode}-composer')

                await dom.settings_open(page)
                await ctx.expand_appearance(page)
                await page.wait_for(MODE_TRIGGER)
                await page.js(f"{close}.focus({{preventScroll:true}})")
                close_style = await page.js(f"({probe})({close}, document.querySelector('.drawer-panel'))")
                await page.shot(f'focus-{mode}-close')
                await page.js(f"{MODE_TRIGGER}.scrollIntoView({{block:'center',behavior:'instant'}}); {MODE_TRIGGER}.focus()")
                select_style = await page.js(f"({probe})({MODE_TRIGGER}, {MODE_TRIGGER}.closest('.settings-accordion'))")
                ctx.check(f'{mode} 关闭按钮和下拉共用清晰的单层焦点轮廓',
                          all(style['focused'] and not style['hasDot'] and style['contrast'] >= 3
                              and style['line'] == ['solid', '2px', '2px'] for style in (close_style, select_style)),
                          (close_style, select_style))
                geometry[mode] = [text_area['line'], close_style['line'], select_style['line']]
                await page.shot(f'focus-{mode}-select')

                await page.key('ArrowDown', 40)
                await page.key('ArrowUp', 38)
                active = await page.js(f"""(() => {{
                  const trigger = {MODE_TRIGGER};
                  const row = document.getElementById(trigger.getAttribute('aria-activedescendant'));
                  const selected = document.getElementById(trigger.getAttribute('aria-controls')).querySelector('[aria-selected=true]');
                  return {{outline: ({probe})(row, row.parentElement).line, separate: !!selected && selected !== row,
                    onlyRow: getComputedStyle(trigger).outlineStyle === 'none'}};
                }})()""")
                ctx.check(f'{mode} 候选项轮廓随方向键移动并与已选项区分',
                          active['outline'] == ['solid', '2px', '-2px'] and active['separate'] and active['onlyRow'], active)
                await page.key('Escape', 27)
                ctx.check(f'{mode} Esc 后触发器恢复焦点轮廓',
                          await page.js(f"document.activeElement === {MODE_TRIGGER} && ({probe})({MODE_TRIGGER}).line[0] === 'solid'"))

                await page.wait_for("!document.querySelector('[role=listbox][aria-label=外观模式]')")
                await page.js(f"{close}.focus({{preventScroll:true}})")
                point = await page.js(f"""(() => {{
                  const r = {MODE_TRIGGER}.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2];
                }})()""")
                await page.mouse('mouseMoved', *point)
                await page.mouse('mousePressed', *point, button='left', buttons=1, clickCount=1)
                await page.mouse('mouseReleased', *point, button='left', clickCount=1)
                pointer_state = await page.js(f"({{open: {MODE_TRIGGER}.getAttribute('aria-expanded') === 'true', "
                                              f"focus: ({probe})({MODE_TRIGGER})}})")
                ctx.check(f'{mode} 鼠标点击选择器时只呈现展开状态',
                          pointer_state['open'] and pointer_state['focus']['line'][0] == 'none', pointer_state)
                await page.key('Escape', 27)

                await page.send('Emulation.setEmulatedMedia', features=[{'name': 'forced-colors', 'value': 'active'}])
                await page.key('Tab', 9)
                await page.js(f"{close}.focus({{preventScroll:true}})")
                ctx.check(f'{mode} 强制颜色下使用系统高亮焦点',
                          await page.js(f"""matchMedia('(forced-colors: active)').matches
                            && getComputedStyle({close}).getPropertyValue('--color-focus-ring').trim().toLowerCase() === 'highlight'
                            && ({probe})({close}).line[0] === 'solid'"""))
            finally:
                await ctx.close(page)
        ctx.check('深浅色下同一控件的轮廓几何一致', geometry['light'] == geometry['dark'], geometry)
    finally:
        dom.request(ctx, 'PUT', '/api/settings', saved)
