@echo off
REM SimpleTavern 一键部署脚本 (Windows)

echo [INFO] SimpleTavern 一键部署脚本
echo [INFO] 操作系统: %OS%
echo.

REM 获取项目根目录
set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

REM 检查 Python
echo [INFO] 检查环境依赖...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未安装或不在 PATH 中
    exit /b 1
)

REM 检查 Node.js/npm
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js/npm 未安装或不在 PATH 中
    exit /b 1
)

echo [SUCCESS] 环境检查通过
echo.

REM 安装后端依赖
echo [INFO] 安装后端依赖...
cd /d "%BACKEND_DIR%"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败
    exit /b 1
)
echo [SUCCESS] 后端依赖安装完成
echo.

REM 安装前端依赖
echo [INFO] 安装前端依赖...
cd /d "%FRONTEND_DIR%"
call npm install
if errorlevel 1 (
    echo [ERROR] 前端依赖安装失败
    exit /b 1
)
echo [SUCCESS] 前端依赖安装完成
echo.

REM 构建前端
echo [INFO] 构建前端...
call npm run build
if errorlevel 1 (
    echo [ERROR] 前端构建失败
    exit /b 1
)
echo [SUCCESS] 前端构建完成
echo.

REM 启动后端
echo [INFO] 启动后端服务...
cd /d "%BACKEND_DIR%"
start "SimpleTavern Backend" cmd /c "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
echo [SUCCESS] 后端服务已启动: http://localhost:8000
echo.

REM 启动前端
echo [INFO] 启动前端服务...
cd /d "%FRONTEND_DIR%"
start "SimpleTavern Frontend" cmd /c "npm run preview -- --port 4173 --host"
timeout /t 3 /nobreak >nul
echo [SUCCESS] 前端服务已启动: http://localhost:4173
echo.

REM 打开浏览器
echo [INFO] 正在打开浏览器...
start http://localhost:4173
echo.

echo [SUCCESS] 部署完成！
echo [INFO] 后端地址: http://localhost:8000
echo [INFO] 前端地址: http://localhost:4173
echo.
echo [WARNING] 按任意键退出（服务将继续在后台运行）
pause >nul

