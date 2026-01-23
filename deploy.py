#!/usr/bin/env python3
"""
SimpleTavern 一键部署脚本
支持 Windows 和 Linux 系统
自动检测部署状态，选择"安装模式"或"启动模式"
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
    CYAN = '\033[96m'
    RESET = '\033[0m'

def _mark(ok: bool) -> str:
    """
    控制台状态标记：
    - 若当前 stdout 编码能输出 '✓/✗'，则优先使用（更直观）
    - 否则回退到 ASCII（避免某些 Windows 控制台编码报错）
    """
    try:
        enc = sys.stdout.encoding or "utf-8"
        "✓".encode(enc)
        "✗".encode(enc)
        return "✓" if ok else "✗"
    except Exception:
        return "OK" if ok else "NO"

def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {msg}")

def print_error(msg):
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")

def print_mode(msg):
    print(f"{Colors.CYAN}[MODE]{Colors.RESET} {msg}")

def find_python():
    """查找 Python 可执行文件"""
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
                # Windows 下优先返回短命令名，避免路径带空格导致 cmd /k 启动命令的嵌套引号问题
                if platform.system() == "Windows":
                    return "npm"
                return npm_path
        except Exception:
            pass
    
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
    except subprocess.CalledProcessError:
        print_error(f"命令执行失败: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        return False
    except Exception as e:
        print_error(f"执行命令时出错: {e}")
        return False

def get_venv_python(venv_dir):
    """获取虚拟环境中的 Python 路径"""
    if platform.system() == 'Windows':
        venv_python = venv_dir / 'Scripts' / 'python.exe'
    else:
        venv_python = venv_dir / 'bin' / 'python'
    return venv_python

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
            return None
    
    venv_python = get_venv_python(venv_dir)
    
    if not venv_python.exists():
        print_error(f"虚拟环境 Python 不存在: {venv_python}")
        return None
    
    print_success(f"虚拟环境 Python: {venv_python}")
    return str(venv_python)

def check_backend_deps(venv_python):
    """检查后端依赖是否已安装"""
    try:
        result = subprocess.run(
            [venv_python, '-c', 'import uvicorn; import fastapi; print("ok")'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and 'ok' in result.stdout
    except Exception:
        return False

def check_deployment_status(venv_dir, frontend_dir):
    """
    检查部署状态，返回 (is_ready, status_details)
    is_ready: True 表示可以直接启动，False 表示需要安装
    """
    status = {
        'venv_exists': False,
        'backend_deps_ok': False,
        'node_modules_exists': False,
        'dist_exists': False,
    }
    
    venv_python = get_venv_python(venv_dir)
    
    # 检查虚拟环境
    status['venv_exists'] = venv_dir.exists() and venv_python.exists()
    
    # 检查后端依赖
    if status['venv_exists']:
        status['backend_deps_ok'] = check_backend_deps(str(venv_python))
    
    # 检查前端 node_modules
    node_modules = frontend_dir / 'node_modules'
    status['node_modules_exists'] = node_modules.exists() and any(node_modules.iterdir())
    
    # 检查前端 dist
    dist_dir = frontend_dir / 'dist'
    status['dist_exists'] = dist_dir.exists() and (dist_dir / 'index.html').exists()
    
    is_ready = all(status.values())
    return is_ready, status

def wait_for_exit():
    """等待用户按键后退出"""
    print()
    if platform.system() == 'Windows':
        os.system('pause')
    else:
        input("按 Enter 键退出...")

def start_services(venv_python, npm_cmd, backend_dir, frontend_dir):
    """启动后端和前端服务"""
    backend_port = 8000
    frontend_port = 4173
    backend_url = f"http://localhost:{backend_port}"
    frontend_url = f"http://localhost:{frontend_port}"
    
    # 启动后端
    print_info("启动后端服务...")
    backend_cmd = [venv_python, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(backend_port)]
    if platform.system() == 'Windows':
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            # 单独控制台窗口，便于用户查看日志/手动关闭
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    print_info("等待后端服务启动...")
    time.sleep(3)
    
    try:
        import urllib.request
        urllib.request.urlopen(f"{backend_url}/api/health", timeout=5)
        print_success(f"后端服务已启动: {backend_url}")
    except Exception:
        print_warning("后端服务可能未完全启动，继续...")
    
    print()
    
    # 启动前端
    print_info("启动前端服务...")
    if platform.system() == 'Windows':
        # Windows 下如果直接用 npm.cmd / shell=True，terminate() 往往只会杀掉“壳进程”，node/vite 子进程会残留。
        # 这里显式启动一个可见的 cmd 窗口，并在退出时用 taskkill /T 杀掉整棵进程树（见下方 KeyboardInterrupt 处理）。
        # 注意：cmd.exe /k 往往会给整段命令再包一层外部引号；因此此处避免在命令内部再嵌套引号（尤其是带空格的 npm 路径）。
        # 这里依赖 npm 在 PATH 中可用（find_npm 已优先返回 "npm"）。
        frontend_dir_str = str(frontend_dir)
        frontend_cmd_str = f'title SimpleTavern Frontend & cd /d {frontend_dir_str} & {npm_cmd} run preview -- --port {frontend_port} --host'
        frontend_process = subprocess.Popen(
            ["cmd.exe", "/k", frontend_cmd_str],
            cwd=frontend_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        frontend_cmd = [npm_cmd, "run", "preview", "--", "--port", str(frontend_port), "--host"]
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    print_info("等待前端服务启动...")
    time.sleep(3)
    print_success(f"前端服务已启动: {frontend_url}")
    print()
    
    # 打开浏览器
    print_info("正在打开浏览器...")
    try:
        webbrowser.open(frontend_url)
        print_success(f"已打开浏览器: {frontend_url}")
    except Exception as e:
        print_warning(f"无法自动打开浏览器: {e}")
        print_info(f"请手动访问: {frontend_url}")
    
    return backend_process, frontend_process, backend_url, frontend_url


def _terminate_process_tree_windows(pid: int) -> None:
    """Windows: 结束指定 PID 的进程树（包含子进程）。"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
    except Exception:
        # 终止过程不应影响主流程退出
        pass

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
    
    # 检查部署状态
    print_info("检查部署状态...")
    is_ready, status = check_deployment_status(venv_dir, frontend_dir)
    
    print_info(f"  - 虚拟环境: {_mark(status['venv_exists'])}")
    print_info(f"  - 后端依赖: {_mark(status['backend_deps_ok'])}")
    print_info(f"  - 前端依赖 (node_modules): {_mark(status['node_modules_exists'])}")
    print_info(f"  - 前端构建 (dist): {_mark(status['dist_exists'])}")
    print()
    
    if is_ready:
        # 启动模式
        print_mode("检测到已完成部署，进入【启动模式】")
        print()
        
        venv_python = str(get_venv_python(venv_dir))
        
    else:
        # 安装模式
        print_mode("检测到需要安装/构建，进入【安装模式】")
        print()
        
        # 创建/使用虚拟环境
        print_info("设置 Python 虚拟环境...")
        venv_python = setup_venv(python_cmd, venv_dir)
        if not venv_python:
            print_error("虚拟环境设置失败")
            wait_for_exit()
            sys.exit(1)
        print()
        
        # 安装后端依赖
        if not status['backend_deps_ok']:
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
        else:
            print_info("后端依赖已安装，跳过")
            print()
        
        # 安装前端依赖
        if not status['node_modules_exists']:
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
        else:
            print_info("前端依赖已安装，跳过")
            print()
        
        # 构建前端
        if not status['dist_exists']:
            print_info("构建前端...")
            if not run_command([npm_cmd, "run", "build"], cwd=frontend_dir):
                print_error("前端构建失败")
                wait_for_exit()
                sys.exit(1)
            
            print_success("前端构建完成")
            print()
        else:
            print_info("前端已构建，跳过")
            print()
    
    # 启动服务
    backend_process, frontend_process, backend_url, frontend_url = start_services(
        venv_python, npm_cmd, backend_dir, frontend_dir
    )
    
    print()
    print_success("=" * 50)
    print_success("服务已启动！")
    print_success("=" * 50)
    print_info(f"后端地址: {backend_url}")
    print_info(f"前端地址: {frontend_url}")
    print_info(f"虚拟环境: {venv_dir}")
    if platform.system() == "Windows":
        print_info("Windows 提示：已分别打开后端/前端控制台窗口；也可在本窗口按 Ctrl+C 一键停止两者")
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
        if platform.system() == "Windows":
            # 用 taskkill /T 确保 node/vite 等子进程不会残留
            if backend_process and backend_process.poll() is None:
                _terminate_process_tree_windows(backend_process.pid)
            if frontend_process and frontend_process.poll() is None:
                _terminate_process_tree_windows(frontend_process.pid)
        else:
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
