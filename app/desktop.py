"""Desktop shell: the FastAPI server in a background thread plus a native window.

Only one copy runs at a time. A second launch brings the first copy's window
to the front and exits. Closing the window stops the server but leaves running
profiles open; the next launch adopts them through their runtime.json.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

from app import core

DEFAULT_PORT = 8765


def _ping(port: int) -> Optional[Dict[str, Any]]:
    """The FoxLogin instance listening on `port`, if any."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/app", timeout=1) as r:
            info = json.loads(r.read())
        return info if info.get("app") == "FoxLogin" else None
    except Exception:
        return None


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _log_to_file() -> None:
    """A windowed app has no console; keep server output in data/logs/app.log."""
    logs = core.DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    f = open(logs / "app.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f


def _open_window(url: str, srv=None) -> None:
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True              # cookie export
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    win = webview.create_window("FoxLogin", url, width=1380, height=880, min_size=(980, 620),
                                background_color="#F4F5F7", text_select=True)
    if srv is not None:
        from app import server

        def focus():
            win.restore()
            win.show()
        server.app.state.focus = focus
    webview.start(private_mode=False, storage_path=str(core.DATA / "webview"))


def main(server_only: bool = False) -> None:
    port = int(os.environ.get("FOXCLI_PORT") or DEFAULT_PORT)
    other = _ping(port)
    if other:
        if server_only:
            sys.exit(f"FoxLogin is already running on port {port}")
        if other.get("window"):
            urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{port}/api/app/focus", method="POST"), timeout=2)
        else:  # a server without a window (run.py or --server): just open one onto it
            _open_window(f"http://127.0.0.1:{port}/")
        return
    if _port_busy(port):
        port = _free_port()
    os.environ["FOXCLI_PORT"] = str(port)

    if core.FROZEN and not server_only:
        _log_to_file()
    if server_only:
        core.hide_dock_icon()

    import uvicorn

    from app import server

    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    srv = uvicorn.Server(config)
    if server_only:
        print(f"FoxLogin API on http://127.0.0.1:{port}", flush=True)
        srv.run()
        return

    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not srv.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not srv.started:
        sys.exit("FoxLogin server failed to start (see logs/app.log)")
    url = f"http://127.0.0.1:{port}/"
    try:
        _open_window(url, srv)
    except Exception as e:  # no usable web view (e.g. WebView2 / WebKitGTK missing)
        print("native window unavailable, using the default browser:", repr(e), flush=True)
        import webbrowser

        webbrowser.open(url)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
    finally:
        srv.should_exit = True
        thread.join(5)
