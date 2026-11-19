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
MODE_FIELD = """[...document.querySelectorAll('.settings-field')].find(e=>e.querySelector('.settings-label')?.textContent.trim()==='外观模式')"""
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
        await page.js(f"""(() => {{const select = {MODE_FIELD}.querySelector('select');
          select.value = 'dark'; select.dispatchEvent(new Event('change', {{bubbles:true}}));}})()""")
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
        await page.wait_for(f"{MODE_FIELD}?.querySelector('select[aria-label=外观模式]')")
        contrast = await page.js(f"""(() => {{
          const select = {MODE_FIELD}.querySelector('select'), style = getComputedStyle(select);
          const panel = $rgb(getComputedStyle(document.documentElement).backgroundColor);
          const border = $contrast($rgb(style.borderColor), $rgb(style.backgroundColor));
          select.focus();
          return {{text: $contrast($rgb(style.color), $rgb(style.backgroundColor)),
                   border, focus: $contrast($rgb(getComputedStyle(select).getPropertyValue('--color-focus-ring')), panel),
                   focused: document.activeElement === select, overflow: document.documentElement.scrollWidth > innerWidth}};
        }})()""")
        ctx.check('窄屏亮色选择器的文字、轮廓和键盘焦点可读', contrast['text'] >= 4.5 and contrast['border'] >= 3
                  and contrast['focus'] >= 3 and contrast['focused'] and not contrast['overflow'], contrast)

        async def choose_dark():
            await page.js(f"""(() => {{const select = {MODE_FIELD}.querySelector('select');
              select.focus(); select.value = 'dark'; select.dispatchEvent(new Event('change', {{bubbles:true}}));}})()""")
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
