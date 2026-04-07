<div align="center">

<img src="frontend/public/image1.jpeg" alt="SimpleTavern" />

<small>AI 生成，仅作参考</small>

**SimpleTavern**

本地单用户 AI 角色扮演应用。前端为 Vue 3 + Vite + TypeScript，后端为 FastAPI（SSE 流式输出），数据以 `data/` 目录下的 JSON 文件持久化，不依赖传统数据库。

</div>

---

<p align="center">
  <img src="frontend/public/image2.jpeg" alt="应用界面" />
  <br />
  <small>AI 生成，多彩主题</small>
</p>

---

## 技术栈概览

| 层级 | 主要技术 | 说明 |
| --- | --- | --- |
| 前端 UI | Vue 3、Pinia、Vue Router | 组件化 SPA |
| 前端构建 | Vite 7、TypeScript、`vue-tsc` | 开发热更新；生产构建前做类型检查 |
| 样式 | Tailwind CSS 4（`@tailwindcss/vite`）、PostCSS | 与工具类、自定义 `variables.css` 等协同 |
| 后端 | FastAPI、Uvicorn | REST + SSE；路由统一挂在 `/api` 下（开发时 Vite 将 `/api` 代理到 `http://127.0.0.1:9091`） |
| 持久化 | 本地 JSON 文件 | 设置、角色、会话等位于 `data/`，见后端 `storage` 模块 |

后端 Python 依赖版本下限见 `backend/requirements.txt`（如 `fastapi>=0.110`、`pydantic>=2.6`、`portalocker` 等）。前端依赖见 `frontend/package.json`。

---

## 功能要点

**聊天助手**：内置可调用工具的 Agent 流程，可与剧情对话、长期记忆摘要、角色卡生成等结合。

**群聊定制**：群聊模式下可为不同角色分别配置模型、系统提示、温度等，减少「千人一面」。

**主题与界面**：玻璃拟态风格（半透明、磨砂、细边框）。品牌色与全局变量可在 `frontend/src/styles/variables.css` 的 `:root` 中调整（如 `--color-brand`、`--glass-bg` 等）。

---

## 后端 API 与数据（摘要）

| 类别 | 路径前缀或示例 | 说明 |
| --- | --- | --- |
| 健康检查 | `GET /api/health` | 服务存活探测 |
| 设置 | `/api/settings` | 读写应用设置（含 OpenAI 兼容端点与密钥等） |
| 角色与会话 | `/api/characters`、`/api/chats` | CRUD、消息、图片、群聊成员等 |
| 生成 | `/api/generate/*` | 流式生成、群聊、插话等 |
| 助手 | `/api/assistant/*` | 助手会话与流式接口 |
| 其他 | `/api/llm`、`/api/avatars`、`/api/fonts`、`/api/import_export`、`/api/tokenizer`、`/api/update` 等 | 模型列表、头像、字体、导入导出、分词、更新检查等 |
| 剪贴板 | `POST /api/clipboard/resolve-rich-paste` | 富文本粘贴解析（服务端对本地文件访问有安全边界，见下文「已知限制」） |

数据目录默认包含 `settings`、`characters`、`chats` 等 JSON 结构；无 SQLite 或其它数据库引擎。

---

## 环境要求

| 项目 | 版本或说明 |
| --- | --- |
| Python | 3.10+ 与 pip（建议使用当前仍受支持的 3.x 版本） |
| Node.js | 16+ 与 npm |
| Git | 克隆仓库时使用；也可从 Releases 下载源码包 |

---

## 获取与运行

### 自 Releases 安装（推荐）

在 [GitHub Releases](https://github.com/DuoHBshuijiao/SimpleTavern/releases) 下载源码压缩包，解压进入目录后执行：

| 系统 | 命令 |
| --- | --- |
| Windows | `python deploy.py` |
| Linux / macOS | `python3 deploy.py` 或 `chmod +x deploy.sh` 后 `./deploy.sh` |

脚本将检查环境、创建 `venv/`、安装前后端依赖、构建前端，并启动后端（默认 **9091**）与前端预览（默认 **9081**），通常会尝试打开浏览器。停止服务：`Ctrl+C`。

根目录还提供 `deploy.sh`、`deploy.bat`；手动分步说明见下文。

### 安卓 Termux

勿将项目放在 **`/sdcard` 共享存储** 下运行：权限与挂载限制易导致 `python -m venv` 失败。请把仓库放在 Termux 私有目录（如 `$HOME`），用 `pkg` 安装 `python`、`nodejs`、`git` 等后再执行 `python deploy.py`。若使用 zip 包，同样在 `$HOME` 下解压。

### 本地开发（前后端分离调试）

| 步骤 | 目录 | 命令 |
| --- | --- | --- |
| 后端 | `backend` | 激活虚拟环境后：`python -m uvicorn app.main:app --reload --port 9091`（局域网可访问可加 `--host 0.0.0.0`） |
| 前端 | `frontend` | `npm install` 后：`npm run dev`（通过 Vite 代理访问 `/api`，开发服务器默认监听 **9081**，见 `vite.config.ts`） |

生产形态可先 `npm run build`，再用 `npm run preview -- --port 9081 --host` 提供静态资源，行为与一键部署脚本中的前端启动方式一致。

### 手动部署（简要）

在仓库根目录创建并激活 `venv`，于 `backend` 执行 `pip install -r requirements.txt`；于 `frontend` 执行 `npm install` 与 `npm run build`。启动顺序：先后端再前端预览。若 PowerShell 禁止脚本，可对当前用户执行 `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`，或使用 `venv\Scripts\activate.bat`。

---

## 模型与凭据（OpenAI 兼容）

在应用内「设置」中配置 **Base URL**、**API Key**、**Model** 等。密钥与连接信息会写入 `data/settings.json`（**明文存储**），请仅在可信本机环境使用并做好文件权限与备份策略。

---

## 已知限制与实现说明

以下条目摘自源码注释或模块文档字符串，供排障与二次开发对照。

| 主题 | 说明 | 出处（仓库内） |
| --- | --- | --- |
| Tailwind v4 与 `group-hover` | `group-hover:opacity-*` 位于 CSS Layer；若在非 Layer 的自定义 CSS 中重复定义 `opacity-*`，会覆盖上述变体，导致悬停透明度不生效。请勿在 `frontend/src/styles/utilities.css` 等处重复定义与 Tailwind 冲突的 `opacity-*`。 | `utilities.css` 注释 |
| 玻璃拟态与构建 | 部分旧类名（如 `.glass-panel-floating`、`.stained-glass`）已弃用，宜改用 Tailwind `backdrop-*`。注释中说明：esbuild 压缩 CSS 时可能改变 `backdrop-filter` 内空格，导致 `saturate` 等失效，故推荐工具类路径。 | `glass.css` |
| MessageList 虚拟滚动与顶栏几何 | 2026-04 曾出现消息列表在每个会话各自固定的滚动阈值处突然重定位。根因是禁用浏览器默认 `overflow-anchor`、改用 `ref/watch` 间接同步虚拟窗口，并在高度测量阶段手动改 `scrollTop`，导致窗口切换与高度写回拆成多轮更新。当前实现依赖 `frontend/src/components/chat/MessageList.vue` 中默认 scroll anchoring、直接 computed 的 `windowStart/windowEnd`；原生滚动条与顶栏重叠的问题暂不通过修改 scrollport 几何解决，后续更适合改成独立自绘滚动条。 | `MessageList.vue` |
| 剪贴板与本地路径 | 自 QQ 等应用粘贴的 HTML 可能带 `file://` 图片链接；浏览器无法直接读取任意本地路径，此类图片在纯前端提取流程中不可用。后端剪贴板接口仅允许解析**系统临时目录**下的路径，以降低任意文件读取风险。 | `ChatInput.vue`、`clipboard.py` |
| SSE 与界面响应 | 前端 SSE 处理约每 20 个事件让出主线程一次，减轻大量缓冲时界面「憋到最后才刷新」的卡顿感。 | `frontend/src/api/sse.ts` |
| 存储并发与查找 | 单用户场景仍可能因前端并发请求产生短暂并发写，对关键写路径使用文件锁避免撕裂。按 `chatId` 定位会话需在无 DB 设计下扫描角色目录，数据量大时存在额外 I/O。 | `backend/app/storage.py` |
| CORS | 后端默认 `allow_origins=["*"]`，便于本地开发；若将服务暴露于不可信网络，需自行收紧策略。 | `backend/app/main.py` |
| 部署脚本（Windows） | 脚本内对 Windows 命令行、引号等有特殊处理，避免嵌套 `cmd` 引号问题。 | `deploy.py` |

**运维常见问题**（非代码缺陷）：9091 / 9081 端口占用时可改 `uvicorn` 与 `vite preview` 的端口参数；系统找不到 `python` / `npm` 时请安装或改用 `py`、`python3` 等。

---

## 其它仓库资源

从 Janitor AI（JAI）迁移聊天记录到本地时，必须在 Chromium 系浏览器中 **手动安装** 本仓库内 `extensions/simpletavern-janitor-bridge/` 目录对应的未打包扩展（例如在 Chrome 或 Edge 中打开「扩展程序」，开启「开发者模式」，选择「加载已解压的扩展程序」并指向该目录）。`deploy.py`、pip 与 npm **不会**自动安装该扩展；若未加载扩展，则无法在 Janitor 站点与本地 SimpleTavern 之间完成聊天数据桥接（后端 `/api/import/janitor/*` 与前端导入流程依赖扩展在页面侧抓取并上报数据）。

| 路径 | 说明 |
| --- | --- |
| `extensions/simpletavern-janitor-bridge/` | Janitor AI 页面桥接：使用 `chrome.*` API，将聊天内容提交至本地 API；需按上段说明自行加载；与主应用分离部署。 |

---

## 许可证

MIT License。
