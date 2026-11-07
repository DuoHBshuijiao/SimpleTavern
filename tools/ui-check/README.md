# 前端回归检查

在无头 Chromium 里驱动真实前端和后端，检查弹窗保存、弹窗动效、滚动定位、搜索等容易被改坏的行为。不属于产品依赖。

## 运行

在仓库根目录，用项目虚拟环境的 Python：

```bash
venv/Scripts/python tools/ui-check/run.py
```

只跑部分检查，或列出全部检查：

```bash
venv/Scripts/python tools/ui-check/run.py --only entry,search
```

```bash
venv/Scripts/python tools/ui-check/run.py --list
```

全部通过时退出码为 0，有失败时为 1。

## 安全

- 真实 `data/` 只读。运行时复制到 `temp/ui-check/data`，清空密钥，把所有接口地址指向内置的模拟模型，复制后再扫一遍，发现疑似密钥就停止。
- 不连接任何外部服务，不用真实模型。
- 默认端口是 9381、9391、9399、9433，和常用的 9081、9091 分开。端口被占用时直接报错，不会关闭别的进程。
- 截图在 `temp/ui-check/shots`，会包含您的角色和聊天内容。`temp/` 已被 Git 忽略，每次运行都会重建。

## 前提

- `data/` 里至少有 3 个单聊和 1 个群聊，不够时会明确报错。消息少的会话会在沙箱里自动补长。
- 依赖 `frontend/node_modules` 和项目虚拟环境（`websockets` 随 `uvicorn[standard]` 安装）。
- 需要 Chromium：优先读环境变量 `UI_CHECK_CHROME`，其次找 Playwright 下载的版本，最后找系统 Chrome。

## 测不到的

- 真实模型的流式节奏，这里是本地模拟。
- WebGPU 着色器背景，无头浏览器没有显卡适配器。
- 真机字体观感。判断视觉效果还是要看截图或真机。
- 判断带图片背景的效果时，先把透明度调到合适档位（约 30%），不要用 100% 下结论。
- 前端全部弹窗和分支没有都覆盖到，比如 PNG 内嵌卡导入、OAuth 登录。

## 加检查

在 `checks.py` 里写一个 `async def check_xxx(ctx)`，并加进文件末尾的 `CHECKS`。

- 判断结果用 `ctx.check(名称, 条件, 详情)`。
- 新页面用 `await ctx.page()`，它会关掉“未总结消息达到阈值”这类挡操作的提示，用完调用 `await ctx.close(page)`。
- 动效要按帧量：把 `--transition-normal` 拉长后采样，不要只看最终状态。
- 会往沙箱发消息的检查放在后面，发送会改变下次首先加载的会话。
