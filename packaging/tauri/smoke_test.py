"""Smoke-test the packaged backend without a display or a Camoufox download.

    python3 packaging/tauri/smoke_test.py [path/to/foxlogin-backend]

Starts `foxlogin-backend --server` on a free port with a temporary data folder,
then checks the UI, the API (create / read / delete a profile, fingerprint
generation) and that the runner mode is wired in. Exits non-zero on failure.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
exe = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "src-tauri" / "resources" / "backend" / (
    "foxlogin-backend.exe" if os.name == "nt" else "foxlogin-backend")

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
base = f"http://127.0.0.1:{port}"
data = tempfile.mkdtemp(prefix="foxlogin-smoke-")
proc = subprocess.Popen([str(exe), "--server", "--port", str(port)], env=dict(os.environ, FOXCLI_DATA=data))


def call(path, method="GET", body=None, raw=False):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = r.read()
    return out if raw else json.loads(out or b"null")


ok = True


def check(desc, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + desc, flush=True)


try:
    start = time.time()
    while time.time() - start < 120:
        try:
            call("/api/meta")
            break
        except Exception:
            if proc.poll() is not None:
                sys.exit(f"backend exited with code {proc.returncode}")
            time.sleep(0.5)
    check(f"backend answers /api/meta ({time.time() - start:.1f}s)", call("/api/meta").get("port") == port)
    check("UI page is served", b"app.js" in call("/", raw=True))
    p = call("/api/v1/profiles", "POST", {"name": "smoke", "os": "windows"})
    check("profile created with a Windows fingerprint", p.get("os") == "windows" and p.get("webgl_info", {}).get("renderer"))
    check("profile listed", any(x["id"] == p["id"] for x in call("/api/v1/profiles")))
    call(f"/api/v1/profiles/{p['id']}", "DELETE")
    check("profile deleted", not any(x["id"] == p["id"] for x in call("/api/v1/profiles")))
    r = subprocess.run([str(exe), "--runner", "--help"], capture_output=True, text=True, timeout=60)
    check("runner mode is available", "pid" in (r.stdout + r.stderr))
finally:
    proc.terminate()
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
