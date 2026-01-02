#!/bin/bash
# SimpleTavern 一键部署脚本 (Linux/macOS)

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
print_info "SimpleTavern 一键部署脚本"
print_info "操作系统: $(uname -s) $(uname -r)"
echo ""

# 获取项目根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$ROOT_DIR/venv"

# ========================================
# 检查 Python
# ========================================
print_info "检查环境依赖..."

PYTHON_CMD=""

# 检查 python3
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    print_success "找到 Python: python3 ($PYTHON_VERSION)"
    PYTHON_CMD="python3"
# 检查 python
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1)
    # 确保是 Python 3
    if [[ "$PYTHON_VERSION" == *"Python 3"* ]]; then
        print_success "找到 Python: python ($PYTHON_VERSION)"
        PYTHON_CMD="python"
    else
        print_error "找到的 Python 不是 3.x 版本: $PYTHON_VERSION"
        print_error "请安装 Python 3.7+"
        exit 1
    fi
else
    print_error "Python 未安装"
    print_error "请先安装 Python 3.7+"
    exit 1
fi

# ========================================
# 检查 Node.js/npm
# ========================================
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version 2>&1)
    print_success "找到 npm: v$NPM_VERSION"
else
    print_error "Node.js/npm 未安装"
    print_error "请先安装 Node.js 和 npm"
    exit 1
fi

print_success "环境检查通过"
echo ""

# ========================================
# 创建/使用虚拟环境
# ========================================
print_info "设置 Python 虚拟环境..."

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ -d "$VENV_DIR" ] && [ -f "$VENV_PYTHON" ]; then
    print_info "使用已存在的虚拟环境: $VENV_DIR"
else
    print_info "创建虚拟环境: $VENV_DIR"
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        print_error "创建虚拟环境失败"
        exit 1
    fi
fi

if [ ! -f "$VENV_PYTHON" ]; then
    print_error "虚拟环境 Python 不存在: $VENV_PYTHON"
    exit 1
fi

print_success "虚拟环境 Python: $VENV_PYTHON"
echo ""

# ========================================
# 安装后端依赖
# ========================================
print_info "安装后端依赖..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    print_error "后端依赖安装失败"
    exit 1
fi
print_success "后端依赖安装完成"
echo ""

# ========================================
# 安装前端依赖
# ========================================
print_info "安装前端依赖..."
cd "$FRONTEND_DIR"
npm install
if [ $? -ne 0 ]; then
    print_error "前端依赖安装失败"
    exit 1
fi
print_success "前端依赖安装完成"
echo ""

# ========================================
# 构建前端
# ========================================
print_info "构建前端..."
npm run build
if [ $? -ne 0 ]; then
    print_error "前端构建失败"
    exit 1
fi
print_success "前端构建完成"
echo ""

# ========================================
# 启动后端
# ========================================
print_info "启动后端服务..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3
print_success "后端服务已启动: http://localhost:8000"
echo ""

# ========================================
# 启动前端
# ========================================
print_info "启动前端服务..."
cd "$FRONTEND_DIR"
npm run preview -- --port 4173 --host &
FRONTEND_PID=$!
sleep 3
print_success "前端服务已启动: http://localhost:4173"
echo ""

# ========================================
# 打开浏览器
# ========================================
print_info "正在打开浏览器..."
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:4173
elif command -v open &> /dev/null; then
    open http://localhost:4173
else
    print_warning "无法自动打开浏览器，请手动访问: http://localhost:4173"
fi
echo ""

echo "=================================================="
print_success "部署完成！"
echo "=================================================="
print_info "后端地址: http://localhost:8000"
print_info "前端地址: http://localhost:4173"
print_info "虚拟环境: $VENV_DIR"
echo ""
print_warning "按 Ctrl+C 停止服务"
echo ""

# 等待用户中断
trap "echo ''; print_info '正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; print_success '服务已停止'; exit" INT TERM
wait
