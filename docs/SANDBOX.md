# 并行沙箱使用说明

沙箱与日常使用的生产实例**同时运行**，互不抢端口、不写同一份数据。用来做浏览器点按核对，或对照 [`docs/specs/BACKEND-API.md`](specs/BACKEND-API.md) / [`docs/specs/FRONTEND-FEATURES.md`](specs/FRONTEND-FEATURES.md) 做黑盒检查。

本仓库**不**内置 Playwright / pytest / Vitest。点按用普通浏览器或 Cursor 内置浏览器即可。

## 和生产的区别

| | 生产 | 沙箱 |
| --- | --- | --- |
| 启动 | `python deploy.py` 或手动 uvicorn + Vite | 仓库根目录 `python sandbox.py` |
| 前端 | `http://127.0.0.1:9081` | `http://127.0.0.1:9181` |
| 后端 | `http://127.0.0.1:9091` | `http://127.0.0.1:9191` |
| 数据目录 | 仓库 `data/` | 仓库 `data-sandbox/` |
| 前端形态 | 一键脚本用 `npm run preview` | 脚本用 `npm run dev`（带 `/api` 代理） |

沙箱前端把 `/api` 代理到 **9191**，不会打进生产 9091。

## 准备

1. 至少成功跑过一次 [`deploy.py`](../deploy.py)，保证存在：
   - `venv/`（Windows：`venv\Scripts\python.exe`）
   - `frontend/node_modules/`
2. 生产实例可以继续开着（9081/9091）。
3. **不要**占用 9181、9191。被占用时脚本直接退出，**不会**结束生产进程。

## 启动

在仓库根目录：

```bash
python sandbox.py
```

看到类似输出即就绪：

```text
沙箱已就绪（生产 9081/9091 与 data/ 未改动）
  前端: http://127.0.0.1:9181
  后端: http://127.0.0.1:9191/api/health
  数据: .../data-sandbox
浏览器点按请打开上述前端地址。Ctrl+C 结束沙箱进程。
```

停止：在运行 `sandbox.py` 的终端按 **Ctrl+C**。脚本会结束它拉起的前后端子进程。

Windows 若提示无法加载脚本，用 `python sandbox.py`，不要依赖未授权的 `.ps1`。

## 浏览器点按

1. 打开 **`http://127.0.0.1:9181`**，不要打开 9081（那是生产）。
2. Cursor 内置浏览器同样导航到 9181，再做点击、输入、截图。
3. 核对界面对照 [`FRONTEND-FEATURES.md`](specs/FRONTEND-FEATURES.md)；核对 HTTP/SSE 对照 [`BACKEND-API.md`](specs/BACKEND-API.md)。
4. 可直接打沙箱后端：`GET http://127.0.0.1:9191/api/health` 应返回 `{"ok": true}`。

## 数据怎么初始化

首次启动（`data-sandbox/settings.json` 还不存在）时：

- 若生产有 `data/settings.json`：**只复制这一份**（含 API Key、API 预设、全局外观与生成默认值等）。
- 若生产没有设置文件：后端按默认 `Settings` 在沙箱里新建。

之后再启动默认**不覆盖**沙箱里已改过的设置。需要重新从生产抄 Key / 预设时：

```bash
python sandbox.py --refresh-settings
```

`--refresh-settings` 会覆盖沙箱 `settings.json`，不会删除沙箱里已创建的角色、会话等其它文件。

### 不会复制的内容

下列仍从空目录由后端自动创建，或保持缺失：

- 角色、会话、群聊、世界书、头像
- `oauth_tokens.json`（GitHub Copilot / OpenAI Codex 须在沙箱里重新登录）
- TTS 缓存、HTTP 日志、各类索引 JSON
- `fonts/`、`page_backgrounds/`、`shader_presets/`、`huggingface/`

因此：设置里若还记着生产字体文件名或背景图文件名，沙箱里文件不存在，界面会回退默认外观。本机 TTS 模型不会从生产缓存复用，体积大，需要时在沙箱内另行下载。

Janitor 浏览器扩展写死生产 `127.0.0.1:9091`，沙箱收不到该扩展的导入。

## 环境变量（脚本会注入）

未设置时，产品行为与过去完全一致（`data/` + 9081/9091）。

| 变量 | 沙箱取值 | 作用 |
| --- | --- | --- |
| `SIMPLETAVERN_DATA_DIR` | 仓库下 `data-sandbox` 的绝对路径 | 后端读写的数据根目录 |
| `SIMPLETAVERN_FRONTEND_PORT` | `9181` | Vite 开发/预览端口 |
| `SIMPLETAVERN_API_PROXY` | `http://127.0.0.1:9191` | 前端 `/api` 代理目标 |

相对路径的 `SIMPLETAVERN_DATA_DIR` 相对**进程当前工作目录**解析。`sandbox.py` 始终传入绝对路径。不要在 `backend/` 目录下手写相对路径 `data-sandbox`，否则会落到 `backend/data-sandbox`。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `找不到虚拟环境 Python` | 先在仓库根运行 `python deploy.py` 完成安装。 |
| `找不到前端依赖` | 在 `frontend` 执行 `npm install`。 |
| `沙箱后端/前端端口已被占用` | 关掉占用 9181/9191 的旧沙箱；不要去杀 9081/9091。 |
| 点按后改的是生产角色/会话 | 地址栏是否为 **9181**。9081 是生产。 |
| 测模型失败、没有 Key | 确认 `data-sandbox/settings.json` 已有预设；或加 `--refresh-settings` 再启动。 |
| OAuth 提示未登录 | 沙箱不复制 token，在沙箱设置里重新登录。 |
| 字体/背景空白 | 未复制资源文件，属预期；在沙箱设置里重新选字体或上传背景。 |
| 改完代码沙箱前端没更新 | 沙箱走 Vite `dev`，保存后应热更新；若进程已死，Ctrl+C 后重新 `python sandbox.py`。 |

## 不要做的事

- 不要把 `data-sandbox/` 提交进 git（已在 `.gitignore`）。
- 不要在沙箱流程里加 pytest / Vitest / Playwright 或 `data-testid`。
- 不要改 `deploy.py` 的默认端口来“兼做沙箱”。
- 不要把沙箱 `settings.json` 拷回 `data/`，除非你明确要覆盖生产 Key。
