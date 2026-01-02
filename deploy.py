#!/usr/bin/env python3
"""
SimpleTavern 一键部署脚本
支持 Windows 和 Linux 系统
"""

import os
import sys
import subprocess
import platform
import time
import webbrowser
from pathlib import Path

# 颜色输出（可选）
class Colors:
    GREEN = '\033[92m' if platform.system() != 'Windows' else ''
    YELLOW = '\033[93m' if platform.system() != 'Windows' else ''
    RED = '\033[91m' if platform.system() != 'Windows' else ''
    BLUE = '\033[94m' if platform.system() != 'Windows' else ''
    RESET = '\033[0m' if platform.system() != 'Windows' else ''

def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {msg}")

def print_error(msg):
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")

def check_command(cmd, name):
    """检查命令是否可用"""
    try:
        subprocess.run([cmd, '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error(f"{name} 未安装或不在 PATH 中")
        return False

def run_command(cmd, cwd=None, check=True, shell=False):
    """运行命令"""
    if platform.system() == 'Windows':
        shell = True
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            shell=shell,
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_error(f"命令执行失败: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        return False
    except Exception as e:
        print_error(f"执行命令时出错: {e}")
        return False

def main():
    print_info("SimpleTavern 一键部署脚本")
    print_info(f"操作系统: {platform.system()} {platform.release()}")
    print()
    
    # 获取项目根目录
    root_dir = Path(__file__).parent.resolve()
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"
    
    # 检查必要的命令
    print_info("检查环境依赖...")
    python_cmd = None
    if check_command("python3", "Python3"):
        python_cmd = "python3"
    elif check_command("python", "Python"):
        python_cmd = "python"
    else:
        print_error("请先安装 Python 3.7+")
        sys.exit(1)
    
    if not check_command("npm", "Node.js/npm"):
        print_error("请先安装 Node.js 和 npm")
        sys.exit(1)
    
    print_success("环境检查通过")
    print()
    
    # 安装后端依赖
    print_info("安装后端依赖...")
    requirements_file = backend_dir / "requirements.txt"
    if not requirements_file.exists():
        print_error(f"找不到 requirements.txt: {requirements_file}")
        sys.exit(1)
    
    if not run_command([python_cmd, "-m", "pip", "install", "-r", str(requirements_file)], cwd=backend_dir):
        print_error("后端依赖安装失败")
        sys.exit(1)
    
    print_success("后端依赖安装完成")
    print()
    
    # 安装前端依赖
    print_info("安装前端依赖...")
    if not (frontend_dir / "package.json").exists():
        print_error(f"找不到 package.json: {frontend_dir / 'package.json'}")
        sys.exit(1)
    
    if not run_command(["npm", "install"], cwd=frontend_dir):
        print_error("前端依赖安装失败")
        sys.exit(1)
    
    print_success("前端依赖安装完成")
    print()
    
    # 构建前端
    print_info("构建前端...")
    if not run_command(["npm", "run", "build"], cwd=frontend_dir):
        print_error("前端构建失败")
        sys.exit(1)
    
    print_success("前端构建完成")
    print()
    
    # 启动后端
    print_info("启动后端服务...")
    backend_port = 8000
    backend_url = f"http://localhost:{backend_port}"
    
    # 使用 uvicorn 启动后端
    backend_cmd = [python_cmd, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(backend_port)]
    if platform.system() == 'Windows':
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0
        )
    else:
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    # 等待后端启动
    print_info("等待后端服务启动...")
    time.sleep(3)
    
    # 检查后端是否启动成功
    try:
        import urllib.request
        urllib.request.urlopen(f"{backend_url}/api/health", timeout=2)
        print_success(f"后端服务已启动: {backend_url}")
    except Exception as e:
        print_warning(f"后端服务可能未完全启动: {e}")
        print_info("继续启动前端...")
    
    print()
    
    # 启动前端预览服务器
    print_info("启动前端服务...")
    frontend_port = 4173  # vite preview 默认端口
    frontend_url = f"http://localhost:{frontend_port}"
    
    frontend_cmd = ["npm", "run", "preview", "--", "--port", str(frontend_port), "--host"]
    if platform.system() == 'Windows':
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0
        )
    else:
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    # 等待前端启动
    print_info("等待前端服务启动...")
    time.sleep(3)
    
    print_success(f"前端服务已启动: {frontend_url}")
    print()
    
    # 自动打开浏览器
    print_info("正在打开浏览器...")
    try:
        webbrowser.open(frontend_url)
        print_success(f"已打开浏览器: {frontend_url}")
    except Exception as e:
        print_warning(f"无法自动打开浏览器: {e}")
        print_info(f"请手动访问: {frontend_url}")
    
    print()
    print_success("部署完成！")
    print_info("后端地址: " + backend_url)
    print_info("前端地址: " + frontend_url)
    print()
    print_warning("按 Ctrl+C 停止服务")
    print()
    
    # 等待用户中断
    try:
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print()
        print_info("正在停止服务...")
        backend_process.terminate()
        frontend_process.terminate()
        time.sleep(1)
        if backend_process.poll() is None:
            backend_process.kill()
        if frontend_process.poll() is None:
            frontend_process.kill()
        print_success("服务已停止")

if __name__ == "__main__":
    main()

