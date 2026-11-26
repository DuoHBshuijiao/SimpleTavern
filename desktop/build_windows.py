"""Build Windows x64 distributables from an explicit application-file allowlist."""
import argparse
import hashlib
from io import BytesIO
import json
import lzma
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
WORK = ROOT / "temp/windows-build"
UPX_VERSION = "5.3.0"
UPX_ARCHIVE = f"upx-{UPX_VERSION}-win64.zip"
UPX_SHA256 = "d127996c76615e431be810e9c8d2910dbe3dd400600c5c0c50276fc5a17a9705"


def run(*args, cwd=ROOT, env=None):
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


def web_install_key(frontend):
    key = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        key.update(hashlib.sha256((frontend / name).read_bytes()).digest())
    npmrc = frontend / ".npmrc"
    if npmrc.is_file():
        key.update(hashlib.sha256(npmrc.read_bytes()).digest())

    key.update(subprocess.check_output([
        "node", "-p", "JSON.stringify([process.version, process.platform, process.arch])",
    ], cwd=frontend))
    key.update(subprocess.check_output([
        "npm.cmd", "config", "get", "user-agent", "omit", "include", "os", "cpu", "libc",
        "ignore-scripts", "bin-links", "install-links", "install-strategy", "legacy-peer-deps",
        "strict-peer-deps", "engine-strict", "force",
    ], cwd=frontend))
    return key.hexdigest()


def web_install_is_current(frontend, marker, installed_lock, key):
    if not marker.is_file() or not installed_lock.is_file():
        return False
    lock_data = installed_lock.read_bytes()
    if marker.read_bytes() != f"{key}\n{hashlib.sha256(lock_data).hexdigest()}\n".encode("ascii"):
        return False

    packages = json.loads(lock_data)["packages"]
    bin_dir = installed_lock.parent / ".bin"
    return (
        all((bin_dir / tool).is_file() for tool in ("vue-tsc.cmd", "vite.cmd"))
        and all((frontend / entry / "package.json").is_file() for entry in packages)
    )


def build_web(frontend, *, clean_deps):
    modules = frontend / "node_modules"
    marker = modules / ".simpletavern-desktop-deps"
    installed_lock = modules / ".package-lock.json"
    key = web_install_key(frontend)
    if not clean_deps and web_install_is_current(frontend, marker, installed_lock, key):
        print("Reusing installed frontend dependencies.", flush=True)
    else:
        print("Installing frontend dependencies (npm ci).", flush=True)
        marker.unlink(missing_ok=True)
        run("npm.cmd", "ci", "--no-audit", "--no-fund", cwd=frontend)
        if installed_lock.is_file():
            digest = hashlib.sha256(installed_lock.read_bytes()).hexdigest()
            marker.write_bytes(f"{key}\n{digest}\n".encode("ascii"))
    run("npm.cmd", "run", "build", cwd=frontend)


def freeze():
    tokenizer_dir = "tokenizer/deepseek_v3_tokenizer"
    vocabulary = ROOT / "backend" / tokenizer_dir / "tokenizer.json"
    compressed_vocabulary = WORK / "tokenizer.json.xz"
    compressed_vocabulary.write_bytes(lzma.compress(vocabulary.read_bytes()))
    # The desktop server uses asyncio, h11, ws="none", and its own logging configuration.
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--noupx",
        "--name", "TavernService", "--distpath", WORK / "frozen", "--workpath", WORK / "pyi",
        "--specpath", WORK, "--paths", ROOT / "backend",
        "--collect-data", "certifi", "--collect-data", "jsonschema_specifications",
        "--hidden-import", "uvicorn.lifespan.on", "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.loops.asyncio", "--hidden-import", "win32timezone",
        "--exclude-module", "watchfiles", "--exclude-module", "httptools", "--exclude-module", "websockets",
        "--exclude-module", "dotenv", "--exclude-module", "yaml",
        "--add-data", f"{compressed_vocabulary}:{tokenizer_dir}",
        "--add-data", f"{ROOT / 'backend/app/llm/catalog/*.json'}:app/llm/catalog",
        "--add-data", f"{ROOT / 'backend/app/assistant/*.md'}:app/assistant",
        "--add-data", f"{ROOT / 'backend/app/MVU_AGENT.md'}:app",
        ROOT / "backend/desktop_service.py")


def unpack_upx(destination):
    cache = WORK / UPX_ARCHIVE
    archive = cache.read_bytes() if cache.is_file() else b""
    if hashlib.sha256(archive).hexdigest() != UPX_SHA256:
        url = f"https://github.com/upx/upx/releases/download/v{UPX_VERSION}/{UPX_ARCHIVE}"
        with urlopen(url, timeout=30) as response:
            archive = response.read()
        if hashlib.sha256(archive).hexdigest() != UPX_SHA256:
            raise ValueError("UPX download does not match its pinned SHA-256")
        cache.write_bytes(archive)
    with ZipFile(BytesIO(archive)) as bundle:
        destination.write_bytes(bundle.read(f"upx-{UPX_VERSION}-win64/upx.exe"))


def copy_native(source, destination, upx):
    from pefile import DIRECTORY_ENTRY, DLL_CHARACTERISTICS, PE

    with PE(str(source), fast_load=True) as image:
        header = image.OPTIONAL_HEADER
        signed = header.DATA_DIRECTORY[DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]].Size
        control_flow_guard = header.DllCharacteristics & DLL_CHARACTERISTICS["IMAGE_DLLCHARACTERISTICS_GUARD_CF"]
    if signed or control_flow_guard:
        shutil.copy2(source, destination)
        return
    run(upx, "--best", "--lzma", "-q", "-o", destination, source)
    run(upx, "-t", "-q", destination)


def stage_service(destination, upx):
    frozen = WORK / "frozen/TavernService"
    internal = frozen / "_internal"
    native = {
        internal / "cryptography/hazmat/bindings/_rust.pyd",
        internal / "tokenizers/tokenizers.pyd",
        *(internal / "pydantic_core").glob("_pydantic_core.*.pyd"),
    }

    def copy_file(source, target):
        if Path(source) in native:
            copy_native(source, target, upx)
        else:
            shutil.copy2(source, target)

    # Windows 10 and later provide UCRT as an operating system component.
    shutil.copytree(frozen, destination, copy_function=copy_file,
                    ignore=lambda folder, _: ("ucrtbase.dll",) if Path(folder) == internal else ())


def package(stage, output, pack_id, version):
    dll = os.environ.get("VPK_DLL")
    cli = [os.environ.get("VPK_DOTNET", "dotnet"), dll] if dll else ["vpk"]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".package-", dir=output) as tmp:
        releases = Path(tmp)
        # Seed the same release history so vpk can still generate deltas.
        for previous in output.glob(f"{pack_id}-*-win-x64-*.nupkg"):
            shutil.copy2(previous, releases)
        for name in ("releases.win-x64.json", "RELEASES-win-x64"):
            if (output / name).is_file():
                shutil.copy2(output / name, releases)
        # Velopack moves its temporary portable ZIP into the releases directory.
        with tempfile.TemporaryDirectory(prefix=".velopack-", dir=releases) as scratch:
            env = dict(os.environ, TEMP=scratch, TMP=scratch)
            run(*cli, "pack", "--packId", pack_id, "--packVersion", version,
                "--packDir", stage, "--mainExe", "SimpleTavern.exe", "--runtime", "win-x64",
                "--channel", "win-x64", "--framework", "webview2", "--icon", DESKTOP / "icons/icon.ico",
                "--outputDir", releases, env=env)
        setup = releases / f"{pack_id}-win-x64-Setup.exe"
        payload = setup.rename(releases / "VelopackSetup.exe")
        env = dict(os.environ, SIMPLETAVERN_SETUP_PAYLOAD=str(payload), SIMPLETAVERN_SETUP_PACK_ID=pack_id)
        run("cargo", "build", "--locked", "--release", "--manifest-path", DESKTOP / "Cargo.toml",
            "--features", "setup", "--bin", "SimpleTavernSetup", env=env)
        shutil.copy2(DESKTOP / "target/release/SimpleTavernSetup.exe", setup)
        payload.unlink()
        with ZipFile(releases / f"{pack_id}-win-x64-Portable.zip") as portable:
            size = sum(item.file_size for item in portable.infolist())
        print(f"Extracted portable program: {size / 1024**2:.2f} MiB ({size:,} bytes)", flush=True)
        # Publish the files referenced by the feed before publishing the feed itself.
        for artifact in sorted(releases.iterdir(), key=lambda file: file.suffix not in {".nupkg", ".exe", ".zip"}):
            artifact.replace(output / artifact.name)


def build(opts):
    if opts.qa:
        os.environ["SIMPLETAVERN_LOCAL_TEST_FEED"] = str(opts.output.resolve())
        os.environ["TAURI_CONFIG"] = json.dumps({"identifier": "io.github.duohbshuijiao.simpletavern.qa"})
    else:
        os.environ.pop("SIMPLETAVERN_LOCAL_TEST_FEED", None)
    if not opts.reuse_web:
        build_web(ROOT / "frontend", clean_deps=opts.clean_web_deps)
    if not opts.reuse_service:
        freeze()
    run("cargo", "build", "--locked", "--release", "--manifest-path", DESKTOP / "Cargo.toml",
        "--features", "setup", "--bin", "SimpleTavern")
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        stage = Path(tmp) / "app"
        stage.mkdir()
        upx = Path(tmp) / "upx.exe"
        unpack_upx(upx)
        copy_native(DESKTOP / "target/release/SimpleTavern.exe", stage / "SimpleTavern.exe", upx)
        stage_service(stage / "service", upx)
        shutil.copytree(ROOT / "frontend/dist", stage / "web")
        shutil.copytree(ROOT / "extensions/simpletavern-janitor-bridge", stage / "extensions/simpletavern-janitor-bridge")
        for name in ("NOTICE", "LICENSE"):
            shutil.copy2(ROOT / name, stage)
        pack_id = "SimpleTavernDesktopQA" if opts.qa else "SimpleTavern"
        package(stage, opts.output.resolve(), pack_id, opts.version)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Velopack SemVer, e.g. 1.0.0")
    parser.add_argument("--reuse-service", action="store_true", help="use the previous frozen backend")
    web_options = parser.add_mutually_exclusive_group()
    web_options.add_argument("--reuse-web", action="store_true", help="use the previous production frontend build")
    web_options.add_argument("--clean-web-deps", action="store_true", help="reinstall frontend dependencies before building")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/windows")
    parser.add_argument("--qa", action="store_true", help="use a separate setup identity and a local test update feed")
    opts = parser.parse_args()
    if os.name != "nt":
        parser.error("Build on Windows x64")

    import msvcrt
    WORK.mkdir(parents=True, exist_ok=True)
    # Both variants use the same Cargo build directory and frozen service.
    with (WORK / "package.lock").open("a+b") as lock:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            parser.error("Another Windows packaging build is using this checkout")
        build(opts)


if __name__ == "__main__":
    main()
