"""Build the FoxLogin desktop app and its installer for the current OS.

    python3 packaging/pywebview/build.py                 # this machine's architecture
    python3 packaging/pywebview/build.py --arch x86_64   # macOS: Intel build (via Rosetta)
    python3 packaging/pywebview/build.py --arch arm64    # macOS: Apple Silicon build

Each architecture gets its own virtualenv in build/, so the packaged Python and
every native wheel (numpy, orjson, pydantic-core, ...) match the target CPU.
Output lands in dist/:

    macOS    FoxLogin-<ver>-macos-<arch>.dmg
    Windows  FoxLogin-<ver>-windows-x64-setup.exe   (Inno Setup; .zip if iscc is missing)
    Linux    FoxLogin-<ver>-linux-<arch>.AppImage    (when appimagetool is on PATH) + .tar.gz

Optional signing (macOS), from the environment:
    FOXLOGIN_SIGN_ID       "Developer ID Application: Name (TEAMID)"  (default: ad-hoc)
    FOXLOGIN_NOTARY_PROFILE  a `xcrun notarytool store-credentials` profile name
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"

# Oldest macOS the app supports. pip on a new Mac prefers wheels built for
# macOS 14/15 (numpy, orjson, ...), which refuse to load on older systems, so
# wheel selection and source builds are pinned to this version.
MACOS_MIN = "11.0"
# Playwright >= 1.57 bundles Node 24, which needs macOS 13.5. Its driver only
# asks for Node >= 20, so the macOS app ships Node 22 LTS (macOS 11+) instead.
MAC_NODE = "v22.18.0"
ZSTD_URL = "https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz"

# pip, made to see this macOS version when it picks wheels
PIP_MACOS = """
import platform, sys
platform.mac_ver = lambda *a: ("{v}", ("", "", ""), platform.machine())
from pip._internal.cli.main import main
sys.exit(main(sys.argv[1:]))
"""


def version() -> str:
    for line in (ROOT / "app" / "core.py").read_text().splitlines():
        if line.startswith("VERSION = "):
            return line.split('"')[1]
    return "0.0.0"


def host_arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(m, m)


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


class Env:
    """A per-architecture virtualenv; on macOS every call runs under `arch -<arch>`."""

    def __init__(self, arch: str):
        self.arch = arch
        self.dir = BUILD / f"venv-{sys.platform}-{arch}"
        self.prefix = ["arch", f"-{arch}"] if sys.platform == "darwin" else []
        bindir = "Scripts" if os.name == "nt" else "bin"
        self.python = self.dir / bindir / ("python.exe" if os.name == "nt" else "python")

    def create(self):
        if not self.python.exists():
            # A universal2 python.org interpreter can create either architecture
            run(self.prefix + [sys.executable, "-m", "venv", self.dir])
        self.py("-m", "pip", "install", "-q", "--upgrade", "pip")
        if sys.platform == "darwin":
            self.mac_indexed_zstd()
        self.pip("install", "-q", "-r", ROOT / "requirements.txt", "-r", PKG / "requirements-build.txt")

    def py(self, *args, **kw):
        run(self.prefix + [self.python, *args], **kw)

    def pip(self, *args, **kw):
        if sys.platform == "darwin":
            env = dict(kw.pop("env", os.environ), MACOSX_DEPLOYMENT_TARGET=MACOS_MIN)
            self.py("-I", "-c", PIP_MACOS.format(v=MACOS_MIN), *args, env=env, **kw)
        else:
            self.py("-m", "pip", *args, **kw)

    def mac_indexed_zstd(self):
        """fpgen needs indexed_zstd, which has no Intel wheel and only a macOS 15
        arm64 one. Build it against a static libzstd for this arch and MACOS_MIN."""
        src = BUILD / "zstd-1.5.7"
        if not src.exists():
            BUILD.mkdir(exist_ok=True)
            tgz = BUILD / "zstd.tar.gz"
            run(["curl", "-fsSL", "-o", tgz, ZSTD_URL])   # python.org builds may lack CA certs
            with tarfile.open(tgz) as t:
                t.extractall(BUILD, filter="data")
        lib = BUILD / f"zstd-{self.arch}"
        if not (lib / "libzstd.a").exists():
            flags = f"-O3 -fPIC -arch {self.arch} -mmacosx-version-min={MACOS_MIN}"
            run(["make", "-C", src / "lib", "clean"], stdout=subprocess.DEVNULL)
            run(self.prefix + ["make", "-C", src / "lib", "-j8", "libzstd.a", f"CFLAGS={flags}"],
                stdout=subprocess.DEVNULL)
            lib.mkdir(exist_ok=True)
            shutil.copy(src / "lib" / "libzstd.a", lib / "libzstd.a")
        env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET=MACOS_MIN, ARCHFLAGS=f"-arch {self.arch}",
                   CFLAGS=f"-I{src / 'lib'} -arch {self.arch}", LDFLAGS=f"-L{lib} -arch {self.arch}")
        self.pip("install", "-q", "--no-binary", "indexed_zstd", "--no-cache-dir", "indexed_zstd", env=env)


def pyinstaller(env: Env) -> Path:
    if not (PKG / "assets" / "icon.png").exists():
        env.py(PKG / "make_icons.py")
    out = BUILD / f"pyi-{sys.platform}-{env.arch}"
    e = dict(os.environ, FOXLOGIN_VERSION=version())
    if sys.platform == "darwin":
        e["FOXLOGIN_ARCH"] = env.arch
    env.py("-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
           "--distpath", out / "dist", "--workpath", out / "work", PKG / "foxlogin.spec", env=e)
    return out / "dist"


# ----------------------------------------------------------------- installers

def mac_node(app: Path, arch: str) -> None:
    name = f"node-{MAC_NODE}-darwin-{'x64' if arch == 'x86_64' else 'arm64'}"
    node = BUILD / name / "bin" / "node"
    if not node.exists():
        tgz = BUILD / f"{name}.tar.gz"
        run(["curl", "-fsSL", "-o", tgz, f"https://nodejs.org/dist/{MAC_NODE}/{name}.tar.gz"])
        with tarfile.open(tgz) as t:
            t.extract(f"{name}/bin/node", BUILD, filter="data")
    for target in app.glob("Contents/*/playwright/driver/node"):
        if not target.is_symlink():
            shutil.copy2(node, target)


def mac_installer(dist: Path, arch: str) -> Path:
    app = dist / "FoxLogin.app"
    mac_node(app, arch)
    sign_id = os.environ.get("FOXLOGIN_SIGN_ID") or "-"   # empty CI secret = ad-hoc
    sign = ["codesign", "--force", "--deep", "--sign", sign_id]
    if sign_id != "-":
        sign += ["--options", "runtime", "--timestamp",
                 "--entitlements", PKG / "macos" / "entitlements.plist"]
    run(sign + [app])
    stage = dist / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    run(["ditto", app, stage / "FoxLogin.app"])
    (stage / "Applications").symlink_to("/Applications")
    DIST.mkdir(exist_ok=True)
    dmg = DIST / f"FoxLogin-{version()}-macos-{arch}.dmg"
    dmg.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", "FoxLogin", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg])
    if sign_id != "-":
        run(["codesign", "--sign", sign_id, "--timestamp", dmg])
        if prof := os.environ.get("FOXLOGIN_NOTARY_PROFILE"):
            run(["xcrun", "notarytool", "submit", dmg, "--keychain-profile", prof, "--wait"])
            run(["xcrun", "stapler", "staple", dmg])
    return dmg


def windows_installer(dist: Path) -> Path:
    DIST.mkdir(exist_ok=True)
    iscc = shutil.which("iscc") or next(
        (p for p in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",) if p.exists()), None)
    if iscc:
        run([iscc, f"/DAppVersion={version()}", f"/DSourceDir={dist / 'FoxLogin'}",
             f"/DOutputDir={DIST}", PKG / "windows" / "foxlogin.iss"])
        return DIST / f"FoxLogin-{version()}-windows-x64-setup.exe"
    print("Inno Setup not found: producing a .zip instead", flush=True)
    return Path(shutil.make_archive(str(DIST / f"FoxLogin-{version()}-windows-x64"), "zip", dist, "FoxLogin"))


def linux_installer(dist: Path, arch: str) -> Path:
    DIST.mkdir(exist_ok=True)
    base = f"FoxLogin-{version()}-linux-{arch}"
    tgz = DIST / f"{base}.tar.gz"
    with tarfile.open(tgz, "w:gz") as t:
        t.add(dist / "FoxLogin", arcname="FoxLogin")
    tool = shutil.which("appimagetool")
    if not tool:
        print("appimagetool not found: only the .tar.gz was produced", flush=True)
        return tgz
    appdir = dist / "FoxLogin.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(dist / "FoxLogin", appdir / "usr" / "lib" / "foxlogin", symlinks=True)
    shutil.copy(PKG / "linux" / "foxlogin.desktop", appdir / "foxlogin.desktop")
    shutil.copy(PKG / "assets" / "icon.png", appdir / "foxlogin.png")
    apprun = appdir / "AppRun"
    apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                      'exec "$HERE/usr/lib/foxlogin/FoxLogin" "$@"\n')
    apprun.chmod(0o755)
    out = DIST / f"{base}.AppImage"
    run([tool, appdir, out], env=dict(os.environ, ARCH={"arm64": "aarch64"}.get(arch, arch)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default=host_arch(), choices=["arm64", "x86_64"])
    ap.add_argument("--no-installer", action="store_true", help="stop after PyInstaller")
    a = ap.parse_args()
    env = Env(a.arch)
    env.create()
    dist = pyinstaller(env)
    if a.no_installer:
        print("Built:", dist)
        return
    if sys.platform == "darwin":
        out = mac_installer(dist, a.arch)
    elif os.name == "nt":
        out = windows_installer(dist)
    else:
        out = linux_installer(dist, a.arch)
    print("\nInstaller:", out)


if __name__ == "__main__":
    main()
