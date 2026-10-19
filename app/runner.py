"""Runs one profile's browser: `python -m app.runner <profile_id>`.

The server starts one of these per profile; the profile is "running" while the
process lives. Closing the last browser window (or SIGTERM from Stop) saves the
cookie summary and exits.
"""
from __future__ import annotations

import argparse
from concurrent.futures import Future, TimeoutError as FutureTimeout
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import queue
import random
import re
import secrets
import signal
import sys
import threading
import time
import warnings
from collections import Counter
from typing import Any, Dict, Tuple

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

BUTTONS = {0: "left", 1: "middle", 2: "right", "left": "left", "middle": "middle", "right": "right"}
stop = False
main_world = False   # launched with allowMainWorld (human_cursor on)


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


def _pick_page(ctx, spec: Any = None):
    pages = [pg for pg in ctx.pages if not pg.is_closed()]
    if not pages:
        raise ValueError("No open pages")
    if spec is None or spec == "":
        return pages[-1]
    if isinstance(spec, int) or (isinstance(spec, str) and re.fullmatch(r"-?\d+", spec.strip())):
        idx = int(spec)
        if -len(pages) <= idx < len(pages):
            return pages[idx]
        raise ValueError(f"Page index {idx} out of range (0..{len(pages) - 1})")
    s = str(spec)
    for pg in reversed(pages):
        if s in (pg.url or ""):
            return pg
    for pg in reversed(pages):
        try:
            if s in (pg.title() or ""):
                return pg
        except Exception:
            pass
    raise ValueError(f"No page matching {s!r}")


def _selector_box_expr(selector: str) -> str:
    # Main world when allowed: after a BiDi client navigates the page, Juggler's
    # isolated utility world is gone, so Playwright locators and plain evaluate
    # fail. launch_kwargs() allows main-world eval only with human_cursor on.
    return (
        ("mw:" if main_world else "") + "(() => {"
        f" const sel = {json.dumps(selector)};"
        " let el = null;"
        " try { el = document.querySelector(sel); } catch (e) { return JSON.stringify({ error: String(e) }); }"
        " if (!el) return '';"
        " try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}"
        " const r = el.getBoundingClientRect();"
        " if (!r || (r.width === 0 && r.height === 0)) return '';"
        " return JSON.stringify({ x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height });"
        "})()"
    )


def _selector_point(page, selector: str, timeout_s: float = 3.0) -> Tuple[float, float]:
    """A point near the centre of the element, scrolled into view, in viewport pixels."""
    deadline = time.monotonic() + timeout_s
    last_err = None
    expr = _selector_box_expr(selector)
    while True:
        try:
            raw = page.evaluate(expr)
            box = json.loads(raw) if isinstance(raw, str) and raw else None
            if isinstance(box, dict) and "x" in box:
                w, h = float(box.get("w") or 0.0), float(box.get("h") or 0.0)
                jx = random.uniform(-min(4.0, w * 0.15), min(4.0, w * 0.15)) if w > 4 else 0.0
                jy = random.uniform(-min(4.0, h * 0.15), min(4.0, h * 0.15)) if h > 4 else 0.0
                return round(float(box["x"]) + jx, 2), round(float(box["y"]) + jy, 2)
            if isinstance(box, dict) and box.get("error"):
                last_err = box["error"]
                break
        except Exception as e:
            last_err = str(e).splitlines()[0]
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(50)
    hint = "" if main_world else "; selector lookups after BiDi navigation need human_cursor on"
    raise ValueError(f"Element not found or not visible for selector {selector!r}"
                     + (f" ({last_err}{hint})" if last_err else ""))


def _exec_human(ctx, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    page = _pick_page(ctx, data.get("page"))
    if action == "move":
        if "x" not in data or "y" not in data:
            raise ValueError("move requires 'x' and 'y'")
        x, y = float(data["x"]), float(data["y"])
        page.mouse.move(x, y)
        return {"ok": True, "action": "move", "x": x, "y": y}

    if action == "click":
        btn = BUTTONS.get(data.get("button", "left"), "left")
        count = int(data.get("clickCount") or data.get("click_count") or 1)
        delay = float(data["delay"]) if data.get("delay") is not None else float(random.randint(40, 110))
        if data.get("selector"):
            sel = str(data["selector"])
            x, y = _selector_point(page, sel)
            page.mouse.click(x, y, button=btn, click_count=count, delay=delay)
            return {"ok": True, "action": "click", "selector": sel, "x": x, "y": y}
        if data.get("x") is not None and data.get("y") is not None:
            x, y = float(data["x"]), float(data["y"])
            page.mouse.click(x, y, button=btn, click_count=count, delay=delay)
            return {"ok": True, "action": "click", "x": x, "y": y}
        raise ValueError("click requires 'selector' or 'x' and 'y'")

    if action == "scroll":
        if data.get("x") is not None and data.get("y") is not None:
            page.mouse.move(float(data["x"]), float(data["y"]))
        dx = float(data.get("deltaX") or 0)
        dy = float(data.get("deltaY") or 0)
        page.mouse.wheel(dx, dy)
        return {"ok": True, "action": "scroll", "deltaX": dx, "deltaY": dy}

    if action == "type":
        if "text" not in data:
            raise ValueError("type requires 'text'")
        text = str(data.get("text") or "")
        if data.get("selector"):
            sel = str(data["selector"])
            x, y = _selector_point(page, sel)
            page.mouse.click(x, y, delay=float(random.randint(40, 95)))
        if data.get("delay") is not None:
            page.keyboard.type(text, delay=float(data["delay"]))
        else:
            for ch in text:
                page.keyboard.type(ch, delay=float(random.randint(30, 90)))
        return {"ok": True, "action": "type", "length": len(text)}

    if action == "hover":
        if data.get("selector"):
            sel = str(data["selector"])
            x, y = _selector_point(page, sel)
            page.mouse.move(x, y)
            return {"ok": True, "action": "hover", "selector": sel, "x": x, "y": y}
        if data.get("x") is not None and data.get("y") is not None:
            x, y = float(data["x"]), float(data["y"])
            page.mouse.move(x, y)
            return {"ok": True, "action": "hover", "x": x, "y": y}
        raise ValueError("hover requires 'selector' or 'x' and 'y'")

    raise ValueError(f"Unknown action: {action!r}")


def _start_control_server(
    cmd_queue: "queue.Queue[Tuple[str, Dict[str, Any], Future]]", token: str,
) -> Tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            # A custom header, not a query param: pages in the browser can't send it
            # without a CORS preflight, which this server never answers.
            if not hmac.compare_digest(self.headers.get(core.CONTROL_TOKEN_HEADER, ""), token):
                self._reply(403, {"detail": "Invalid control token"})
                return
            action = self.path.strip("/").rsplit("/", 1)[-1]
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
            except ValueError as e:
                self._reply(400, {"detail": f"Invalid JSON: {e}"})
                return
            fut: Future = Future()
            cmd_queue.put((action, body, fut))
            try:
                res = fut.result(timeout=60)
                self._reply(200, res)
            except FutureTimeout:
                fut.cancel()   # don't run it later, after the caller has given up
                self._reply(504, {"detail": "Human input command timed out"})
            except (ValueError, KeyError) as e:
                self._reply(400, {"detail": str(e)})
            except Exception as e:
                self._reply(500, {"detail": str(e)})

        def _reply(self, code: int, payload: Dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = int(srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


def _drain(ctx, cmd_queue: "queue.Queue[Tuple[str, Dict[str, Any], Future]]") -> None:
    while True:
        try:
            action, data, fut = cmd_queue.get_nowait()
        except queue.Empty:
            break
        if not fut.set_running_or_notify_cancel():
            continue
        try:
            fut.set_result(_exec_human(ctx, action, data))
        except Exception as e:
            fut.set_exception(e)


def _fail_pending(cmd_queue: "queue.Queue[Tuple[str, Dict[str, Any], Future]]") -> None:
    while True:
        try:
            _, _, fut = cmd_queue.get_nowait()
        except queue.Empty:
            break
        if fut.set_running_or_notify_cancel():
            fut.set_exception(RuntimeError("Browser closed"))


def main(pid: str, debug_port: int = 0, headless: bool = False) -> None:
    global main_world
    p = core.get_profile(pid)
    if p is None:
        sys.exit(f"profile {pid} not found")
    stop_flag = core._pdir(pid) / "stop.flag"   # Stop on Windows, where SIGTERM can't be caught
    stop_flag.unlink(missing_ok=True)
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    core.install_dock_hook()
    core.install_search_policy()
    label = core.dock_label(p)
    os.environ["FOXCLI_DOCK_BADGE"] = label
    os.environ.pop("FOXCLI_DOCK_TEXT", None)
    kw, loc = core.launch_kwargs(p, headless=headless, debug_port=debug_port or None)
    main_world = bool((kw.get("config") or {}).get("allowMainWorld"))
    exe = core.dock_app(p)     # private copy of the browser: Google search, badge in its Dock icon
    if exe:
        kw.pop("browser", None)
        kw["executable_path"] = exe
    elif label:
        os.environ["FOXCLI_DOCK_TEXT"] = "1"   # fall back to the Dock badge text
    udir = core._pdir(pid) / "userdata"
    udir.mkdir(exist_ok=True)
    cmd_queue: "queue.Queue[Tuple[str, Dict[str, Any], Future]]" = queue.Queue()
    control_token = secrets.token_urlsafe(24)
    srv, control_port = _start_control_server(cmd_queue, control_token)
    try:
        with Camoufox(persistent_context=True, user_data_dir=str(udir), **kw) as ctx:
            imp = core._pdir(pid) / "cookies_import.json"
            if imp.exists():
                try:
                    ctx.add_cookies(json.loads(imp.read_text()))
                finally:
                    imp.unlink(missing_ok=True)

            core._write_json(core._pdir(pid) / "runtime.json", {
                "pid": os.getpid(),
                "port": debug_port or None,
                "control_port": control_port,
                "control_token": control_token,
                "started_at": time.time(),
                "headless": headless,
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
                _drain(ctx, cmd_queue)
                pages = [pg for pg in ctx.pages if not pg.is_closed()]
                if not pages:
                    break
                try:
                    pages[0].wait_for_timeout(100)
                except Exception:
                    if closed or not [pg for pg in ctx.pages if not pg.is_closed()]:
                        break
                _drain(ctx, cmd_queue)
                if time.time() - last_save > 30:
                    save_cookies(pid, ctx)
                    last_save = time.time()
            if not closed:
                save_cookies(pid, ctx)
    finally:
        srv.shutdown()
        srv.server_close()
        _fail_pending(cmd_queue)


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
