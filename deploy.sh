#!/bin/bash
# SimpleTavern 一键部署脚本 (Linux/macOS)

set -e

echo "[INFO] SimpleTavern 一键部署脚本"
echo "[INFO] 操作系统: $(uname -s)"
echo ""

# 获取项目根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# 检查 Python
echo "[INFO] 检查环境依赖..."
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 未安装"
    exit 1
fi

# 检查 Node.js/npm
if ! command -v npm &> /dev/null; then
    echo "[ERROR] Node.js/npm 未安装"
    exit 1
fi

echo "[SUCCESS] 环境检查通过"
echo ""

# 安装后端依赖
echo "[INFO] 安装后端依赖..."
cd "$BACKEND_DIR"
python3 -m pip install -r requirements.txt
echo "[SUCCESS] 后端依赖安装完成"
echo ""

# 安装前端依赖
echo "[INFO] 安装前端依赖..."
cd "$FRONTEND_DIR"
npm install
echo "[SUCCESS] 前端依赖安装完成"
echo ""

# 构建前端
echo "[INFO] 构建前端..."
npm run build
echo "[SUCCESS] 前端构建完成"
echo ""

# 启动后端
echo "[INFO] 启动后端服务..."
cd "$BACKEND_DIR"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3
echo "[SUCCESS] 后端服务已启动: http://localhost:8000"
echo ""

# 启动前端
echo "[INFO] 启动前端服务..."
cd "$FRONTEND_DIR"
npm run preview -- --port 4173 --host &
FRONTEND_PID=$!
sleep 3
echo "[SUCCESS] 前端服务已启动: http://localhost:4173"
echo ""

# 打开浏览器
echo "[INFO] 正在打开浏览器..."
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:4173
elif command -v open &> /dev/null; then
    open http://localhost:4173
else
    echo "[WARNING] 无法自动打开浏览器，请手动访问: http://localhost:4173"
fi
echo ""

echo "[SUCCESS] 部署完成！"
echo "[INFO] 后端地址: http://localhost:8000"
echo "[INFO] 前端地址: http://localhost:4173"
echo ""
echo "[WARNING] 按 Ctrl+C 停止服务"
echo ""

# 等待用户中断
trap "echo ''; echo '[INFO] 正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

