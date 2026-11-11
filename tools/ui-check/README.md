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

## 开发服务器和构建产物

前端只构建一次，放到 `temp/ui-check/dist`，不会碰 `frontend/dist`。构建前先跑 `vue-tsc -b`，和 `npm run build` 一致；类型检查不过就直接报错退出。各检查跑在哪里：

| 检查 | 环境 | 说明 |
|---|---|---|
| `built` | 构建产物 | 模糊、设置页滚动，以及构建后的 CSS 不能有只带 `-webkit-` 前缀的模糊规则 |
| `core` | 构建和开发各一遍 | 只操作 DOM：进入长会话定位、搜索跳转和计数、原地删除、弹窗动效、Esc 只关一层 |
| `modals` | 构建和开发各一遍 | 只操作 DOM：PNG 内嵌卡确认、OAuth 登录弹窗的打开、按帧动效和各种关闭 |
| `dev_built` | 不开页面 | 比较 `core` 和 `modals` 在两个环境的结果，要和它们一起跑 |
| `themes`、`viewports`、`long_chat`、`errors`、`secrets` | 构建产物 | 沙箱核对，见下一节 |
| 其余 | 开发服务器 | 直接操作 Vue 实例 |

两者结果可能不同：手写的 `backdrop-filter` 在开发服务器上有效，构建后会失效。“确认”以构建产物为准。

要和修改前对照，先把旧版本 `git archive` 出来单独构建，再让检查用它，`--built-only` 表示不跑开发服务器那一遍：

```bash
venv/Scripts/python tools/ui-check/run.py --only built,core --built-only --dist temp/control/旧提交/dist
```

## 沙箱核对

- `themes`：7 个主题在透明度 30% 下各拍主界面、设置和弹窗。脚本只查 `data-theme`、主色互不相同、主按钮对比度，**看不看得清要人看截图**（`theme-*.png`）。
- `viewports`：1920、1440、1100、420 宽，量 `scrollWidth`、出界元素和控件是否被挡。先注入超宽元素和遮挡层，确认量得出来。截图是 `viewport-*.png`。
- `long_chat`：320 条以上的会话，量打开、发送、保存和冷启动的耗时。只记录数字，不设门槛，无头软件渲染和模拟模型下的数字只能看量级。
- `errors`：让模拟上游返回 401、429、500、流内错误和断连接，看错误栈里的 requestId 和用户消息；上游恢复后能否续上；REST 错误同样要进错误栈。流内错误时，错误提示里要有上游发来的那段独特原文；断连接时，提示里要有“中断、断开、中途、断流、意外结束、提前结束、未完整、不完整、截断”或对应英文词之一，且不能说“无法连接”；两种情况半句都要保留。
- `secrets`：把假密钥换成真实格式的探针发给上游，上游还会回显。然后扫服务日志、HTTP 日志、会话和角色导出、三种设置备份，也确认真实密钥原文没有进沙箱。只输出文件名、字段名和次数。放在最后跑，这样能扫到前面所有检查产生的日志。

## 安全

- 真实 `data/` 只读。运行时复制到 `temp/ui-check/data`，清空密钥，把所有接口地址指向内置的模拟模型，复制后再扫一遍，发现疑似密钥就停止。
- 不连接任何外部服务，不用真实模型。
- 默认端口是 9381、9382、9391、9399、9433，和常用的 9081、9091 分开。端口被占用时直接报错，不会关闭别的进程。
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
- 前端全部弹窗和分支没有都覆盖到。OAuth 只测弹窗本身，没有点“开始登录”，真实授权流程要作者走。

## 加检查

在 `checks.py` 或 `dom_checks.py` 里写一个 `async def check_xxx(ctx)`，并加进 `checks.py` 末尾的 `CHECKS`。

- 判断结果用 `ctx.check(名称, 条件, 详情)`，只记录数字不判断对错用 `ctx.note(名称, 值)`。
- 新页面用 `await ctx.page()`，它会关掉“未总结消息达到阈值”这类挡操作的提示，用完调用 `await ctx.close(page)`。
- 动效要按帧量：把 `--transition-normal` 拉长后采样，不要只看最终状态。
- 构建产物里没有 Vue 实例，只能操作 DOM，不能用 `__chat()`、`__drawer()`。这类检查放在 `dom_checks.py`，用 `open_app` 开页面。
- 每项新检查都要有对照：在修复前的构建上跑一次，或注入错误状态，确认它能失败。
- 会往沙箱发消息的检查放在后面，发送会改变下次首先加载的会话。
