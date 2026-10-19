"""Python side of the Tauri desktop app (also what PyInstaller packages).

    foxlogin-backend --server --port N   API + web UI on 127.0.0.1:N (started by the Tauri shell)
    foxlogin-backend --runner <id> [...] run one profile's browser (started by the server)
    foxlogin-backend --camoufox <args>   the camoufox CLI (fetch, sync, ...), used by Settings

The Tauri shell owns the window, tray and single-instance logic; this process
only serves http://127.0.0.1:N and exits when the shell kills it. Running
profiles live in their own sessions, so they survive that.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# From source (python3 packaging/tauri/backend.py) the app package sits two levels up
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _std_streams() -> None:
    # Windowed builds start with no sys.stdout/stderr. Child modes get their
    # output redirected to a log by the parent, so reattach to those handles.
    # UTF-8, not the Windows ANSI code page: rich's spinner (U+280B) and
    # other non-ASCII output would otherwise raise UnicodeEncodeError.
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", buffering=1, closefd=False, encoding="utf-8", errors="replace"))
            except OSError:
                setattr(sys, name, open(os.devnull, "w"))


def _exit_with_parent() -> None:
    """Stop serving when the Tauri shell is gone, even if it was killed without
    a chance to stop us. Profiles keep running; the next start adopts them."""
    parent = os.environ.get("FOXLOGIN_PARENT_PID")
    if not parent:
        return
    import threading
    import time

    import psutil

    def watch():
        while psutil.pid_exists(int(parent)):
            time.sleep(2)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def serve(port: int) -> None:
    os.environ["FOXCLI_PORT"] = str(port)   # read by app.server for /api/meta and code samples
    from app import core

    core.hide_dock_icon()   # the Tauri shell already has the Dock icon
    logs = core.DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if core.FROZEN:
        sys.stdout = sys.stderr = open(logs / "app.log", "a", buffering=1, encoding="utf-8")

    import uvicorn

    from app import server

    _exit_with_parent()
    print(f"FoxLogin API on http://127.0.0.1:{port} (data: {core.DATA})", flush=True)
    uvicorn.run(server.app, host="127.0.0.1", port=port, log_level="warning", log_config=None)


def main(argv) -> None:
    _std_streams()
    mode = argv[0] if argv else ""
    if mode == "--runner":
        from app import runner
        runner.cli(argv[1:])
    elif mode == "--camoufox":
        from camoufox.__main__ import cli
        cli(argv[1:], prog_name="camoufox")
    elif mode == "--server":
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8765
        serve(port)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main(sys.argv[1:])
