"""FastAPI backend + static UI for FoxLogin.

Two API surfaces share the same handlers:
  /api/...      used by the web UI
  /api/v1/...   documented automation API (GoLogin-style), plus the GoLogin
                compatible  POST /browser/start-profile  and  /browser/stop-profile
"""
from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import core

STATIC = Path(__file__).parent / "static"
LOGS = core.DATA / "logs"
LOGS.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("FOXCLI_PORT", 8765))

app = FastAPI(title="FoxLogin")
procs: Dict[str, subprocess.Popen] = {}
ports: Dict[str, int] = {}   # automation (WebDriver BiDi) port per running profile
errors: Dict[str, str] = {}  # last launch failure per profile, shown once by the UI
jobs: Dict[str, Dict[str, Any]] = {}  # browser install / sync jobs
pending: Dict[str, str] = {}  # profile -> browser download job it starts after (first Run)


# ------------------------------------------------------------------------ state

def _adopted_pid(pid: str) -> Optional[int]:
    """A runner left over from a previous server process (server restarted
    while the browser stayed open): its runtime.json names a live process."""
    rt = core._read_json(core._pdir(pid) / "runtime.json")
    if not rt or not rt.get("pid"):
        return None
    if not core.runner_alive(rt["pid"], pid):
        return None
    if rt.get("port"):
        ports[pid] = rt["port"]
    return rt["pid"]


def _state(pid: str) -> str:
    if pid in pending:
        return _pending_state(pid)
    pr = procs.get(pid)
    if pr is None:
        return "running" if _adopted_pid(pid) else "ready"
    if pr.poll() is None:
        return "running"
    procs.pop(pid, None)
    ports.pop(pid, None)
    if pr.returncode not in (0, -15):
        errors[pid] = _last_error(pid)
    return "ready"


def _last_error(pid: str) -> str:
    try:
        lines = (LOGS / f"{pid}.log").read_text(errors="replace").strip().splitlines()
    except OSError:
        return "Browser exited unexpectedly"
    msg = next((l for l in reversed(lines) if l.strip() and not l.startswith(" ")), "")
    if "public IP" in msg or "ProxyError" in msg or "InvalidIP" in msg or "Proxy" in msg:
        return "Could not reach the internet through the proxy: " + msg[-200:]
    return msg[-300:] or "Browser exited unexpectedly"


def _with_state(p: Dict[str, Any]) -> Dict[str, Any]:
    p["state"] = _state(p["id"])
    p["port"] = ports.get(p["id"]) if p["state"] == "running" else None
    return p


def _profile_or_404(pid: str) -> Dict[str, Any]:
    p = core.get_profile(pid)
    if not p:
        raise HTTPException(404, f"Profile {pid} not found")
    return p


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _run_info(pid: str) -> Dict[str, Any]:
    port = ports.get(pid)
    info = {"status": "success", "profileId": pid, "state": _state(pid), "port": port,
            "wsUrl": None, "wsEndpoint": None}
    if port:
        info["wsUrl"] = f"ws://127.0.0.1:{PORT}/ws/{pid}"          # Puppeteer: protocol 'webDriverBiDi'
        info["wsEndpoint"] = f"ws://127.0.0.1:{port}/session"      # raw WebDriver BiDi (Selenium etc.)
    return info


def _spawn(pid: str, automation: bool = False, headless: bool = False) -> int:
    """Start the profile's runner; returns its automation port (0 without)."""
    cmd = core.self_cmd("runner", pid)
    port = _free_port() if automation else 0
    if port:
        cmd += ["--port", str(port)]
        ports[pid] = port
    if headless:
        cmd.append("--headless")
    log = open(LOGS / f"{pid}.log", "wb")
    procs[pid] = subprocess.Popen(cmd, cwd=str(core.DATA if core.FROZEN else core.ROOT), stdout=log, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, **core.popen_kwargs())
    return port


def _pending_state(pid: str) -> str:
    """A profile waiting for the browser download: starts once it is in."""
    name = pending.get(pid)
    if name and _job_state(name) == "running":
        return "downloading"
    if pending.pop(pid, None) is None:  # another request (thread) got here first
        return _state(pid)
    if not core.browser_installed():
        errors[pid] = "Could not download the Camoufox browser: " + (_job_log(name).strip().splitlines() or ["unknown error"])[-1][-200:]
        return "ready"
    _spawn(pid)
    return "running"


def _download_job() -> str:
    """The job bringing in a first browser: one already running, else the newest stable build."""
    if dl := _download_info():
        return dl["job"]
    stable = [v for v in core.browser_versions()["available"] if v["repo"] == "official" and not v["prerelease"]]
    if not stable:  # no repo list yet: the build this camoufox library pairs with
        return _job("setup", ["fetch"])["job"]
    v = max(stable, key=lambda v: core.version_key(v["version"]))
    spec = f"official/{v['version']}"
    return _job(f"install {spec}", ["fetch", spec])["job"]


async def start_profile(pid: str, automation: bool = False, headless: bool = False,
                        wait: bool = False) -> Dict[str, Any]:
    _profile_or_404(pid)
    state = _state(pid)
    if state == "running":
        if automation and not ports.get(pid):
            raise HTTPException(409, "Profile is running without automation; stop it first")
        return _run_info(pid)
    if state == "downloading" or not core.browser_installed():
        job = _download_job()
        if wait or automation:
            raise HTTPException(503, "The Camoufox browser is still downloading (first run); try again when it finishes")
        pending[pid] = job
        return _run_info(pid)
    port = _spawn(pid, automation, headless)
    if wait or port:
        deadline = time.time() + 90
        while time.time() < deadline:
            if _state(pid) != "running":
                raise HTTPException(500, errors.pop(pid, "Browser exited during start"))
            if port and _port_open(port):
                break
            if not port and (core._pdir(pid) / "runtime.json").exists():
                break
            await asyncio.sleep(0.4)
        else:
            stop_profile(pid)
            raise HTTPException(504, "Browser did not start in time")
    return _run_info(pid)


def stop_profile(pid: str) -> Dict[str, Any]:
    pending.pop(pid, None)  # waiting for the download: just don't start (the download goes on)
    pr = procs.get(pid)
    if pr is not None and pr.poll() is None:
        core.stop_runner(pr.pid, pid)
        pr.wait()
    elif pr is None and (opid := _adopted_pid(pid)):
        core.stop_runner(opid, pid)
    procs.pop(pid, None)
    ports.pop(pid, None)
    return {"status": "success", "profileId": pid, "state": "ready"}


# ----------------------------------------------------------------- auth (API v1)

@app.middleware("http")
async def api_token(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1/") or path.startswith("/browser/"):
        token = core.get_settings().get("api_token")
        if token:
            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip() \
                or request.query_params.get("token", "")
            if given != token:
                return JSONResponse({"detail": "Invalid API token"}, status_code=401)
    return await call_next(request)


# ------------------------------------------------------------------------ pages

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/fptest")
def fptest():
    return FileResponse(STATIC / "fptest.html")


@app.get("/api/app")
def app_info():
    """Lets a second launch of the desktop app find this one."""
    return {"app": "FoxLogin", "version": core.VERSION, "window": callable(getattr(app.state, "focus", None))}


@app.post("/api/app/focus")
def app_focus():
    focus = getattr(app.state, "focus", None)
    if callable(focus):
        focus()
    return {"window": callable(focus)}


@app.get("/api/meta")
def meta():
    return {
        "resolutions": core.RESOLUTIONS,
        "gpus": {o: core.coherent_gpus(o) for o in core.OS_KEYS},
        "hostOs": core.host_os(),
        "port": PORT,
        "version": core.VERSION,
        "dataDir": str(core.DATA),
    }


# --------------------------------------------------------------------- settings

@app.get("/api/settings")
def get_settings():
    return core.get_settings()


@app.patch("/api/settings")
def patch_settings(changes: Dict[str, Any] = Body(...)):
    return core.save_settings(changes)


@app.post("/api/settings/reset")
def reset_settings():
    """Back to the recommended defaults (browser and API token are kept)."""
    return core.save_settings({"reset_defaults": True})


@app.get("/api/random-device")
def random_device(os: str = "macos"):
    if os not in core.OS_KEYS:
        raise HTTPException(400, "Unknown OS")
    dev = core.random_device(os)
    gpus = core.coherent_gpus(os)
    import random as _r
    vendor, renderer = _r.choice(gpus)
    dev["webgl_info"] = {"mode": "masked", "vendor": vendor, "renderer": renderer}
    return dev


# ---------------------------------------------------------------------- folders

@app.get("/api/folders")
def folders():
    return core.list_folders()


@app.post("/api/folders")
def add_folder(data: Dict[str, Any] = Body(...)):
    name = str(data.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Folder name required")
    return core.add_folder(name)


# --------------------------------------------------------------------- profiles

@app.get("/api/profiles")
@app.get("/api/v1/profiles")
def profiles(folder: Optional[str] = None, q: Optional[str] = None):
    items = [_with_state(p) for p in core.list_profiles()]
    if folder is not None:
        items = [p for p in items if p.get("folder") == folder]
    if q:
        items = [p for p in items if q.lower() in (p["name"] + " " + p["notes"]).lower()]
    return items


@app.get("/api/profiles/{pid}")
@app.get("/api/v1/profiles/{pid}")
def profile(pid: str):
    return _with_state(_profile_or_404(pid))


@app.post("/api/profiles")
@app.post("/api/v1/profiles")
def create(data: Dict[str, Any] = Body(default={})):
    if isinstance(data.get("proxy"), str):
        data["proxy"] = core.parse_proxy(data["proxy"]) or {"type": "none"}
    return _with_state(core.create_profile(data))


@app.post("/api/profiles/bulk")
def create_bulk(data: Dict[str, Any] = Body(...)):
    count = max(1, min(int(data.get("count", 1)), 1000))
    template = data.get("template") or {}
    prefix = (data.get("prefix") or "").strip()
    randomize = data.get("randomize", True)
    out = []
    for i in range(count):
        d = dict(template)
        if prefix:
            d["name"] = f"{prefix} {i + 1}"
        if randomize:
            dev = core.random_device(d.get("os") or core.get_settings()["defaults"]["os"])
            d.update(device=dev["device"], resolution=dev["resolution"], media_devices=dev["media_devices"])
        out.append(core.create_profile(d)["id"])
    return {"created": out}


@app.post("/api/profiles/import")
@app.post("/api/v1/profiles/import")
def import_profiles(data: Dict[str, Any] = Body(...)):
    return core.import_profiles(data.get("text", ""), data.get("template") or {})


@app.patch("/api/profiles/{pid}")
@app.patch("/api/v1/profiles/{pid}")
def update(pid: str, changes: Dict[str, Any] = Body(...)):
    if isinstance(changes.get("proxy"), str):
        changes["proxy"] = core.parse_proxy(changes["proxy"]) or {"type": "none"}
    if _state(pid) == "running" and any(k not in ("name", "notes", "folder", "pinned", "dock_badge") for k in changes):
        raise HTTPException(409, "Stop the profile before changing its fingerprint settings")
    try:
        return _with_state(core.update_profile(pid, changes))
    except KeyError:
        raise HTTPException(404)


@app.post("/api/profiles/{pid}/refresh")
def refresh(pid: str):
    p = _profile_or_404(pid)
    if _state(pid) == "running":
        raise HTTPException(409, "Stop the profile first")
    core.new_fingerprint(p)
    core.save_profile(p)
    return _with_state(core.get_profile(pid))


@app.post("/api/profiles/{pid}/reset")
@app.post("/api/v1/profiles/{pid}/reset")
def reset_profile(pid: str):
    _profile_or_404(pid)
    if _state(pid) == "running":
        raise HTTPException(409, "Stop the profile first")
    return _with_state(core.reset_profile(pid))


@app.post("/api/profiles/{pid}/randomize")
@app.post("/api/v1/profiles/{pid}/randomize")
def randomize(pid: str):
    _profile_or_404(pid)
    if _state(pid) == "running":
        raise HTTPException(409, "Stop the profile first")
    return _with_state(core.randomize_profile(pid))


@app.get("/api/profiles/{pid}/gpus")
def profile_gpus(pid: str):
    p = _profile_or_404(pid)
    return core.coherent_gpus(p["os"], core.load_fingerprint(pid))


@app.post("/api/profiles/{pid}/clone")
def clone(pid: str):
    return _with_state(core.clone_profile(pid))


@app.post("/api/profiles/delete")
def delete(ids: List[str] = Body(...)):
    for pid in ids:
        stop_profile(pid)
        core.delete_profile(pid)
    return {"ok": True}


@app.delete("/api/v1/profiles/{pid}")
def delete_one(pid: str):
    _profile_or_404(pid)
    stop_profile(pid)
    core.delete_profile(pid)
    return {"status": "success"}


@app.get("/api/profiles/{pid}/preview")
def preview(pid: str):
    p = _profile_or_404(pid)
    try:
        return core.preview(p)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/profiles/{pid}/run")
async def run(pid: str):
    return await start_profile(pid)


@app.post("/api/profiles/{pid}/stop")
def stop(pid: str):
    return stop_profile(pid)


@app.post("/api/profiles/{pid}/cookies")
@app.post("/api/v1/profiles/{pid}/cookies")
def import_cookies(pid: str, cookies: List[Dict[str, Any]] = Body(...)):
    """Queue cookies (EditThisCookie / Playwright JSON) for the next launch."""
    norm = []
    for c in cookies:
        item = {
            "name": c["name"], "value": str(c.get("value", "")),
            "domain": c.get("domain") or c.get("host"), "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)), "httpOnly": bool(c.get("httpOnly", False)),
        }
        exp = c.get("expires", c.get("expirationDate"))
        if exp and float(exp) > 0:
            # Firefox drops cookies that outlive its 400-day cap instead of clamping them
            item["expires"] = min(float(exp), time.time() + 399 * 86400)
        ss = str(c.get("sameSite", "")).lower()
        item["sameSite"] = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None"}.get(ss, "Lax")
        norm.append(item)
    core._write_json(core._pdir(pid) / "cookies_import.json", norm)
    return {"queued": len(norm)}


@app.get("/api/profiles/{pid}/cookies/export")
@app.get("/api/v1/profiles/{pid}/cookies")
def export_cookies(pid: str):
    """Cookies saved in the profile, in Cookie-Editor / Playwright JSON."""
    import shutil as _sh
    import sqlite3
    import tempfile

    _profile_or_404(pid)
    db = core._pdir(pid) / "userdata" / "cookies.sqlite"
    if not db.exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:   # copy: the browser may hold a lock
        for suffix in ("", "-wal"):
            if Path(str(db) + suffix).exists():
                _sh.copy(str(db) + suffix, Path(tmp) / ("cookies.sqlite" + suffix))
        con = sqlite3.connect(Path(tmp) / "cookies.sqlite")
        rows = con.execute("SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite FROM moz_cookies").fetchall()
        con.close()
    same = {0: "no_restriction", 1: "lax", 2: "strict"}
    return [{"name": n, "value": v, "domain": h, "path": pa, "expirationDate": (e / 1000 if e > 1e11 else e),
             "secure": bool(se), "httpOnly": bool(ho), "sameSite": same.get(ss, "lax")}
            for n, v, h, pa, e, se, ho, ss in rows]


@app.get("/run/{pid}")
async def run_link(pid: str):
    """The "Run" link: open it in any browser to start the profile."""
    from fastapi.responses import HTMLResponse

    p = _profile_or_404(pid)
    what = "Downloading the Camoufox browser first; it opens when that finishes" \
        if (await start_profile(pid))["state"] == "downloading" else "Started"
    return HTMLResponse(f"<p style='font:15px system-ui;padding:24px'>{what}: <b>{p['name']}</b>. You can close this tab.</p>")


@app.get("/api/states")
def states():
    ids = set(procs) | set(pending) | {d.name for d in core.PROFILES.iterdir() if (d / "runtime.json").exists()}
    out = {pid: _state(pid) for pid in ids}
    return {"states": out, "ports": dict(ports), "errors": {pid: errors.pop(pid) for pid in list(errors)},
            "download": _download_info()}


# -------------------------------------------------------------- automation API

@app.post("/api/v1/profiles/{pid}/start")
async def v1_start(pid: str, automation: bool = True, headless: bool = False):
    """Start a profile and return its WebDriver BiDi endpoint for Puppeteer."""
    return await start_profile(pid, automation=automation, headless=headless, wait=True)


@app.post("/api/v1/profiles/{pid}/stop")
def v1_stop(pid: str):
    return stop_profile(pid)


@app.get("/api/v1/running")
def v1_running():
    ids = set(procs) | {d.name for d in core.PROFILES.iterdir() if (d / "runtime.json").exists()}
    return [_run_info(pid) for pid in ids if _state(pid) == "running"]


@app.post("/browser/start-profile")
async def gologin_start(data: Dict[str, Any] = Body(...)):
    """GoLogin local API compatible: {"profileId": "..."} -> {"status", "wsUrl"}."""
    pid = data.get("profileId") or data.get("profile_id")
    return await start_profile(pid, automation=True, headless=bool(data.get("headless")), wait=True)


@app.post("/browser/stop-profile")
def gologin_stop(data: Dict[str, Any] = Body(...)):
    return stop_profile(data.get("profileId") or data.get("profile_id"))


@app.websocket("/ws/{pid}")
async def bidi_proxy(ws: WebSocket, pid: str):
    """Relay to the profile's WebDriver BiDi socket.

    Puppeteer only drives BiDi browsers whose session reports a browserName
    containing "firefox"; Camoufox reports its own name, so the relay rewrites
    that one field and passes everything else through untouched.
    """
    import websockets

    port = ports.get(pid)
    if not port or _state(pid) != "running":
        await ws.close(code=4404)
        return
    await ws.accept()
    async with websockets.connect(f"ws://127.0.0.1:{port}/session", max_size=None) as up:
        async def down_to_up():
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    await up.close()
                    return
                await up.send(msg.get("text") if msg.get("text") is not None else msg.get("bytes"))

        async def up_to_down():
            async for m in up:
                if isinstance(m, str):
                    if '"browserName"' in m:
                        m = re.sub(r'"browserName":"[^"]*"', '"browserName":"firefox"', m)
                    await ws.send_text(m)
                else:
                    await ws.send_bytes(m)

        tasks = [asyncio.create_task(down_to_up()), asyncio.create_task(up_to_down())]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in tasks:
            t.cancel()
    try:
        await ws.close()
    except Exception:
        pass


# ----------------------------------------------------------------------- proxies

@app.get("/api/proxies")
@app.get("/api/v1/proxies")
def proxies():
    used: Dict[tuple, int] = {}
    for p in core.list_profiles():
        px = p["proxy"]
        if px.get("type") != "none":
            k = (px.get("host"), str(px.get("port")), px.get("username", ""))
            used[k] = used.get(k, 0) + 1
    out = core.list_proxies()
    for x in out:
        x["profiles"] = used.get((x["host"], str(x["port"]), x.get("username", "")), 0)
    return out


@app.post("/api/proxies/import")
@app.post("/api/v1/proxies/import")
def proxies_import(data: Dict[str, Any] = Body(...)):
    return core.add_proxies(data.get("text", ""), data.get("type") or "http")


@app.post("/api/proxies/parse")
def proxies_parse(data: Dict[str, Any] = Body(...)):
    px = core.parse_proxy(data.get("text", ""), data.get("type") or "http")
    if not px:
        raise HTTPException(400, "Unrecognised proxy format")
    return px


@app.patch("/api/proxies/{xid}")
def proxies_update(xid: str, changes: Dict[str, Any] = Body(...)):
    try:
        return core.update_proxy(xid, changes)
    except KeyError:
        raise HTTPException(404)


@app.post("/api/proxies/delete")
def proxies_delete(ids: List[str] = Body(...)):
    core.delete_proxies(ids)
    return {"ok": True}


@app.post("/api/proxies/check")
async def proxies_check(ids: List[str] = Body(...)):
    items = {x["id"]: x for x in core.list_proxies()}
    sel = [items[i] for i in ids if i in items]
    results = await asyncio.gather(*(asyncio.to_thread(core.check_proxy, x) for x in sel))
    for x, r in zip(sel, results):
        core.update_proxy(x["id"], {"check": r})
    return {x["id"]: r for x, r in zip(sel, results)}


@app.post("/api/proxy/check")
def check_proxy(proxy: Dict[str, Any] = Body(...)):
    if not core.proxy_dict(proxy):
        raise HTTPException(400, "No proxy")
    return core.check_proxy(proxy)


# ---------------------------------------------------------------- browser builds

@app.get("/api/browsers")
def browsers():
    data = core.browser_versions()
    data["jobs"] = {k: {"state": _job_state(k), "log": _job_log(k)[-600:], "progress": _job_progress(k),
                        "started": v["started"]} for k, v in jobs.items()}
    return data


def _job_state(name: str) -> str:
    j = jobs[name]
    pr = j.get("proc")
    if pr is not None and pr.poll() is not None and j["state"] == "running":
        j["state"] = "done" if pr.returncode == 0 else "failed"
    return j["state"]


def _job_raw(name: str) -> str:
    try:
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", Path(jobs[name]["log"]).read_text(errors="replace"))
    except OSError:
        return ""


def _job_log(name: str) -> str:
    """The job's output as plain text: the progress bar redraws collapse to their last state."""
    lines = (([seg for seg in l.split("\r") if seg.strip()] or [""])[-1] for l in _job_raw(name).splitlines())
    return "\n".join(l for l in lines if l.strip())


def _job_progress(name: str) -> Optional[Dict[str, Any]]:
    """The download bar's last "12.3/456.7 MB" reading."""
    m = re.findall(r"([\d.]+)/([\d.]+) ([kMG]?B)\b", _job_raw(name))  # extracting keeps the last (100%) reading
    if not m:
        return None
    done, total, unit = m[-1]
    pct = int(float(done) * 100 / float(total)) if float(total) else 0
    return {"done": float(done), "total": float(total), "unit": unit, "pct": min(pct, 100)}


def _download_info() -> Optional[Dict[str, Any]]:
    """The browser download in progress, for the UI's progress display."""
    for name in list(jobs):
        if (name == "setup" or name.startswith("install ")) and _job_state(name) == "running":
            return {"job": name, "version": name.split("/")[-1] if "/" in name else "",
                    "progress": _job_progress(name), "started": jobs[name]["started"]}
    return None


def _job(name: str, args: List[str]) -> Dict[str, Any]:
    if name in jobs and _job_state(name) == "running":
        raise HTTPException(409, "Already running")
    logf = LOGS / f"job-{re.sub(r'[^a-z0-9.-]', '_', name.lower())}.log"
    env = dict(os.environ, FORCE_COLOR="1", COLUMNS="100")  # rich draws its progress bar into the log
    proc = subprocess.Popen(core.self_cmd("camoufox", *args), stdout=open(logf, "wb"), env=env,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **core.popen_kwargs())
    jobs[name] = {"state": "running", "log": str(logf), "proc": proc, "started": time.time()}
    return {"job": name}


@app.post("/api/browsers/setup")
def browsers_setup():
    """First run: the Camoufox build this camoufox library pairs with, plus GeoIP and addons."""
    return _job("setup", ["fetch"])


@app.post("/api/browsers/sync")
def browsers_sync():
    return _job("sync", ["sync"])


@app.post("/api/browsers/install")
def browsers_install(data: Dict[str, Any] = Body(...)):
    spec = f"{data.get('repo', 'official')}/{data['version']}"
    return _job(f"install {spec}", ["fetch", spec])


@app.post("/api/browsers/default")
def browsers_default(data: Dict[str, Any] = Body(...)):
    return core.save_settings({"browser": data.get("version", "")})


@app.post("/api/browsers/remove")
def browsers_remove(data: Dict[str, Any] = Body(...)):
    from camoufox.multiversion import list_installed, remove_version

    for iv in list_installed():
        if iv.version.full_string == data.get("version") and iv.repo_name == data.get("repo", "official"):
            if iv.is_active:
                raise HTTPException(409, "This is Camoufox's active build; choose another default first")
            remove_version(iv.path)
            if core.get_settings()["browser"] == data.get("version"):
                core.save_settings({"browser": ""})
            return {"ok": True}
    raise HTTPException(404, "Not installed")


@app.on_event("shutdown")
def _shutdown():
    # Open browsers keep running; the next server adopts them via runtime.json.
    for j in jobs.values():
        if j.get("proc") and j["proc"].poll() is None:
            j["proc"].terminate()


app.mount("/static", StaticFiles(directory=STATIC), name="static")
