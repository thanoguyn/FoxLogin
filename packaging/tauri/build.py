"""Build the FoxLogin Tauri app and its installers for the current OS.

    python3 packaging/tauri/build.py            # backend (PyInstaller) + Tauri bundle
    python3 packaging/tauri/build.py --backend  # only the Python backend

Steps:
  1. a virtualenv in build/venv-tauri with requirements.txt + PyInstaller, plus the fpgen model
  2. PyInstaller one-dir build of packaging/tauri/backend.py -> build/tauri-pyi/dist/foxlogin-backend
  3. copy it to src-tauri/resources/backend (shipped as a Tauri resource)
  4. `tauri build` -> src-tauri/target/release/bundle/ (.app/.dmg, .msi/.exe, .AppImage/.deb)

Needs Python 3.10+, Rust (rustup) and Node.js 18+ on PATH.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BUILD = ROOT / "build"
VENV = BUILD / "venv-tauri"
RESOURCES = HERE / "src-tauri" / "resources" / "backend"


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def venv_python() -> Path:
    py = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        run([sys.executable, "-m", "venv", VENV])
        run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-q", "-r", ROOT / "requirements.txt", "-r", HERE / "requirements-build.txt"])
    # Camoufox installs its pinned fpgen model into fpgen's package folder on
    # first use; inside an installed app that folder is read-only, so bundle it now
    run([py, "-c", "from camoufox.fpgen_model import ensure_fpgen_model; ensure_fpgen_model()"])
    return py


def backend() -> None:
    py = venv_python()
    work = BUILD / "tauri-pyi"
    run([py, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", work / "dist",
         "--workpath", work / "work", HERE / "backend.spec"])
    shutil.rmtree(RESOURCES, ignore_errors=True)
    shutil.copytree(work / "dist" / "foxlogin-backend", RESOURCES, symlinks=True)
    # Camoufox dates the pinned model files 2100-01-01 so fpgen never refreshes
    # them; keep that date, because the installed copy cannot be rewritten
    for f in (RESOURCES / "_internal" / "fpgen" / "data").glob("*.zst"):
        os.utime(f, (4102444800, 4102444800))
    print("backend ->", RESOURCES)


def bundle() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    if not (HERE / "node_modules").exists():
        run([npm, "install"], cwd=HERE)
    run([npx, "tauri", "build"], cwd=HERE)
    print("bundles ->", HERE / "src-tauri" / "target" / "release" / "bundle")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", action="store_true", help="only build the Python backend")
    a = ap.parse_args()
    backend()
    if not a.backend:
        bundle()
