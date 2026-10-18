"""Start FoxLogin: python3 run.py  ->  http://127.0.0.1:8765"""
import os
import threading
import webbrowser

import uvicorn

from app import core

core.hide_dock_icon()

PORT = int(os.environ.get("FOXCLI_PORT", 8765))

if __name__ == "__main__":
    if not os.environ.get("FOXCLI_NO_OPEN"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    uvicorn.run("app.server:app", host="127.0.0.1", port=PORT, log_level="warning")
