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
import hashlib
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

def maybe_run_npm_audit_fix(npm_cmd, frontend_dir: Path) -> None:
    """
    在 npm install 之后：若 npm audit 报告漏洞或提示可执行 npm audit fix，则先运行 npm audit fix。
    audit fix 失败时仅警告，不中断部署。
    """
    shell = platform.system() == "Windows"
    try:
        result = subprocess.run(
            [npm_cmd, "audit"],
            cwd=frontend_dir,
            shell=shell,
            capture_output=True,
            text=True,
        )
    except Exception as e:
        print_warning(f"无法执行 npm audit（已跳过 audit fix）: {e}")
        return

    combined = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    need_fix = result.returncode != 0
    if not need_fix:
        # 与 npm install 末尾提示类似：To address all issues, run: npm audit fix
        need_fix = (
            "npm audit fix" in combined
            and (
                "to address" in combined
                or "to fix" in combined
                or "vulnerabilit" in combined
            )
        )

    if not need_fix:
        return

    print_info("检测到依赖安全提示，正在执行 npm audit fix...")
    if run_command([npm_cmd, "audit", "fix"], cwd=frontend_dir, check=False):
        print_success("npm audit fix 已完成")
    else:
        print_warning("npm audit fix 未完全成功，将继续后续步骤")

def get_venv_python(venv_dir):
    """获取虚拟环境中的 Python 路径"""
    if platform.system() == 'Windows':
        venv_python = venv_dir / 'Scripts' / 'python.exe'
    else:
        venv_python = venv_dir / 'bin' / 'python'
    return venv_python

def setup_venv(python_cmd, venv_dir):
    """创建或使用虚拟环境"""
    venv_python = get_venv_python(venv_dir)
    
    # 若 venv 目录存在但 Python 可执行文件不存在（如下载的源码含空/损坏的 venv），则删除并重建
    if venv_dir.exists() and not venv_python.exists():
        print_warning(f"检测到无效的虚拟环境（Python 不存在），将删除并重新创建: {venv_dir}")
        try:
            shutil.rmtree(venv_dir)
        except Exception as e:
            print_error(f"删除无效虚拟环境失败: {e}")
            return None
    
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

def _summarize_command_output(stdout: str, stderr: str, max_lines: int = 16) -> str:
    """拼接并裁剪命令输出，便于在控制台显示关键错误。"""
    combined = ((stderr or "").strip() + "\n" + (stdout or "").strip()).strip()
    if not combined:
        return "无详细输出。"
    lines = [ln for ln in combined.splitlines() if ln.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def check_backend_runtime(venv_python, backend_dir):
    """检查后端应用是否可导入（比仅检查 fastapi/uvicorn 更接近真实启动）。"""
    try:
        result = subprocess.run(
            [venv_python, '-c', 'import app.main; print("ok")'],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        ok = result.returncode == 0 and 'ok' in result.stdout
        if ok:
            return True, ""
        return False, _summarize_command_output(result.stdout, result.stderr)
    except Exception as e:
        return False, str(e)


_REQUIREMENTS_HASH_FILENAME = ".requirements-hash"


def compute_requirements_hash(backend_dir: Path) -> str:
    """对 backend/requirements.txt 内容计算 SHA256（与 pip 解析无关，仅检测清单变更）。"""
    req_file = backend_dir / "requirements.txt"
    return hashlib.sha256(req_file.read_bytes()).hexdigest()


def get_saved_requirements_hash(venv_dir: Path) -> str | None:
    """读取 venv 内记录的 requirements 摘要，不存在或无效则返回 None。"""
    path = venv_dir / _REQUIREMENTS_HASH_FILENAME
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except Exception:
        return None


def save_requirements_hash(venv_dir: Path, hash_value: str) -> None:
    """将 requirements 摘要写入虚拟环境目录（与已安装依赖对应）。"""
    (venv_dir / _REQUIREMENTS_HASH_FILENAME).write_text(hash_value + "\n", encoding="utf-8")


def requirements_synced_with_venv(venv_dir: Path, backend_dir: Path) -> tuple[bool, str]:
    """
    判断当前 requirements.txt 是否与上次 pip install 后记录一致。
    不一致或从未记录时返回 (False, 原因)，需执行 pip install -r。
    """
    req_file = backend_dir / "requirements.txt"
    if not req_file.is_file():
        return False, "缺少 requirements.txt"
    try:
        current = compute_requirements_hash(backend_dir)
    except Exception as e:
        return False, f"读取 requirements.txt 失败: {e}"
    saved = get_saved_requirements_hash(venv_dir)
    if saved is None:
        return False, "未记录 requirements 摘要（需同步依赖）"
    if saved != current:
        return False, "requirements.txt 已变更"
    return True, ""


def check_backend_deps(venv_python, backend_dir, venv_dir: Path):
    """检查后端依赖可导入，且 requirements.txt 与 venv 内记录一致。"""
    runtime_ok, _ = check_backend_runtime(venv_python, backend_dir)
    if not runtime_ok:
        return False
    synced, _ = requirements_synced_with_venv(venv_dir, backend_dir)
    return synced


def maybe_run_pip_check(venv_python: str, backend_dir: Path) -> None:
    """
    在 pip install 之后：运行 pip check 做环境一致性检查；失败时仅警告，不中断部署。
    """
    try:
        result = subprocess.run(
            [venv_python, "-m", "pip", "check"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )
    except Exception as e:
        print_warning(f"无法执行 pip check（已跳过）: {e}")
        return
    if result.returncode == 0:
        return
    combined = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    print_warning("pip check 报告依赖问题（应用仍可能可运行）:")
    if combined:
        print_warning(_summarize_command_output(result.stdout, result.stderr, max_lines=20))


def check_deployment_status(venv_dir, backend_dir, frontend_dir):
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
    
    # 检查后端依赖（应用可导入 + requirements 摘要与 venv 记录一致）
    if status['venv_exists']:
        status['backend_deps_ok'] = check_backend_deps(str(venv_python), backend_dir, venv_dir)
    
    # 检查前端 node_modules
    node_modules = frontend_dir / 'node_modules'
    status['node_modules_exists'] = node_modules.exists() and any(node_modules.iterdir())
    
    # 检查前端 dist
    dist_dir = frontend_dir / 'dist'
    status['dist_exists'] = dist_dir.exists() and (dist_dir / 'index.html').exists()
    
    is_ready = all(status.values())
    return is_ready, status

# 前端源码 hash 校验：排除的目录与文件
_FRONTEND_HASH_EXCLUDE_DIRS = {".vscode", "dist", "node_modules"}
_FRONTEND_HASH_EXCLUDE_FILES = {".gitignore"}
_BUILD_HASH_FILENAME = ".build-hash"

def compute_frontend_source_hash(frontend_dir: Path) -> str:
    """对 frontend 目录内源码计算 hash，排除 .vscode、dist、node_modules 及 .gitignore。"""
    h = hashlib.sha256()
    collected = []
    for root, dirs, files in os.walk(frontend_dir, topdown=True):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in _FRONTEND_HASH_EXCLUDE_DIRS]
        for f in files:
            if f in _FRONTEND_HASH_EXCLUDE_FILES:
                continue
            collected.append(root_path / f)
    for p in sorted(collected, key=lambda x: x.as_posix()):
        try:
            with open(p, "rb") as fp:
                while True:
                    chunk = fp.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
        except Exception:
            pass
    return h.hexdigest()

def get_saved_build_hash(frontend_dir: Path) -> str | None:
    """读取 dist 内保存的构建 hash，不存在或无效则返回 None。"""
    path = frontend_dir / "dist" / _BUILD_HASH_FILENAME
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except Exception:
        return None

def save_build_hash(frontend_dir: Path, hash_value: str) -> None:
    """将构建 hash 写入 dist 目录。"""
    dist_dir = frontend_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / _BUILD_HASH_FILENAME).write_text(hash_value, encoding="utf-8")

def need_frontend_build(frontend_dir: Path) -> tuple[bool, str]:
    """
    判断是否需要执行前端 build。
    返回 (need_build, reason)。
    需要 build：dist 不存在或无效、未检测到 hash、hash 与当前源码不一致。
    """
    dist_dir = frontend_dir / "dist"
    if not dist_dir.exists() or not (dist_dir / "index.html").exists():
        return True, "dist 不存在或无效"
    saved = get_saved_build_hash(frontend_dir)
    if saved is None:
        return True, "未检测到构建 hash"
    current = compute_frontend_source_hash(frontend_dir)
    if current != saved:
        return True, "源码已变更，hash 不一致"
    return False, "hash 一致，跳过构建"

def wait_for_exit():
    """等待用户按键后退出"""
    print()
    if platform.system() == 'Windows':
        os.system('pause')
    else:
        input("按 Enter 键退出...")

def _windows_cmd_k_in_dir(cmd_line: str, cwd: Path) -> subprocess.Popen:
    """
    在 cwd 下用 cmd /k 执行命令行（命令里不要写项目路径，避免空格/括号；目录由 Popen 的 cwd 指定）。
    """
    return subprocess.Popen(
        ["cmd.exe", "/k", cmd_line],
        cwd=cwd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

def _windows_npm_cmd_fragment(npm_cmd: str) -> str:
    """供 cmd 使用的 npm 调用片段：Windows 上 npm 实为 npm.cmd，不能 CreateProcess 直接当 exe 跑。"""
    n = npm_cmd.strip()
    if len(n) >= 2 and n[0] == '"' and n[-1] == '"':
        return n
    return f'"{n}"' if " " in n else n

def _windows_try_backend_cmd_k(venv_python: str, backend_dir: Path, backend_port: int) -> subprocess.Popen | None:
    """
    若 venv 的 python 相对 backend 目录可用相对路径表达，则用 cmd /k + 相对路径启动，
    命令行里不含带括号/空格的用户绝对路径；末尾 || pause 便于启动失败时窗口停留。
    """
    try:
        vp = Path(venv_python).resolve()
        bd = Path(backend_dir).resolve()
        rel = os.path.relpath(vp, bd)
    except Exception:
        return None
    if not rel or os.path.isabs(rel):
        return None
    rel_norm = os.path.normpath(rel).replace("/", "\\")
    cmd_line = (
        f"{rel_norm} -m uvicorn app.main:app --host 0.0.0.0 --port {backend_port} || pause"
    )
    return _windows_cmd_k_in_dir(cmd_line, bd)

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
        # 优先 cmd /k + 相对路径（如 ..\venv\Scripts\python.exe）：命令行不含带括号/空格的用户绝对路径；
        # 失败时 || pause 保留窗口。无法写相对路径时退回 CreateProcess 直接调 python.exe。
        w = _windows_try_backend_cmd_k(venv_python, backend_dir, backend_port)
        if w is not None:
            backend_process = w
        else:
            backend_process = subprocess.Popen(
                backend_cmd,
                cwd=backend_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
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
        if platform.system() == "Windows":
            print_info("若后端启动失败，请查看弹出的后端控制台窗口中的报错信息。")
    
    print()
    
    # 启动前端
    print_info("启动前端服务...")
    if platform.system() == 'Windows':
        # npm 在 Windows 上是 npm.cmd，不能 Popen(["npm", ...]) 直接启动（会 WinError 2）。
        # 仅把「npm run …」交给 cmd，项目路径只用 cwd=frontend_dir，避免路径含空格/括号时整行解析失败。
        npm_part = _windows_npm_cmd_fragment(npm_cmd)
        frontend_cmd_line = (
            f"{npm_part} run preview -- --port {frontend_port} --host || pause"
        )
        frontend_process = _windows_cmd_k_in_dir(frontend_cmd_line, frontend_dir)
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
        print_error("请先安装 Python 3.10+")
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
    is_ready, status = check_deployment_status(venv_dir, backend_dir, frontend_dir)
    
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

            try:
                save_requirements_hash(venv_dir, compute_requirements_hash(backend_dir))
            except Exception as e:
                print_warning(f"写入 requirements 摘要失败（下次可能重复安装依赖）: {e}")

            maybe_run_pip_check(venv_python, backend_dir)

            print_success("后端依赖安装完成")
            print()
        else:
            print_info("后端依赖已安装，跳过")
            print()

        print_info("校验后端应用导入...")
        runtime_ok, runtime_err = check_backend_runtime(venv_python, backend_dir)
        if not runtime_ok:
            print_error("后端应用导入失败，无法启动。")
            if runtime_err:
                print_error(runtime_err)
            wait_for_exit()
            sys.exit(1)
        print_success("后端应用导入校验通过")
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

            maybe_run_npm_audit_fix(npm_cmd, frontend_dir)

            print_success("前端依赖安装完成")
            print()
        else:
            print_info("前端依赖已安装，跳过")
            print()
    
    # 前端构建（按 hash 决定是否执行）
    need_build, reason = need_frontend_build(frontend_dir)
    if need_build:
        print_info(reason)
        print_info("构建前端...")
        if not run_command([npm_cmd, "run", "build"], cwd=frontend_dir):
            print_error("前端构建失败")
            wait_for_exit()
            sys.exit(1)
        save_build_hash(frontend_dir, compute_frontend_source_hash(frontend_dir))
        print_success("前端构建完成")
    else:
        print_info(reason)
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
        print_info("请分别关闭前端、后端控制台窗口，再关闭本窗口。")
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
