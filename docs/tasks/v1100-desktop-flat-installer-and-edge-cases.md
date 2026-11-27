# Windows 桌面端用户边界情况、自研卸载器与扁平化安装/静默更新评估

日期：2026-11-27  
适用范围：`SimpleTavern-Desktop` Windows x64 桌面发行版（安装版与免安装版）

---

## 一、背景与核心产品诉求

SimpleTavern 坚持采用**纯 JSON 文件存储**而不是 SQLite，核心目的是让用户随时能够直接查看、复制、手动备份和迁移自己的聊天记录、角色卡与设置。

在实际测试与用户习惯分析中，发现了以下与当前 **Velopack 1.2.161** 默认打包架构之间的根本摩擦：

1. **用户的直觉路径是「去安装目录找 `data/` 就地备份」**：普通工具软件（尤其是本地 AI / 酒馆类工具）用户不像游戏玩家那样习惯去翻 `%LOCALAPPDATA%` 或 `Documents`；即便在服务管理器里放了「打开数据目录」按钮，仍有不少用户会下意识打开安装文件夹直接找文件。
2. **用户习惯装完就删 `Setup.exe`**：几周后若想改安装位置、换盘或卸载重装，在 Windows「设置 → 应用 → 已安装的应用」中「修改」按钮是灰色的，只能点「卸载」，且卸载时系统不会告知是否保留用户数据。
3. **Velopack 目录结构对普通用户不够直观**：安装目录包含 `current/`、`packages/`、`Update.exe`、`SimpleTavern.exe`（491KB 入口桩）以及 `current/sq.version`。由于 Velopack 卸载器（`Update.exe uninstall`）会**整目录删除安装根目录**，当前安装版不得不把真实数据隔离到 `%LOCALAPPDATA%\SimpleTavern.User\data`（见 `desktop/src/profile.rs`），并在 `desktop/src/setup.rs` 中禁止安装目录与数据目录重叠。

---

## 二、真实用户行为边界情况清单（不预设用户按开发者思路操作）

| # | 用户真实行为 | 当前架构下的实际后果 | 风险等级 |
| --- | --- | --- | --- |
| 1 | **装完就删 `Setup.exe`，之后想换盘或找 JSON 数据** | Windows 设置里「修改」不可用；点「卸载」无保留数据提示；安装目录内没有 `data/`，用户找不到数据也不敢点卸载。 | 高 |
| 2 | **在 WinRAR / Bandizip / 资源管理器 ZIP 预览窗口里直接双击免安装版 `SimpleTavern.exe`（未解压）** | 压缩软件仅将部分文件临时解到 `%TEMP%` 运行。用户可能使用多日后被系统自动清理临时目录导致**数据丢失**，或因缺 `current/` 启动失败。 | 极高（丢数据） |
| 3 | **用户手动把旧 `data/` 文件夹复制进安装目录的 `current/data/`** | 软件实际读取 `%LOCALAPPDATA%\SimpleTavern.User\data` 或根目录 `data/`，完全读不到 `current/data/`；更严重的是，**下次 Velopack 自动更新原子替换 `current/` 时会直接删掉 `current/data/`**。 | 极高（丢数据） |
| 4 | **用户直接 `Ctrl+X` / `Ctrl+V` 把安装版整个目录剪切到别的盘** | 桌面/开始菜单快捷方式失效，注册表 `InstallLocation` 仍指向旧路径，后续重装或卸载异常（免安装版则支持退出后整目录移动）。 | 中 |
| 5 | **把免安装版解压到「桌面」或「文档」（被 Windows 11 OneDrive 接管同步）** | 频繁写入 JSON 易与 OneDrive 同步锁冲突导致偶发写入失败，且含明文 API Key 的 `settings.json` 会被自动同步至云端。 | 中 |
| 6 | **已开着源码版（`deploy.bat` 占 9081/9091）再启动桌面版** | 管理器报端口无法绑定，但未直接提醒“可能已有另一份 SimpleTavern（如源码版）正在运行”。 | 中 |
| 7 | **不点托盘「退出服务」直接关机或强杀进程** | `TavernService.exe` 由 Windows Job Object（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）托管会一并退出；JSON 使用文件锁与原子写不会撕裂，仅流式未完结的半截回复可能未落盘。 | 低（已兜底） |
| 8 | **误删 `Update.exe`、`packages/` 或 `current/sq.version`** | `updates::manager()` 失败后自动回退到编译期版本号，聊天服务仍可正常启动，仅检查更新失败，不丢数据。 | 低（已兜底） |

### v1.0.x 阶段可选的轻量化兜底（不换 Velopack）

以下 4 项均在 `desktop/src/` 与 `desktop/ui/` 内可小成本完成（约 0.5–1 天）：

1. **服务管理器与托盘菜单增加「打开数据目录」「打开扩展目录」**，并在安装版界面明确标注「卸载或重装软件不会删除用户数据」。
2. **免安装版 `%TEMP%` 运行拦截/警告**：检测到运行目录位于系统临时目录（如 `AppData\Local\Temp`）时，顶部高亮告警并阻止在临时目录新建正式数据。
3. **`current/data/` 误放预警**：启动时检查 `current/data/` 是否存在 `settings.json` 或 `characters/`，若有则立即提醒用户移走，避免更新时被清除。
4. **端口冲突提示更直白**：提示可能已有源码版或另一份 SimpleTavern 正在后台运行，再引导更换端口。

---

## 三、现状代码资产盘点（供后续架构改造参考）

当前 Windows 桌面端实现高度集中，边界清晰：

- `desktop/src/main.rs`：Tauri 2 托盘、单实例、窗口外观联动（~334 行）
- `desktop/src/manager.rs`：服务生命周期、端口管理、优雅排空（drain）与更新状态机（~483 行）
- `desktop/src/profile.rs`：区分 `.portable` 与 `%LOCALAPPDATA%\SimpleTavern.User` 及旧版 `data/` 导入（~134 行）
- `desktop/src/service.rs`：通过 Job Object + stdin/stdout JSON 管道托管 `TavernService.exe`（~90 行）
- `desktop/src/updates.rs`：**唯一直接依赖 `velopack::UpdateManager` 的文件**（~48 行）
- `desktop/src/setup.rs`：自研 Rust 安装引导壳，负责目录校验、盘符保护、非空拦截、更改目录迁移（~490 行）
- `desktop/build_windows.py`：PyInstaller 冻结后端 + UPX/XZ 压缩 + `vpk pack` + 包装 `SimpleTavernSetup.exe`（~238 行）
- `.github/workflows/windows-desktop.yml`：GitHub Actions 自动打包与挂载 Release Assets（~59 行）
- `tools/desktop-check/packages.py`：真实安装/免安装 + 升级 + 保留草稿端到端验收脚本（~337 行）

---

## 四、方案评估 A：在现有体系或新安装器中设计「自研卸载器」

### 目标
- 解决“卸载会不会删光用户数据”的焦虑，支持把 `data/` 放在安装目录中且**卸载时默认保留 `data/`**（可勾选是否一并删除用户数据）。
- 支持用户在删掉 `Setup.exe` 后，也能从 Windows「设置 → 应用」直接点「修改」（换盘/迁移安装目录）或「卸载」。

### 需要完成的工作拆解

1. **卸载程序本体（Rust 独立轻量二进制，如 `Uninstall.exe` 或 `SimpleTavern.exe --uninstall`）**
   - 检查并优雅停止正在运行的 `SimpleTavern.exe` / `TavernService.exe`（等待排空或提示用户先关闭，避免文件锁死）。
   - 弹窗向用户明确展示：**「仅卸载程序（保留 `data/` 聊天记录与角色卡）」**（默认）与 **「同时删除用户数据」**（需二次确认）。
   - **白名单删除程序文件**：只删除已知程序清单（如 `app/`、`SimpleTavern.exe`、`Uninstall.exe`、`LICENSE`、`NOTICE` 等），**绝不对安装根目录执行无脑 `remove_dir_all`**（彻底杜绝误删用户自己放进目录的备份或 `data/`）。
   - 仅当安装目录已完全为空时才删除目录本身；若保留了 `data/`，明确提示保留路径。
   - **Windows 自删除技巧**：卸载程序自身无法在运行中删除自己的 `.exe`，标准做法是把自身复制到 `%TEMP%` 后带 `--cleanup <原路径>` 启动子进程，主进程退出后由子进程删掉原 `Uninstall.exe`（或在 Windows 重启时通过 `MoveFileExW(..., MOVEFILE_DELAY_UNTIL_REBOOT)` 清理）。
   - 清理桌面快捷方式、开始菜单快捷方式以及 `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\SimpleTavern` 注册表项。
2. **「修改 / 迁盘」入口（解决删掉 `Setup.exe` 后无法改目录）**
   - 注册表写入 `ModifyPath`（不再设 `NoModify = 1`），指向安装目录内的维护工具（例如 `Uninstall.exe --modify`）。
   - 支持选择新的空目标文件夹 → 停止服务 → 移动程序文件（以及可选一并移动 `data/`）→ 重建快捷方式与注册表 `InstallLocation` / `UninstallString` / `ModifyPath`。
3. **测试与边界校验**
   - 覆盖运行中卸载、文件被资源管理器/编辑器占用时的重试提示、保留 `data/` 后原路径重新安装自动接管、权限不足目录回滚。

### 工作量估算
- **仅自研卸载器 + ModifyPath 迁盘（不含自研静默更新）**：约 **2–4 天**（含 Rust 实现、快捷方式 COM/PowerShell 处理、边界单测与虚拟机实测）。
- **注意**：如果仍保留 Velopack，Velopack 每次自动更新都会重新覆盖注册表的 `UninstallString` 并重新写入 `Update.exe`，**自研卸载器与 Velopack 并存会频繁打架**；因此自研卸载器通常应与下方「扁平安装器 + 自研静默更新」一起整体替换 Velopack。

---

## 五、方案评估 B：彻底替换 Velopack → 扁平目录安装器 + 自研静默更新

### 目标目录结构（安装版与免安装版完全一致！）

```text
D:\SimpleTavern\
├── SimpleTavern.exe        # 唯一带图标的启动程序（用户双击即用）
├── data\                   # 用户的全部 JSON 数据（聊天、角色、世界书、设置、头像）
│   ├── settings.json
│   ├── characters\
│   └── chats\
├── app\                    # 程序内部运行文件（更新时只替换此目录与 SimpleTavern.exe）
│   ├── service\            # PyInstaller 冻结后的 TavernService.exe 及依赖
│   ├── web\                # 前端静态构建产物
│   ├── extensions\         # Janitor Bridge 浏览器扩展
│   ├── updater.exe         # 无应用图标的轻量更新/卸载辅助程序
│   ├── version.json        # 版本与文件清单
│   ├── LICENSE
│   └── NOTICE
└── manager.json            # 管理器端口等轻量配置
```

> **核心优势**：
> - 安装版与免安装版目录结构 100% 统一；
> - 根目录干干净净只有 `SimpleTavern.exe`、`data/`、`app/`、`manager.json`；
> - 用户点进安装目录一眼就看到 `data/`，可直接就地复制备份；
> - 无 `current/`、`packages/`、`Update.exe`、`sq.version` 等 Velopack 概念。

### 需要完成的工作拆解

#### 1. 安装器与目录权限策略（约 2–3 天）
- 复用现有 `desktop/src/setup.rs` 的大部分路径安全校验（盘符自动补子目录、禁止软链接、禁止非空目录覆写），**移除 `VelopackSetup.exe` 嵌套**，改为直接内嵌压缩包（如 `zip` / `7z` / `tar.zst`）并解压到目标目录。
- **权限关键点**：因为 `data/` 放在安装目录内，安装器必须强制要求目标目录**当前普通用户可写**（禁止装到只读的 `C:\Program Files`，或明确拒绝并引导选 `D:\SimpleTavern` / `%LOCALAPPDATA%\SimpleTavern`），现有 `setup.rs` 的写入探测已经能拦住只读目录。
- 创建桌面与开始菜单快捷方式（Windows `IShellLinkW` COM 接口，Rust `windows-sys` / `windows` crate 可直接调用，无外部依赖），写入标准 `HKCU\...\Uninstall\SimpleTavern` 注册表项（含 `DisplayIcon`、`InstallLocation`、`UninstallString`、`ModifyPath`、`EstimatedSize`）。
- 已有安装检测：若旧目录存在且用户选择重装/覆盖，保留原 `data/` 与 `manager.json`，仅替换 `SimpleTavern.exe` 与 `app/`。

#### 2. 自研卸载器与修改/迁盘器（约 2–3 天）
- 如第四节所述：支持 Windows 设置里的「卸载」和「修改」（换盘迁移），默认保留 `data/`，用户显式勾选才删除数据；只按程序清单清理 `SimpleTavern.exe`、`app/`、`app.old/`、快捷方式与注册表。

#### 3. 自研后台静默更新器（替代 Velopack，约 3–5 天）
这是最核心、最需要严谨处理异常与回滚的部分（替代现有 48 行的 `desktop/src/updates.rs`）：
- **发布清单设计**：CI 构建时生成 `manifest-win-x64.json`（包含 `version`、`url`、`sha256`、`size`、`releaseNotes`），与 `SimpleTavern-win-x64-App.zip`（或 `.tar.zst`）、`Setup.exe`、`Portable.zip` 一并挂到 GitHub Release。
  - *差分 vs 全量取舍*：当前整个应用包仅约 **29 MB**（比普通 Electron 应用小得多），**强烈建议第一版先做全量包下载 + SHA-256 校验**，省去二进制差分（bsdiff/zstd patch）的大量复杂度和损坏风险。
- **后台下载与预解包（Staging）**：
  - `SimpleTavern.exe` 后台请求 GitHub Releases 的 `manifest-win-x64.json`，对比 SemVer 版本；
  - 下载新包到 `<installDir>\.update_staging\`，严格校验 SHA-256，提前解压到 `.update_staging\new\`（保证校验不通过或磁盘空间不足时，现有运行环境零影响）。
- **退出后安全替换（原子切换 + 失败回滚）**：
  - 复用现有 `manager.rs` 的排空机制（`drain` 等待当前生成与 JSON 写入完成 → 优雅关闭 `TavernService.exe`）；
  - 将 `app\updater.exe` 复制到 `%TEMP%` 启动，传入主进程 PID、安装根目录、`.update_staging\new\`、是否 `--resume`；
  - `updater.exe` 等待主进程与 `TavernService.exe` 完全退出（释放文件句柄，带超时重试）；
  - **两阶段重命名替换（绝不触碰 `data/` 与 `manager.json`）**：
    1. `SimpleTavern.exe` → `SimpleTavern.exe.old`，`app\` → `app.old\`；
    2. `.update_staging\new\SimpleTavern.exe` → `SimpleTavern.exe`，`.update_staging\new\app\` → `app\`；
    3. 若第 2 步任意步骤失败（例如被杀软或资源管理器锁文件），立刻把 `.old` 重命名回原位完成**自动回滚**；
    4. 成功后拉起新版 `SimpleTavern.exe --resume`，清理 `.old` 与 `.update_staging\`。
- **旧版迁移兼容**：若 v1.0.0 已用 Velopack 发布，后续 v1.1.0 切到自研扁平结构时，需要提供平滑过渡路径（例如 v1.0.0 → v1.0.1 仍走 Velopack，或 v1.1.0 安装器自动识别旧 Velopack 安装并把 `%LOCALAPPDATA%\SimpleTavern.User\data` 复制/迁入新目录的 `data/`）。

#### 4. CI 构建、打包与端到端回归改造（约 1–2 天）
- 改造 `desktop/build_windows.py` 与 `.github/workflows/windows-desktop.yml`：移除 `dotnet` / `vpk` 依赖（CI 构建速度反而会更快、环境更轻！），输出 `Setup.exe`、`Portable.zip`、`App.zip`、`manifest-win-x64.json`。
- 改造 `tools/desktop-check/packages.py`：用本地文件更新源验证完整安装、覆盖升级、退出时更新、下载失败/校验失败恢复、模拟锁文件回滚、修改迁盘与卸载保留 `data/`。

#### 5. 杀毒软件与 SmartScreen 重新实测（约 0.5–1 天，**非常关键**）
- 自研 `Setup.exe`（内嵌压缩包释放 exe + 写注册表 + 建快捷方式）以及 `updater.exe`（复制到 `%TEMP%` 后等进程退出并替换目标目录 `.exe`）的行为特征，**高度接近杀毒软件重点监控的敏感模式**。
- 必须在 Win11 虚拟机上重新过一遍 Windows Defender、SmartScreen、360、火绒、腾讯电脑管家；如果某款杀软误报，需要逐一排查是 UPX、自解压释放还是 `%TEMP%` 替换逻辑触发的。

---

## 六、总工作量与发布节奏建议

| 方案 | 预计工作量 | 风险与代价 | 建议落地时机 |
| --- | --- | --- | --- |
| **v1.0.0 保持 Velopack**（当前已移除 `Update.exe` 图标 + `Setup.exe` 支持改目录与保留数据提示） | 已完成 | 安装版 `data/` 在 `%LOCALAPPDATA%`；目录仍有 `current/`、`packages/` | **立即用于 v1.0.0 正式发布**（已通过 4 家杀软零误报实测） |
| **v1.0.x 轻量化兜底**（管理器加打开数据/扩展目录、`%TEMP%` 拦截、`current/data` 误放告警） | **0.5–1 天** | 零架构风险，不影响杀软结果 | 可视情况进 v1.0.0 或 v1.0.1 |
| **v1.1.0 扁平目录 + 自研安装/卸载/静默更新** | **约 8–13 天**（含测试与杀软复测） | 需重写更新状态机、安装/卸载器与回归脚本，且必须重新做杀软误报验证 | **v1.1.0 专题迭代**（同时做好从 v1.0.0 `%LOCALAPPDATA%` 自动迁移 `data/`） |
