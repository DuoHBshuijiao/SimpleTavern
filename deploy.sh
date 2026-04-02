#!/bin/bash
# SimpleTavern 一键部署脚本 (Linux/macOS)
# 自动检测部署状态，选择"安装模式"或"启动模式"

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

print_mode() {
    echo -e "${CYAN}[MODE]${NC} $1"
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
VENV_PYTHON="$VENV_DIR/bin/python"
# 与 deploy.py 一致：记录上次 pip install 对应的 requirements.txt 摘要
REQ_HASH_FILE="$VENV_DIR/.requirements-hash"

# ========================================
# 检查 Python
# ========================================
print_info "检查环境依赖..."

PYTHON_CMD=""

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    print_success "找到 Python: python3 ($PYTHON_VERSION)"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1)
    if [[ "$PYTHON_VERSION" == *"Python 3"* ]]; then
        print_success "找到 Python: python ($PYTHON_VERSION)"
        PYTHON_CMD="python"
    else
        print_error "找到的 Python 不是 3.x 版本: $PYTHON_VERSION"
        print_error "请安装 Python 3.10+"
        exit 1
    fi
else
    print_error "Python 未安装"
    print_error "请先安装 Python 3.10+"
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

# 与 deploy.py 一致：对 requirements.txt 的 SHA256（判断清单是否相对上次安装变更）
hash_requirements_file() {
    local f="$1"
    if command -v sha256sum &> /dev/null; then
        sha256sum "$f" | awk '{print $1}'
    elif command -v shasum &> /dev/null; then
        shasum -a 256 "$f" | awk '{print $1}'
    elif command -v openssl &> /dev/null; then
        openssl dgst -sha256 "$f" | awk '{print $2}'
    elif [ -n "$PYTHON_CMD" ]; then
        "$PYTHON_CMD" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$f"
    else
        echo ""
    fi
}

CURRENT_REQ_HASH=""
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    CURRENT_REQ_HASH=$(hash_requirements_file "$BACKEND_DIR/requirements.txt")
fi

# ========================================
# 检查部署状态
# ========================================
print_info "检查部署状态..."

VENV_EXISTS="✗"
BACKEND_DEPS_OK="✗"
NODE_MODULES_EXISTS="✗"
DIST_EXISTS="✗"

# 检查虚拟环境
if [ -d "$VENV_DIR" ] && [ -f "$VENV_PYTHON" ]; then
    VENV_EXISTS="✓"
fi

# 检查后端依赖（与 deploy.py：在 backend 目录下 import app.main + requirements 摘要一致）
if [ "$VENV_EXISTS" = "✓" ]; then
    if (cd "$BACKEND_DIR" && "$VENV_PYTHON" -c "import app.main; print('ok')" 2>/dev/null | grep -q "ok"); then
        if [ -n "$CURRENT_REQ_HASH" ] && [ -f "$REQ_HASH_FILE" ]; then
            SAVED_HASH=$(tr -d '\r\n' < "$REQ_HASH_FILE" 2>/dev/null || true)
            if [ "$SAVED_HASH" = "$CURRENT_REQ_HASH" ]; then
                BACKEND_DEPS_OK="✓"
            fi
        fi
    fi
fi

# 检查前端 node_modules
if [ -d "$FRONTEND_DIR/node_modules" ] && [ "$(ls -A $FRONTEND_DIR/node_modules 2>/dev/null)" ]; then
    NODE_MODULES_EXISTS="✓"
fi

# 检查前端 dist
if [ -d "$FRONTEND_DIR/dist" ] && [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    DIST_EXISTS="✓"
fi

print_info "  - 虚拟环境: $VENV_EXISTS"
print_info "  - 后端依赖: $BACKEND_DEPS_OK"
print_info "  - 前端依赖 (node_modules): $NODE_MODULES_EXISTS"
print_info "  - 前端构建 (dist): $DIST_EXISTS"
echo ""

# 判断是否需要安装
NEED_INSTALL=false
if [ "$VENV_EXISTS" != "✓" ] || [ "$BACKEND_DEPS_OK" != "✓" ] || [ "$NODE_MODULES_EXISTS" != "✓" ] || [ "$DIST_EXISTS" != "✓" ]; then
    NEED_INSTALL=true
fi

if [ "$NEED_INSTALL" = false ]; then
    # ========================================
    # 启动模式
    # ========================================
    print_mode "检测到已完成部署，进入【启动模式】"
    echo ""
else
    # ========================================
    # 安装模式
    # ========================================
    print_mode "检测到需要安装/构建，进入【安装模式】"
    echo ""
    
    # 创建/使用虚拟环境
    # 若 venv 目录存在但 Python 可执行文件不存在（如下载的源码含空/损坏的 venv），则删除并重建
    if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_PYTHON" ]; then
        print_warning "检测到无效的虚拟环境（Python 不存在），将删除并重新创建: $VENV_DIR"
        rm -rf "$VENV_DIR"
    fi
    
    if [ "$VENV_EXISTS" != "✓" ]; then
        print_info "创建虚拟环境: $VENV_DIR"
        $PYTHON_CMD -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            print_error "创建虚拟环境失败"
            exit 1
        fi
        print_success "虚拟环境已创建"
    else
        print_info "使用已存在的虚拟环境: $VENV_DIR"
    fi
    echo ""
    
    # 安装后端依赖
    if [ "$BACKEND_DEPS_OK" != "✓" ]; then
        print_info "安装后端依赖..."
        cd "$BACKEND_DIR"
        "$VENV_PYTHON" -m pip install -r requirements.txt
        if [ $? -ne 0 ]; then
            print_error "后端依赖安装失败"
            exit 1
        fi
        H=$(hash_requirements_file "$BACKEND_DIR/requirements.txt")
        if [ -n "$H" ]; then
            printf '%s\n' "$H" > "$REQ_HASH_FILE"
        else
            print_warning "无法写入 requirements 摘要（下次可能重复安装依赖）；请确保存在 sha256sum、openssl 或可用 Python"
        fi
        set +e
        "$VENV_PYTHON" -m pip check
        PC=$?
        set -e
        if [ $PC -ne 0 ]; then
            print_warning "pip check 报告依赖问题（应用仍可能可运行）"
        fi
        print_success "后端依赖安装完成"
    else
        print_info "后端依赖已安装，跳过"
    fi
    echo ""
    
    # 安装前端依赖
    if [ "$NODE_MODULES_EXISTS" != "✓" ]; then
        print_info "安装前端依赖..."
        cd "$FRONTEND_DIR"
        npm install
        if [ $? -ne 0 ]; then
            print_error "前端依赖安装失败"
            exit 1
        fi
        # 若 npm audit 报告漏洞或提示可执行 npm audit fix，则先修复再继续
        set +e
        AUDIT_COMBINED=$(npm audit 2>&1)
        AUDIT_RC=$?
        set -e
        NEED_FIX=0
        if [ $AUDIT_RC -ne 0 ]; then
            NEED_FIX=1
        else
            if echo "$AUDIT_COMBINED" | grep -qi 'npm audit fix' && echo "$AUDIT_COMBINED" | grep -qiE 'to address|to fix|vulnerabilit'; then
                NEED_FIX=1
            fi
        fi
        if [ $NEED_FIX -eq 1 ]; then
            print_info "检测到依赖安全提示，正在执行 npm audit fix..."
            set +e
            npm audit fix
            FIX_RC=$?
            set -e
            if [ $FIX_RC -eq 0 ]; then
                print_success "npm audit fix 已完成"
            else
                print_warning "npm audit fix 未完全成功，将继续后续步骤"
            fi
        fi
        print_success "前端依赖安装完成"
    else
        print_info "前端依赖已安装，跳过"
    fi
    echo ""
    
    # 构建前端
    if [ "$DIST_EXISTS" != "✓" ]; then
        print_info "构建前端..."
        cd "$FRONTEND_DIR"
        npm run build
        if [ $? -ne 0 ]; then
            print_error "前端构建失败"
            exit 1
        fi
        print_success "前端构建完成"
    else
        print_info "前端已构建，跳过"
    fi
    echo ""
fi

# ========================================
# 启动服务
# ========================================
print_info "启动后端服务..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 9091 &
BACKEND_PID=$!
sleep 3
print_success "后端服务已启动: http://localhost:9091"
echo ""

print_info "启动前端服务..."
cd "$FRONTEND_DIR"
npm run preview -- --port 9081 --host &
FRONTEND_PID=$!
sleep 3
print_success "前端服务已启动: http://localhost:9081"
echo ""

# ========================================
# 打开浏览器
# ========================================
print_info "正在打开浏览器..."
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:9081
elif command -v open &> /dev/null; then
    open http://localhost:9081
else
    print_warning "无法自动打开浏览器，请手动访问: http://localhost:9081"
fi
echo ""

echo "=================================================="
print_success "服务已启动！"
echo "=================================================="
print_info "后端地址: http://localhost:9091"
print_info "前端地址: http://localhost:9081"
print_info "虚拟环境: $VENV_DIR"
echo ""
print_warning "按 Ctrl+C 停止服务"
echo ""

# 等待用户中断
trap "echo ''; print_info '正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; print_success '服务已停止'; exit" INT TERM
wait
