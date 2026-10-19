# PyInstaller spec for FoxLogin. Run through packaging/build.py, which sets
# FOXLOGIN_ARCH (macOS: arm64 | x86_64) and the version.
# -*- mode: python -*-
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
ASSETS = ROOT / "packaging" / "assets"
VERSION = os.environ.get("FOXLOGIN_VERSION", "1.0.0")
ARCH = os.environ.get("FOXLOGIN_ARCH") or None

datas = [(str(ROOT / "app" / "static"), "app/static")]
binaries = []
hiddenimports = ["app.server", "app.runner", "app.desktop", "app.core"]
hiddenimports += collect_submodules("uvicorn")

# Packages that ship data files (fingerprint models, locales, the Playwright
# Node driver, ...) and import submodules dynamically.
for pkg in ("camoufox", "fpgen", "playwright", "language_tags", "ua_parser", "browserforge",
            "maxminddb", "webview", "screeninfo", "orjson", "rich", "rich_click"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

excludes = ["tkinter", "PySide6", "PyQt5", "matplotlib", "IPython", "pytest"]
if sys.platform != "linux":
    excludes += ["PyQt6", "qtpy", "webview.platforms.qt"]   # Qt is the Linux window backend only
if sys.platform != "win32":
    excludes += ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr", "pythonnet"]

a = Analysis(
    [str(ROOT / "foxlogin.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = {"darwin": "icon.icns", "win32": "icon.ico"}.get(sys.platform, "icon.png")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FoxLogin",
    console=False,          # windowed: no terminal window on Windows/macOS
    disable_windowed_traceback=False,
    target_arch=ARCH,
    icon=str(ASSETS / icon),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FoxLogin")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="FoxLogin.app",
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="app.foxlogin.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "FoxLogin",
            "CFBundleDisplayName": "FoxLogin",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            # Profiles may use the camera/mic (WebRTC sites); macOS asks the user once
            "NSCameraUsageDescription": "Browser profiles can use the camera when a website asks.",
            "NSMicrophoneUsageDescription": "Browser profiles can use the microphone when a website asks.",
        },
    )
