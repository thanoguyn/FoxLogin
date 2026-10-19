"""Runs one profile's browser: `python -m app.runner <profile_id>`.

The server starts one of these per profile; the profile is "running" while the
process lives. Closing the last browser window (or SIGTERM from Stop) saves the
cookie summary and exits.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import warnings
from collections import Counter

warnings.filterwarnings("ignore")

from app import core  # noqa: E402

core.hide_dock_icon()  # before camoufox touches AppKit

from camoufox.sync_api import Camoufox  # noqa: E402

PROBE = """() => {
  let gl = null, vendor = null, renderer = null;
  try {
    gl = document.createElement('canvas').getContext('webgl');
    const d = gl && gl.getExtension('WEBGL_debug_renderer_info');
    if (d) { vendor = gl.getParameter(d.UNMASKED_VENDOR_WEBGL); renderer = gl.getParameter(d.UNMASKED_RENDERER_WEBGL); }
  } catch (e) {}
  return {
    userAgent: navigator.userAgent, platform: navigator.platform,
    threads: navigator.hardwareConcurrency, languages: navigator.languages.join(','),
    screen: screen.width + 'x' + screen.height,
    window: outerWidth + 'x' + outerHeight,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    webglVendor: vendor, webglRenderer: renderer,
  };
}"""

stop = False


def _on_term(*_):
    global stop
    stop = True


def save_cookies(pid: str, ctx) -> None:
    try:
        cookies = ctx.cookies()
    except Exception:
        return
    counts = Counter(c["domain"].lstrip(".") for c in cookies)
    path = core._pdir(pid) / "cookies_summary.json"
    core._write_json(path, {"total": len(cookies), "domains": counts.most_common(20)})


def main(pid: str, debug_port: int = 0, headless: bool = False) -> None:
    p = core.get_profile(pid)
    if p is None:
        sys.exit(f"profile {pid} not found")
    stop_flag = core._pdir(pid) / "stop.flag"   # Stop on Windows, where SIGTERM can't be caught
    stop_flag.unlink(missing_ok=True)
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    core.install_dock_hook()
    label = core.dock_label(p)
    os.environ["FOXCLI_DOCK_BADGE"] = label
    os.environ.pop("FOXCLI_DOCK_TEXT", None)
    kw, loc = core.launch_kwargs(p, headless=headless, debug_port=debug_port or None)
    exe = core.dock_app(p)     # private copy of the browser: Google search, badge in its Dock icon
    if exe:
        kw.pop("browser", None)
        kw["executable_path"] = exe
    elif label:
        os.environ["FOXCLI_DOCK_TEXT"] = "1"   # fall back to the Dock badge text
    udir = core._pdir(pid) / "userdata"
    udir.mkdir(exist_ok=True)
    with Camoufox(persistent_context=True, user_data_dir=str(udir), **kw) as ctx:
        imp = core._pdir(pid) / "cookies_import.json"
        if imp.exists():
            try:
                ctx.add_cookies(json.loads(imp.read_text()))
            finally:
                imp.unlink(missing_ok=True)

        core._write_json(core._pdir(pid) / "runtime.json", {
            "pid": os.getpid(), "port": debug_port or None, "started_at": time.time(), "headless": headless,
        })
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            applied = page.evaluate(PROBE)
            applied["at"] = time.time()
            if loc:
                applied.update(ip=loc["ip"], country=loc["country"])
            core._write_json(core._pdir(pid) / "applied.json", applied)
        except Exception as e:  # never block the launch on the probe
            print("probe failed:", e, file=sys.stderr)
        if p.get("start_url"):
            try:
                page.goto(p["start_url"], timeout=60000)
            except Exception as e:
                print("start url failed:", e, file=sys.stderr)

        closed = []
        ctx.on("close", lambda *_: closed.append(1))
        last_save = time.time()
        while not stop and not closed and not stop_flag.exists():
            try:
                if not ctx.pages:
                    break
                ctx.pages[0].wait_for_timeout(500)
            except Exception:
                break
            if time.time() - last_save > 30:
                save_cookies(pid, ctx)
                last_save = time.time()
        if not closed:
            save_cookies(pid, ctx)


def cli(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="runner")
    ap.add_argument("pid")
    ap.add_argument("--port", type=int, default=0, help="WebDriver BiDi port for automation")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(argv)
    try:
        main(a.pid, a.port, a.headless)
    finally:
        (core._pdir(a.pid) / "runtime.json").unlink(missing_ok=True)
        (core._pdir(a.pid) / "stop.flag").unlink(missing_ok=True)


if __name__ == "__main__":
    cli()
