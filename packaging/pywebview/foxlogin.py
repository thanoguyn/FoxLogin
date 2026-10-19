"""FoxLogin desktop app with a pywebview window (also what PyInstaller packages).

    python3 packaging/pywebview/foxlogin.py   run it from source (pip install -r packaging/pywebview/requirements-build.txt)

    foxlogin                         open the app window
    foxlogin --server                API + web UI only, no window (http://127.0.0.1:8765)
    foxlogin --runner <id> [...]     run one profile's browser (started by the app)
    foxlogin --camoufox <args>       the camoufox CLI (fetch, sync, ...), used by Settings
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# From source the app package sits three levels up; desktop.py sits next to this file
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
        elif hasattr(getattr(sys, name), "reconfigure"):
            getattr(sys, name).reconfigure(encoding="utf-8", errors="replace")


def main(argv) -> None:
    _std_streams()
    mode = argv[0] if argv else ""
    if mode == "--runner":
        from app import runner
        runner.cli(argv[1:])
    elif mode == "--camoufox":
        from camoufox.__main__ import cli
        cli(argv[1:], prog_name="camoufox")
    else:
        import desktop
        desktop.main(server_only="--server" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
