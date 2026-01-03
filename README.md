# SimpleTavern（本地单用户 AI 角色扮演）

前端：Vue 3（Vite + TS）  
后端：FastAPI（SSE 流式）  
存储：本地 `data/` 下按文件拆分的 JSON（无数据库）

## 环境要求

- **Python 3.7+** 和 pip
- **Node.js 16+** 和 npm
- **Git**（用于克隆仓库，或直接从 releases 下载）

## 快速开始

### 方法一：从 GitHub Releases 下载（推荐）

1. **访问 Releases 页面**
   - 打开 [https://github.com/DuoHBshuijiao/SimpleTavern/releases](https://github.com/DuoHBshuijiao/SimpleTavern/releases)
   - 下载最新版本的源码压缩包（Source code (zip) 或 Source code (tar.gz)）

2. **解压并进入项目目录**

   **Windows (PowerShell):**
   ```powershell
   # 假设下载到 D:\Downloads，解压后进入目录
   cd D:\Downloads\SimpleTavern-0.15
   ```

   **Linux/macOS (Bash):**
   ```bash
   # 假设下载到 ~/Downloads，解压后进入目录
   cd ~/Downloads/SimpleTavern-0.15
   ```

3. **运行一键部署脚本**

   **Windows:**
   ```cmd
   python deploy.py
   ```

   **Linux/macOS:**
   ```bash
   python3 deploy.py
   ```
   或使用 shell 脚本：
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

### 方法二：安卓 Termux 命令行安装部署教程

> 重要：**请不要把项目放在 `/sdcard`（共享存储）里运行**。Termux 在共享存储下经常会遇到权限/挂载限制，导致 `python -m venv` 创建虚拟环境失败。  
> 推荐做法：用 `git clone` 把源码直接放到 Termux 的私有目录（`$HOME`）中。

1. **安装依赖（Termux）**

```bash
pkg update -y
pkg install -y python nodejs git unzip wget
```

2. **在 Termux 私有目录中克隆源码（推荐）**

```bash
cd ~
git clone https://github.com/DuoHBshuijiao/SimpleTavern.git
cd SimpleTavern
```

> 可选：如果你必须用 Releases 的 zip 包，也请**在 `$HOME` 下解压**（不要在 `/sdcard` 下解压/运行）。

3. **运行一键部署脚本**

```bash
python deploy.py
```

## 一键部署脚本说明

项目提供了跨平台的一键部署脚本，支持 Windows 和 Linux/macOS。

脚本会自动完成以下操作：
1. 检查 Python 和 Node.js 环境
2. **创建 Python 虚拟环境**（`venv/` 目录）
3. 在虚拟环境中安装后端依赖（pip install）
4. 安装前端依赖（npm install）
5. 构建前端项目（npm run build）
6. 启动后端服务（端口 8000）
7. 启动前端服务（端口 4173）
8. 自动打开浏览器访问应用

按 `Ctrl+C` 可停止所有服务。

### 部署脚本文件

- `deploy.py`：跨平台一键部署脚本（Python，**推荐使用**）
- `deploy.sh`：Linux/macOS 一键部署脚本

## 手动部署（分步操作）

如果一键部署脚本遇到问题，可以按照以下步骤手动部署：

### Windows (PowerShell)

#### 1) 创建虚拟环境并安装后端依赖

```powershell
# 进入项目根目录
cd E:\SimpleTavern

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 进入后端目录并安装依赖
cd backend
pip install -r requirements.txt
```

#### 2) 安装前端依赖

```powershell
# 返回项目根目录
cd ..

# 进入前端目录并安装依赖
cd frontend
npm install
```

#### 3) 构建前端

```powershell
# 仍在 frontend 目录
npm run build
```

#### 4) 启动后端服务

```powershell
# 返回项目根目录
cd ..

# 进入后端目录
cd backend

# 确保激活虚拟环境
..\venv\Scripts\Activate.ps1

# 启动后端（在新终端窗口）
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

#### 5) 启动前端服务

```powershell
# 打开新终端，进入前端目录
cd E:\SimpleTavern\frontend

# 启动预览服务器
npm run preview -- --port 4173 --host
```

#### 6) 访问应用

打开浏览器访问：`http://localhost:4173`

### Linux/macOS (Bash)

#### 1) 创建虚拟环境并安装后端依赖

```bash
# 进入项目根目录
cd ~/SimpleTavern

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 进入后端目录并安装依赖
cd backend
pip install -r requirements.txt
```

#### 2) 安装前端依赖

```bash
# 返回项目根目录
cd ..

# 进入前端目录并安装依赖
cd frontend
npm install
```

#### 3) 构建前端

```bash
# 仍在 frontend 目录
npm run build
```

#### 4) 启动后端服务

```bash
# 返回项目根目录
cd ..

# 进入后端目录
cd backend

# 确保激活虚拟环境
source ../venv/bin/activate

# 启动后端（在后台运行或新终端）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

#### 5) 启动前端服务

```bash
# 进入前端目录（新终端或后台）
cd ~/SimpleTavern/frontend

# 启动预览服务器
npm run preview -- --port 4173 --host &
```

#### 6) 访问应用

打开浏览器访问：`http://localhost:4173`

## 项目目录结构

- `frontend/`：Vue3 前端
- `backend/`：FastAPI 后端
- `data/`：本地 JSON 数据（settings/characters/chats）
- `venv/`：Python 虚拟环境（由部署脚本自动创建）
- `deploy.py`：跨平台一键部署脚本（Python）
- `deploy.sh`：Linux/macOS 一键部署脚本

## 配置模型（OpenAI 兼容）

在应用内"设置"里配置：
- **Base URL**：例如 `https://api.openai.com` 或你的兼容网关地址
- **API Key**：明文存储到 `data/settings.json`
- **Model**：例如 `gpt-4o-mini`（取决于你的服务端支持）

## 常见问题

### 端口被占用

如果 8000 或 4173 端口被占用，可以：

1. **修改后端端口**：在启动命令中修改 `--port` 参数
2. **修改前端端口**：在 `npm run preview` 命令中修改 `--port` 参数
3. **关闭占用端口的程序**

### Python 命令不存在

- Windows：尝试使用 `py` 或 `python3`
- Linux/macOS：确保已安装 Python 3，使用 `python3` 命令

### npm 命令不存在

确保已安装 Node.js，可以从 [nodejs.org](https://nodejs.org/) 下载安装。

### 虚拟环境激活问题

- Windows PowerShell：如果提示脚本执行策略问题，以管理员身份运行：
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- Windows CMD：使用 `venv\Scripts\activate.bat` 代替

## 许可证

本项目采用 MIT 许可证。
