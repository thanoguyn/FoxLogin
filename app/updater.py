"""FoxLogin's own updates, from the GitHub Releases that CI publishes.

    check()   the latest release and whether it is newer than this copy
    start()   download its installer for this platform in the background, then
              install it and quit; the update is picked by the server, never
              by the caller, so a web page posting to 127.0.0.1 cannot choose it

How an update is applied depends on how this copy was installed:
    auto   Windows installers and Linux AppImages: a detached helper waits for
           the app to exit, installs, and starts the new version
    open   macOS: the .dmg is saved to Downloads and opened for the user to
           drag into Applications (the running app is quit so Finder can replace it)
    link   from source, tar.gz / .deb / .msi installs, or no matching file:
           the release page only
"""
from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app import core

REPO = "thanoguyn/FoxLogin"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_OK = 6 * 3600     # GitHub allows 60 unauthenticated calls an hour per IP
CACHE_FAIL = 30 * 60
UPDATES = core.DATA / "updates"

_cache: Dict[str, Any] = {"at": 0.0, "info": None}
_lock = threading.Lock()
# Download / install progress, shown by the UI's update banner
job: Dict[str, Any] = {"state": "idle"}   # idle | downloading | installing | failed


# ------------------------------------------------------------------ this copy

def shell() -> str:
    """"pywebview" or "tauri" for the packaged apps (their entry points say
    which), "source" when run from a checkout."""
    if not core.FROZEN:
        return "source"
    return os.environ.get("FOXLOGIN_SHELL", "pywebview")


def _arm() -> bool:
    return platform.machine().lower() in ("arm64", "aarch64")


def asset_name(version: str, sh: str, os_name: str, arm: bool) -> Optional[str]:
    """The release file that installs this kind of copy (see the release job
    in .github/workflows/build.yml for the names)."""
    if sh == "pywebview":
        return {
            "windows": f"FoxLogin-{version}-windows-x64-setup.exe",
            "macos": f"FoxLogin-{version}-macos-{'arm64' if arm else 'x86_64'}.dmg",
            "linux": f"FoxLogin-{version}-linux-{'arm64' if arm else 'x86_64'}.AppImage",
        }[os_name]
    if sh == "tauri":
        return {
            "windows": f"FoxLogin-Tauri_{version}_x64-setup.exe",
            "macos": f"FoxLogin-Tauri_{version}_{'aarch64' if arm else 'x64'}.dmg",
            "linux": None if arm else f"FoxLogin-Tauri_{version}_amd64.AppImage",
        }[os_name]
    return None


def _shell_exe() -> Optional[str]:
    """The executable to start again after the update: the Tauri shell owns
    the window (this backend is its child); otherwise this process."""
    if shell() != "tauri":
        return sys.executable
    import psutil

    try:
        return psutil.Process(int(os.environ["FOXLOGIN_PARENT_PID"])).exe()
    except Exception:
        return None


def install_mode(sh: str, os_name: str) -> str:
    if sh == "source":
        return "link"
    if os_name == "macos":
        return "open"
    if os_name == "windows":
        if sh == "tauri":
            # Only the NSIS install can be updated by the NSIS installer; an
            # .msi install would end up as a second copy elsewhere
            exe = _shell_exe()
            if not exe or not (Path(exe).parent / "uninstall.exe").exists():
                return "link"
        return "auto"
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.access(Path(appimage).parent, os.W_OK):
        return "auto"
    return "link"


# --------------------------------------------------------------------- check

def _fetch_latest() -> Dict[str, Any]:
    import requests

    r = requests.get(API, timeout=8, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"FoxLogin/{core.VERSION}"})
    r.raise_for_status()
    return r.json()


def check(force: bool = False) -> Dict[str, Any]:
    """The latest release, cached. Offline, rate-limited or no release yet all
    read as "no update" with an error the UI can show on a manual check."""
    with _lock:
        info, age = _cache["info"], time.time() - _cache["at"]
        if info is not None and not force and age < (CACHE_FAIL if info.get("error") else CACHE_OK):
            return dict(info, job=dict(job))
        try:
            rel = _fetch_latest()
            latest = rel["tag_name"].lstrip("v")
            os_name = core.host_os()
            name = asset_name(latest, shell(), os_name, _arm())
            asset = next((a for a in rel.get("assets", []) if a["name"] == name), None)
            info = {
                "current": core.VERSION, "latest": latest,
                "newer": core.version_key(latest) > core.version_key(core.VERSION),
                "url": rel.get("html_url") or f"https://github.com/{REPO}/releases/latest",
                "published": rel.get("published_at"), "notes": (rel.get("body") or "")[:4000],
                "asset": asset and {"name": asset["name"], "size": asset["size"],
                                    "url": asset["browser_download_url"], "digest": asset.get("digest")},
                "mode": install_mode(shell(), os_name) if asset else "link",
                "shell": shell(), "os": os_name,
            }
        except Exception as e:
            info = {"current": core.VERSION, "latest": None, "newer": False,
                    "url": f"https://github.com/{REPO}/releases/latest", "error": str(e)[:200]}
        _cache.update(at=time.time(), info=info)
        return dict(info, job=dict(job))


# ------------------------------------------------------------------ download

def _download(asset: Dict[str, Any], dest: Path) -> None:
    import requests

    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    job.update(done=0, total=asset["size"])
    with requests.get(asset["url"], stream=True, timeout=30,
                      headers={"User-Agent": f"FoxLogin/{core.VERSION}"}) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                sha.update(chunk)
                job["done"] += len(chunk)
    if job["done"] != asset["size"]:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Incomplete download ({job['done']} of {asset['size']} bytes)")
    want = (asset.get("digest") or "").removeprefix("sha256:")
    if want and sha.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise RuntimeError("The download does not match the release checksum")
    part.replace(dest)


def _target(info: Dict[str, Any]) -> Path:
    name = info["asset"]["name"]
    if info["mode"] == "open":   # the user installs it from Finder: keep it findable
        from platformdirs import user_downloads_dir

        return Path(user_downloads_dir()) / name
    if info["os"] == "linux":    # same folder, so the swap is a rename
        appimage = Path(os.environ["APPIMAGE"])
        return appimage.with_name("." + appimage.name + ".new")
    return UPDATES / name


# ------------------------------------------------------------------- install

def _helper_env() -> Dict[str, str]:
    """Environment for the relaunched app: none of this copy's PyInstaller or
    AppImage mount paths, which are gone once it exits."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    for k in ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "FOXLOGIN_PARENT_PID", "FOXLOGIN_SHELL", "FOXCLI_PORT"):
        env.pop(k, None)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def _app_pids() -> list:
    pids = [os.getpid()]
    if shell() == "tauri" and os.environ.get("FOXLOGIN_PARENT_PID"):
        pids.append(int(os.environ["FOXLOGIN_PARENT_PID"]))
    return pids


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _launch_windows(installer: Path, exe: str) -> None:
    # Inno Setup (pywebview) and Tauri's NSIS installer both skip their
    # "launch the app" step when silent, so the helper starts it afterwards
    args = "'/S'" if shell() == "tauri" else "'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'"
    script = UPDATES / "update.ps1"
    script.write_text("\r\n".join([
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"Wait-Process -Id {','.join(map(str, _app_pids()))} -Timeout 120",
        f"$p = Start-Process -FilePath {_ps_quote(str(installer))} -ArgumentList {args} -Wait -PassThru",
        f"Start-Process -FilePath {_ps_quote(exe)}",
        f"if ($p.ExitCode -eq 0) {{ Remove-Item -LiteralPath {_ps_quote(str(installer))} }}",
    ]), encoding="utf-8-sig")   # Windows PowerShell reads a BOM-less script as ANSI
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
         "-File", str(script)],
        env=_helper_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, **core.popen_kwargs())


def _launch_linux(new: Path) -> None:
    appimage = os.environ["APPIMAGE"]
    new.chmod(0o755)
    # The running copy keeps its mount of the old file, so swapping it now is safe
    new.replace(appimage)
    wait = " ".join(f'while kill -0 {p} 2>/dev/null; do sleep 0.3; done;' for p in _app_pids())
    subprocess.Popen(["/bin/sh", "-c", f"{wait} exec {shlex.quote(appimage)}"],
                     env=_helper_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)


def _quit() -> None:
    """Close the whole app: the Tauri shell too, or its window stays open on a
    dead backend and its files stay locked. Running profiles are separate."""
    time.sleep(1.5)   # let the UI receive the "installing" state first
    if shell() == "tauri" and os.environ.get("FOXLOGIN_PARENT_PID"):
        import psutil

        try:
            psutil.Process(int(os.environ["FOXLOGIN_PARENT_PID"])).terminate()
        except Exception:
            pass
    os._exit(0)


def _run(info: Dict[str, Any], before_quit: Callable[[], None]) -> None:
    try:
        dest = _target(info)
        _download(info["asset"], dest)
        job.update(state="installing", path=str(dest))
        if info["mode"] == "open":
            subprocess.Popen(["open", str(dest)])
        elif info["os"] == "windows":
            exe = _shell_exe()
            if not exe:
                raise RuntimeError("Cannot find the FoxLogin program to start after the update")
            _launch_windows(dest, exe)
        else:
            _launch_linux(dest)
        before_quit()
        _quit()
    except Exception as e:
        job.update(state="failed", error=str(e)[:300])


def start(before_quit: Callable[[], None]) -> Dict[str, Any]:
    """Download and install the latest release (see the module docstring)."""
    if job["state"] in ("downloading", "installing"):
        return dict(job)
    info = check()
    if not info.get("newer"):
        raise ValueError("FoxLogin is up to date")
    if info["mode"] == "link":
        raise ValueError("This copy of FoxLogin cannot update itself; download it from the release page")
    UPDATES.mkdir(parents=True, exist_ok=True)
    for old in UPDATES.iterdir():   # leftovers of earlier updates
        old.unlink(missing_ok=True)
    job.clear()
    job.update(state="downloading", version=info["latest"], mode=info["mode"], done=0, total=info["asset"]["size"])
    threading.Thread(target=_run, args=(info, before_quit), daemon=True).start()
    return dict(job)
