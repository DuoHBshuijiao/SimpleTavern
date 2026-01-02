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
import shutil
from pathlib import Path

# 颜色输出
class Colors:
    if platform.system() == 'Windows':
        # Windows 启用 ANSI 颜色支持
        os.system('')
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {msg}")

def print_error(msg):
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")

def find_python():
    """查找 Python 可执行文件"""
    # 首先检查当前运行的 Python
    current_python = sys.executable
    if current_python:
        try:
            result = subprocess.run([current_python, '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                print_success(f"找到 Python: {current_python} ({version})")
                return current_python
        except Exception:
            pass
    
    # 尝试其他常见名称
    candidates = ['python', 'python3', 'py']
    for cmd in candidates:
        path = shutil.which(cmd)
        if path:
            try:
                result = subprocess.run([path, '--version'], capture_output=True, text=True)
                if result.returncode == 0:
                    version = result.stdout.strip() or result.stderr.strip()
                    print_success(f"找到 Python: {path} ({version})")
                    return path
            except Exception:
                continue
    
    return None

def find_npm():
    """查找 npm 可执行文件"""
    npm_path = shutil.which('npm')
    if npm_path:
        try:
            result = subprocess.run([npm_path, '--version'], capture_output=True, text=True, shell=(platform.system() == 'Windows'))
            if result.returncode == 0:
                version = result.stdout.strip()
                print_success(f"找到 npm: {npm_path} (v{version})")
                return npm_path
        except Exception:
            pass
    
    # Windows 上尝试直接调用
    if platform.system() == 'Windows':
        try:
            result = subprocess.run(['npm', '--version'], capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                print_success(f"找到 npm: npm (v{version})")
                return 'npm'
        except Exception:
            pass
    
    return None

def run_command(cmd, cwd=None, check=True, env=None):
    """运行命令"""
    shell = platform.system() == 'Windows'
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            shell=shell,
            env=env,
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_error(f"命令执行失败: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        return False
    except Exception as e:
        print_error(f"执行命令时出错: {e}")
        return False

def setup_venv(python_cmd, venv_dir):
    """创建或使用虚拟环境"""
    if venv_dir.exists():
        print_info(f"使用已存在的虚拟环境: {venv_dir}")
    else:
        print_info(f"创建虚拟环境: {venv_dir}")
        try:
            subprocess.run([python_cmd, '-m', 'venv', str(venv_dir)], check=True)
        except subprocess.CalledProcessError as e:
            print_error(f"创建虚拟环境失败: {e}")
            return None, None
    
    # 获取虚拟环境中的 Python 路径
    if platform.system() == 'Windows':
        venv_python = venv_dir / 'Scripts' / 'python.exe'
        venv_pip = venv_dir / 'Scripts' / 'pip.exe'
    else:
        venv_python = venv_dir / 'bin' / 'python'
        venv_pip = venv_dir / 'bin' / 'pip'
    
    if not venv_python.exists():
        print_error(f"虚拟环境 Python 不存在: {venv_python}")
        return None, None
    
    print_success(f"虚拟环境 Python: {venv_python}")
    return str(venv_python), str(venv_pip)

def wait_for_exit():
    """等待用户按键后退出"""
    print()
    if platform.system() == 'Windows':
        os.system('pause')
    else:
        input("按 Enter 键退出...")

def main():
    print_info("SimpleTavern 一键部署脚本")
    print_info(f"操作系统: {platform.system()} {platform.release()}")
    print()
    
    # 获取项目根目录
    root_dir = Path(__file__).parent.resolve()
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"
    venv_dir = root_dir / "venv"
    
    # 检查必要的命令
    print_info("检查环境依赖...")
    
    python_cmd = find_python()
    if not python_cmd:
        print_error("Python 未安装或不在 PATH 中")
        print_error("请先安装 Python 3.7+")
        wait_for_exit()
        sys.exit(1)
    
    npm_cmd = find_npm()
    if not npm_cmd:
        print_error("Node.js/npm 未安装或不在 PATH 中")
        print_error("请先安装 Node.js 和 npm")
        wait_for_exit()
        sys.exit(1)
    
    print_success("环境检查通过")
    print()
    
    # 创建/使用虚拟环境
    print_info("设置 Python 虚拟环境...")
    venv_python, venv_pip = setup_venv(python_cmd, venv_dir)
    if not venv_python:
        print_error("虚拟环境设置失败")
        wait_for_exit()
        sys.exit(1)
    print()
    
    # 安装后端依赖
    print_info("安装后端依赖...")
    requirements_file = backend_dir / "requirements.txt"
    if not requirements_file.exists():
        print_error(f"找不到 requirements.txt: {requirements_file}")
        wait_for_exit()
        sys.exit(1)
    
    if not run_command([venv_python, "-m", "pip", "install", "-r", str(requirements_file)], cwd=backend_dir):
        print_error("后端依赖安装失败")
        wait_for_exit()
        sys.exit(1)
    
    print_success("后端依赖安装完成")
    print()
    
    # 安装前端依赖
    print_info("安装前端依赖...")
    if not (frontend_dir / "package.json").exists():
        print_error(f"找不到 package.json: {frontend_dir / 'package.json'}")
        wait_for_exit()
        sys.exit(1)
    
    if not run_command([npm_cmd, "install"], cwd=frontend_dir):
        print_error("前端依赖安装失败")
        wait_for_exit()
        sys.exit(1)
    
    print_success("前端依赖安装完成")
    print()
    
    # 构建前端
    print_info("构建前端...")
    if not run_command([npm_cmd, "run", "build"], cwd=frontend_dir):
        print_error("前端构建失败")
        wait_for_exit()
        sys.exit(1)
    
    print_success("前端构建完成")
    print()
    
    # 启动后端
    print_info("启动后端服务...")
    backend_port = 8000
    backend_url = f"http://localhost:{backend_port}"
    
    # 使用 uvicorn 启动后端
    backend_cmd = [venv_python, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(backend_port)]
    if platform.system() == 'Windows':
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE
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
        urllib.request.urlopen(f"{backend_url}/api/health", timeout=5)
        print_success(f"后端服务已启动: {backend_url}")
    except Exception as e:
        print_warning(f"后端服务可能未完全启动，继续...")
    
    print()
    
    # 启动前端预览服务器
    print_info("启动前端服务...")
    frontend_port = 4173  # vite preview 默认端口
    frontend_url = f"http://localhost:{frontend_port}"
    
    frontend_cmd = [npm_cmd, "run", "preview", "--", "--port", str(frontend_port), "--host"]
    if platform.system() == 'Windows':
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=frontend_dir,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
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
    print_success("=" * 50)
    print_success("部署完成！")
    print_success("=" * 50)
    print_info(f"后端地址: {backend_url}")
    print_info(f"前端地址: {frontend_url}")
    print_info(f"虚拟环境: {venv_dir}")
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
    try:
        main()
    except Exception as e:
        print_error(f"部署过程中发生错误: {e}")
        wait_for_exit()
        sys.exit(1)
