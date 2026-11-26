# Windows 服务管理器

管理器使用 Tauri 2、系统 WebView2 和 Windows 托盘。浏览器加载预构建的聊天界面。FastAPI 在同一个进程里提供静态资源与 API，默认监听本机 9081 和扩展使用的 9091。

## 构建

在 Windows x64 构建机安装 Python 3.11、Node 22、Rust MSVC、Visual Studio C++ 构建工具及 .NET 8 SDK。项目根目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt pyinstaller==6.22.3
dotnet tool install --global vpk --version 1.2.161
.venv/Scripts/python desktop/build_windows.py --version 0.810.0
```

本地打包会复用脚本上次成功安装的前端依赖，并重新构建前端。首次打包、依赖文件或 Node 安装环境变化时会执行 `npm ci`。加 `--clean-web-deps` 可强制重装依赖。若已有所需版本的 `frontend/dist`，可用 `--reuse-web` 直接复用产物。GitHub Actions 发布构建会执行干净安装，并缓存 npm 下载。

首次打包会下载固定版本的 UPX，验证 SHA-256 后缓存在 `temp/windows-build`。构建将词表以 XZ 随包分发，并在签名前压缩管理器和选定的原生扩展。打包日志会输出免安装包解压后的程序字节数。桌面程序使用 Windows 10 或更新版本自带的 Universal CRT。

版本参数使用三段 SemVer。生成的安装包和可自更新的 Portable.zip 在 `dist/windows/`。同一目录中的 `releases.win-x64.json` 和 `*-full.nupkg` 是应用更新必需的资产。保留上次发布的完整包再构建会生成差分包。发版时把这些文件作为同一 GitHub Release 的附件上传。仓库的 Windows 发布工作流也支持手动构建。需要签名时，可通过 Velopack 的 `VPK_SIGN_PARAMS` 或其签名服务签署内部程序，打包完成后再对输出的 `*-Setup.exe` 签名。签名凭据只保存在构建者环境。

## 目录与运行

- 安装器默认使用 `%LOCALAPPDATA%\SimpleTavern`。可以选择其他空文件夹，选择 `D:\` 这样的盘符根目录会将安装路径设为 `D:\SimpleTavern`。重装沿用已有目录，换盘前请先卸载。数据保存在 `%LOCALAPPDATA%\SimpleTavern.User\data`。
- 免安装版从压缩包根目录的启动器运行，数据和 `manager.json` 位于 `current` 之外。整个目录需可写。首次启动可从已停止写入的旧版复制 data；原文件保留。
- 已配置的本地语音引擎使用各自的网关环境。受管进程由聊天服务启动。外部网关可检查连接。Janitor 扩展位于 `current/extensions` 中，可复制到固定位置后在浏览器中加载。
- 管理器和服务通过父子进程管道交换固定命令与状态。退出时先暂停新写入，等活动操作结束，再停止服务。浏览器保持原页面，输入文字和待发送图片仍在原标签中。再次手工打开或刷新页面会加载最新前端。
- 本机服务故障时管理窗口仍可用。端口冲突可在窗口内修改端口，扩展若使用了自定义端口，需同步修改扩展地址。托盘的「退出并停止服务」才结束进程。静默更新由 Velopack 在进程退出后执行。

## 验证

```powershell
.venv/Scripts/python tools/desktop-check/service.py
```

服务回归使用临时数据与模拟模型，覆盖词表加载、Vertex JWT 鉴权、流式生成期间等待退出、回复落盘、恢复接收请求及关闭。GitHub Actions 从生成的免安装包解压后运行这项检查。管理器的数据导入测试可用 `cargo test --manifest-path desktop/Cargo.toml` 运行。

在 Windows 桌面会话中可验证完整升级。以下命令复用同一份刚构建的前后端。QA 包使用独立的安装标识、窗口标识、数据目录及本地更新源。常规发行版从项目的 GitHub Releases 检查更新。

```powershell
$qa = "temp/desktop-qa/versions"
.venv/Scripts/python desktop/build_windows.py --qa --reuse-service --reuse-web --version 1.0.1 --output "$qa/feed"
New-Item -ItemType Directory -Force "$qa/first"
Copy-Item "$qa/feed/*-Setup.exe","$qa/feed/*-Portable.zip" "$qa/first"
.venv/Scripts/python desktop/build_windows.py --qa --reuse-service --reuse-web --version 1.0.2 --output "$qa/feed"
.venv/Scripts/python tools/desktop-check/packages.py --first "$qa/first" --expected 1.0.2 --qa-feed "$qa/feed" --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

两种包分别在新目录运行，验证收至托盘后仍可聊天、再次启动唤回窗口、暂时无法下载后可重试、更新后数据及端口保留。浏览器使用独立临时配置检查原标签页的未发送草稿。运行截图保存至 `first` 同级的 `run-*` 目录。GUI 验收额外使用 Python 的 `pywin32` 和 `websockets>=15`。
