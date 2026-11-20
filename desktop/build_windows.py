"""Build Windows x64 distributables from an explicit application-file allowlist."""
import argparse
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
WORK = ROOT / "temp/windows-build"


def run(*args, cwd=ROOT):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def freeze():
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "TavernService", "--distpath", WORK / "frozen", "--workpath", WORK / "pyi",
        "--specpath", WORK, "--paths", ROOT / "backend",
        "--collect-data", "certifi", "--collect-data", "jsonschema_specifications",
        "--hidden-import", "uvicorn.lifespan.on", "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.loops.asyncio", "--hidden-import", "win32timezone",
        "--add-data", f"{ROOT / 'backend/tokenizer'}:tokenizer",
        "--add-data", f"{ROOT / 'backend/app/llm/catalog/*.json'}:app/llm/catalog",
        "--add-data", f"{ROOT / 'backend/app/assistant/*.md'}:app/assistant",
        "--add-data", f"{ROOT / 'backend/app/MVU_AGENT.md'}:app",
        ROOT / "backend/desktop_service.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Velopack SemVer, e.g. 1.0.0")
    parser.add_argument("--reuse-service", action="store_true", help="use the previous frozen backend")
    parser.add_argument("--reuse-web", action="store_true", help="use the previous production frontend build")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/windows")
    parser.add_argument("--qa", action="store_true", help="use a separate setup identity and a local test update feed")
    opts = parser.parse_args()
    if opts.qa:
        os.environ["SIMPLETAVERN_LOCAL_TEST_FEED"] = str(opts.output.resolve())
        os.environ["TAURI_CONFIG"] = json.dumps({"identifier": "io.github.duohbshuijiao.simpletavern.qa"})
    else:
        os.environ.pop("SIMPLETAVERN_LOCAL_TEST_FEED", None)
    if os.name != "nt":
        parser.error("Build on Windows x64")
    WORK.mkdir(parents=True, exist_ok=True)
    if not opts.reuse_web:
        run("npm.cmd", "ci", "--no-audit", "--no-fund", cwd=ROOT / "frontend")
        run("npm.cmd", "run", "build", cwd=ROOT / "frontend")
    if not opts.reuse_service:
        freeze()
    run("cargo", "build", "--locked", "--release", "--manifest-path", DESKTOP / "Cargo.toml")
    import tempfile
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        stage = Path(tmp)
        shutil.copy2(DESKTOP / "target/release/SimpleTavern.exe", stage)
        shutil.copytree(WORK / "frozen/TavernService", stage / "service")
        shutil.copytree(ROOT / "frontend/dist", stage / "web")
        shutil.copytree(ROOT / "extensions/simpletavern-janitor-bridge", stage / "extensions/simpletavern-janitor-bridge")
        for name in ("NOTICE", "LICENSE"):
            shutil.copy2(ROOT / name, stage)
        dll = os.environ.get("VPK_DLL")
        cli = [os.environ.get("VPK_DOTNET", "dotnet"), dll] if dll else ["vpk"]
        run(*cli, "pack", "--packId", "SimpleTavernDesktopQA" if opts.qa else "SimpleTavern", "--packVersion", opts.version,
            "--packDir", stage, "--mainExe", "SimpleTavern.exe", "--runtime", "win-x64",
            "--channel", "win-x64", "--framework", "webview2", "--icon", DESKTOP / "icons/icon.ico",
            "--outputDir", opts.output.resolve())


if __name__ == "__main__":
    main()
