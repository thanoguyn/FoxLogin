# PyInstaller spec for the Python backend of the Tauri app. Run through
# packaging/tauri/build.py. Produces a one-dir build (fast start, no
# re-extraction for every profile runner) that Tauri ships as a resource.
# -*- mode: python -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent.parent

datas = [(str(ROOT / "app" / "static"), "app/static")]
binaries = []
hiddenimports = ["app.server", "app.runner", "app.core"]
hiddenimports += collect_submodules("uvicorn")

# Packages that ship data files (fingerprint models, locales, the Playwright
# Node driver, ...) and import submodules dynamically.
for pkg in ("camoufox", "fpgen", "playwright", "language_tags", "ua_parser", "browserforge",
            "maxminddb", "screeninfo", "orjson", "rich", "rich_click"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(Path(SPECPATH) / "backend.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6", "PyQt5", "PyQt6", "webview", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="foxlogin-backend",
    console=sys.platform != "win32",   # Windows: no console window for the server or runners
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="foxlogin-backend")
