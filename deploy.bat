@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM SimpleTavern 一键部署脚本 (Windows)

echo [INFO] SimpleTavern 一键部署脚本
echo [INFO] 操作系统: Windows
echo.

REM 获取项目根目录
set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "VENV_DIR=%ROOT_DIR%venv"

REM ========================================
REM 检查 Python
REM ========================================
echo [INFO] 检查环境依赖...

set "PYTHON_CMD="

REM 方法1: 检查 python 命令
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo [SUCCESS] 找到 Python: !PYTHON_VERSION!
    set "PYTHON_CMD=python"
    goto :python_found
)

REM 方法2: 检查 py 启动器
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('py --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo [SUCCESS] 找到 Python: !PYTHON_VERSION!
    set "PYTHON_CMD=py"
    goto :python_found
)

REM 方法3: 检查常见安装路径
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist %%p (
        for /f "tokens=*" %%i in ('%%p --version 2^>^&1') do set "PYTHON_VERSION=%%i"
        echo [SUCCESS] 找到 Python: %%p ^(!PYTHON_VERSION!^)
        set "PYTHON_CMD=%%p"
        goto :python_found
    )
)

echo [ERROR] Python 未安装或不在 PATH 中
echo [ERROR] 请先安装 Python 3.7+ 并确保添加到 PATH
echo.
pause
exit /b 1

:python_found

REM ========================================
REM 检查 Node.js/npm
REM ========================================
set "NPM_CMD="

where npm >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('npm --version 2^>^&1') do set "NPM_VERSION=%%i"
    echo [SUCCESS] 找到 npm: v!NPM_VERSION!
    set "NPM_CMD=npm"
    goto :npm_found
)

REM 检查常见安装路径
for %%p in (
    "%PROGRAMFILES%\nodejs\npm.cmd"
    "%PROGRAMFILES(x86)%\nodejs\npm.cmd"
    "%APPDATA%\npm\npm.cmd"
) do (
    if exist %%p (
        for /f "tokens=*" %%i in ('%%p --version 2^>^&1') do set "NPM_VERSION=%%i"
        echo [SUCCESS] 找到 npm: %%p ^(v!NPM_VERSION!^)
        set "NPM_CMD=%%p"
        goto :npm_found
    )
)

echo [ERROR] Node.js/npm 未安装或不在 PATH 中
echo [ERROR] 请先安装 Node.js 和 npm
echo.
pause
exit /b 1

:npm_found

echo [SUCCESS] 环境检查通过
echo.

REM ========================================
REM 创建/使用虚拟环境
REM ========================================
echo [INFO] 设置 Python 虚拟环境...

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] 使用已存在的虚拟环境: %VENV_DIR%
) else (
    echo [INFO] 创建虚拟环境: %VENV_DIR%
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        echo.
        pause
        exit /b 1
    )
)

if not exist "%VENV_PYTHON%" (
    echo [ERROR] 虚拟环境 Python 不存在: %VENV_PYTHON%
    echo.
    pause
    exit /b 1
)

echo [SUCCESS] 虚拟环境 Python: %VENV_PYTHON%
echo.

REM ========================================
REM 安装后端依赖
REM ========================================
echo [INFO] 安装后端依赖...
cd /d "%BACKEND_DIR%"
"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败
    echo.
    pause
    exit /b 1
)
echo [SUCCESS] 后端依赖安装完成
echo.

REM ========================================
REM 安装前端依赖
REM ========================================
echo [INFO] 安装前端依赖...
cd /d "%FRONTEND_DIR%"
call %NPM_CMD% install
if errorlevel 1 (
    echo [ERROR] 前端依赖安装失败
    echo.
    pause
    exit /b 1
)
echo [SUCCESS] 前端依赖安装完成
echo.

REM ========================================
REM 构建前端
REM ========================================
echo [INFO] 构建前端...
call %NPM_CMD% run build
if errorlevel 1 (
    echo [ERROR] 前端构建失败
    echo.
    pause
    exit /b 1
)
echo [SUCCESS] 前端构建完成
echo.

REM ========================================
REM 启动后端
REM ========================================
echo [INFO] 启动后端服务...
cd /d "%BACKEND_DIR%"
start "SimpleTavern Backend" cmd /k ""%VENV_PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
echo [SUCCESS] 后端服务已启动: http://localhost:8000
echo.

REM ========================================
REM 启动前端
REM ========================================
echo [INFO] 启动前端服务...
cd /d "%FRONTEND_DIR%"
start "SimpleTavern Frontend" cmd /k "%NPM_CMD% run preview -- --port 4173 --host"
timeout /t 3 /nobreak >nul
echo [SUCCESS] 前端服务已启动: http://localhost:4173
echo.

REM ========================================
REM 打开浏览器
REM ========================================
echo [INFO] 正在打开浏览器...
start http://localhost:4173
echo.

echo ==================================================
echo [SUCCESS] 部署完成！
echo ==================================================
echo [INFO] 后端地址: http://localhost:8000
echo [INFO] 前端地址: http://localhost:4173
echo [INFO] 虚拟环境: %VENV_DIR%
echo.
echo [INFO] 后台服务窗口将保持运行
echo [INFO] 关闭此窗口不会停止服务
echo [WARNING] 要停止服务，请关闭 "SimpleTavern Backend" 和 "SimpleTavern Frontend" 窗口
echo.
echo 按任意键退出此窗口...
pause >nul
