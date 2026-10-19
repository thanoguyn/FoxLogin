"""Verify humanized cursor movement over both WebDriver BiDi (/ws/<id>) and
Camoufox's native Playwright channel (/api/v1/profiles/<id>/human/*).

Covers:
  1. BiDi relay (/ws/<id>) with human_cursor on:
     - pointerMove (10,10) -> (800,500) produces > 20 mousemove events,
       a curved path (max perpendicular distance > 5 px), duration <= max_time,
       and ends at (800, 500).
     - element-origin pointerMove + click lands on and clicks the target button.
     - wheel scroll with a large deltaY splits into multiple wheel notches.
  2. BiDi relay (/ws/<id>) with human_cursor off:
     - pointerMove (10,10) -> (800,500) jumps in a single event.
  3. Native Playwright channel (/api/v1/profiles/<id>/human/*) with human_cursor on:
     - /human/move (10,10) -> (800,500) produces a curved, multi-step path.
     - /human/click clicks a button and fires its handler.
  4. Native Playwright channel with human_cursor off:
     - /human/move (10,10) -> (800,500) jumps in a single event (proves the
       humanize launch option reaches the browser only when enabled).
"""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.humanize import generate_trajectory, perpendicular_distance  # noqa: E402

BASE = os.environ.get("FOXCLI_URL", "http://127.0.0.1:8765")

TEST_BODY_HTML = (
    '<div style="width:100vw;height:3000px;position:relative">'
    '<button id="target-btn" style="position:absolute;left:320px;top:220px;width:120px;height:48px">'
    "Click Me</button></div>"
)

SETUP_TRACKER_JS = """() => {
  document.body.style.margin = '0';
  document.body.innerHTML = """ + json.dumps(TEST_BODY_HTML) + """;
  window.scrollTo(0, 0);
  window.__moves = [];
  window.__clicks = [];
  window.__wheels = [];
  if (!window.__installed) {
    window.__installed = true;
    window.addEventListener('mousemove', e => {
      window.__moves.push({ x: e.clientX, y: e.clientY, t: performance.now() });
    });
    window.addEventListener('wheel', e => {
      window.__wheels.push({ dy: e.deltaY, mode: e.deltaMode, t: performance.now() });
    });
  }
  const btn = document.getElementById('target-btn');
  if (btn) {
    btn.addEventListener('click', e => {
      window.__clicks.push({ x: e.clientX, y: e.clientY, id: 'target-btn' });
    });
  }
  return [window.innerWidth, window.innerHeight];
}"""


def api(path: str, method: str = "GET", body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json"},
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=90).read() or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {path}: {detail}") from e


def max_perp(moves, x0=10.0, y0=10.0, x1=800.0, y1=500.0) -> float:
    if not moves:
        return 0.0
    return max(perpendicular_distance(m["x"], m["y"], x0, y0, x1, y1) for m in moves)


async def test_bidi(ws_url: str, humanized: bool):
    async with websockets.connect(ws_url, max_size=None) as ws:
        seq = 0

        async def cmd(method: str, params: dict):
            nonlocal seq
            seq += 1
            cid = seq
            await ws.send(json.dumps({"id": cid, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == cid:
                    if m.get("type") == "error":
                        raise RuntimeError(f"BiDi {method} failed: {m}")
                    return m

        async def call_fn(fn_decl: str, args=None):
            res = await cmd("script.callFunction", {
                "functionDeclaration": fn_decl,
                "target": {"context": ctx},
                "arguments": args or [],
                "awaitPromise": False,
            })
            return res["result"]["result"]

        async def eval_json(expr: str):
            res = await cmd("script.evaluate", {
                "expression": f"JSON.stringify({expr})",
                "target": {"context": ctx},
                "awaitPromise": False,
            })
            return json.loads(res["result"]["result"]["value"])

        await cmd("session.new", {"capabilities": {}})
        ctx = (await cmd("browsingContext.getTree", {}))["result"]["contexts"][0]["context"]
        await cmd("browsingContext.navigate", {
            "context": ctx,
            "url": "https://example.com/",
            "wait": "complete",
        })
        await call_fn(SETUP_TRACKER_JS)

        # Position cursor at (10, 10), then clear recorded moves and move to (800, 500)
        await cmd("input.performActions", {
            "context": ctx,
            "actions": [{
                "type": "pointer",
                "id": "mouse",
                "parameters": {"pointerType": "mouse"},
                "actions": [{"type": "pointerMove", "x": 10, "y": 10, "duration": 0, "origin": "viewport"}],
            }],
        })
        await eval_json("(window.__moves = [], true)")

        t0 = time.monotonic()
        await cmd("input.performActions", {
            "context": ctx,
            "actions": [{
                "type": "pointer",
                "id": "mouse",
                "parameters": {"pointerType": "mouse"},
                "actions": [{"type": "pointerMove", "x": 800, "y": 500, "duration": 0, "origin": "viewport"}],
            }],
        })
        wall_s = time.monotonic() - t0
        moves = await eval_json("window.__moves")
        span_s = ((moves[-1]["t"] - moves[0]["t"]) / 1000.0) if len(moves) >= 2 else 0.0

        out = {
            "count": len(moves),
            "perp": round(max_perp(moves, 10, 10, 800, 500), 2),
            "span_s": round(span_s, 3),
            "wall_s": round(wall_s, 3),
            "last": (moves[-1]["x"], moves[-1]["y"]) if moves else None,
        }

        if humanized:
            # Element-origin move + click
            el_ref = await call_fn("() => document.getElementById('target-btn')")
            await eval_json("(window.__moves = [], window.__clicks = [], true)")
            await cmd("input.performActions", {
                "context": ctx,
                "actions": [{
                    "type": "pointer",
                    "id": "mouse",
                    "parameters": {"pointerType": "mouse"},
                    "actions": [
                        {
                            "type": "pointerMove",
                            "x": 0,
                            "y": 0,
                            "duration": 0,
                            "origin": {"type": "element", "element": {"sharedId": el_ref["sharedId"]}},
                        },
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerUp", "button": 0},
                    ],
                }],
            })
            el_moves = await eval_json("window.__moves")
            clicks = await eval_json("window.__clicks")
            out["el_moves"] = len(el_moves)
            out["clicked"] = len(clicks) == 1 and clicks[0]["id"] == "target-btn"

            # Wheel scroll split into notches
            await eval_json("(window.__wheels = [], true)")
            await cmd("input.performActions", {
                "context": ctx,
                "actions": [{
                    "type": "wheel",
                    "id": "wheel",
                    "actions": [{
                        "type": "scroll",
                        "x": 300,
                        "y": 200,
                        "deltaX": 0,
                        "deltaY": 450,
                        "duration": 0,
                        "origin": "viewport",
                    }],
                }],
            })
            wheels = await eval_json("window.__wheels")
            out["wheel_notches"] = len(wheels)
            out["wheel_sum"] = round(sum(w["dy"] for w in wheels), 1)

        await cmd("session.end", {})
        return out


async def test_human_api(pid: str, ws_url: str, click: bool = True):
    async with websockets.connect(ws_url, max_size=None) as ws:
        seq = 0

        async def cmd(method: str, params: dict):
            nonlocal seq
            seq += 1
            cid = seq
            await ws.send(json.dumps({"id": cid, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == cid:
                    if m.get("type") == "error":
                        raise RuntimeError(f"BiDi {method} failed: {m}")
                    return m

        async def call_fn(fn_decl: str):
            res = await cmd("script.callFunction", {
                "functionDeclaration": fn_decl,
                "target": {"context": ctx},
                "arguments": [],
                "awaitPromise": False,
            })
            return res["result"]["result"]

        async def eval_json(expr: str):
            res = await cmd("script.evaluate", {
                "expression": f"JSON.stringify({expr})",
                "target": {"context": ctx},
                "awaitPromise": False,
            })
            return json.loads(res["result"]["result"]["value"])

        await cmd("session.new", {"capabilities": {}})
        ctx = (await cmd("browsingContext.getTree", {}))["result"]["contexts"][0]["context"]
        await cmd("browsingContext.navigate", {
            "context": ctx,
            "url": "https://example.com/",
            "wait": "complete",
        })
        await call_fn(SETUP_TRACKER_JS)

        # Move to (10, 10) via /human/move, clear moves, then move to (800, 500)
        api(f"/api/v1/profiles/{pid}/human/move", "POST", {"x": 10, "y": 10})
        await eval_json("(window.__moves = [], window.__clicks = [], true)")

        api(f"/api/v1/profiles/{pid}/human/move", "POST", {"x": 800, "y": 500})
        moves = await eval_json("window.__moves")
        span_s = ((moves[-1]["t"] - moves[0]["t"]) / 1000.0) if len(moves) >= 2 else 0.0

        clicks = []
        if click:   # selector lookups need main-world eval, which only human_cursor on allows
            api(f"/api/v1/profiles/{pid}/human/click", "POST", {"selector": "#target-btn"})
            clicks = await eval_json("window.__clicks")

        await cmd("session.end", {})
        return {
            "count": len(moves),
            "perp": round(max_perp(moves, 10, 10, 800, 500), 2),
            "span_s": round(span_s, 3),
            "last": (moves[-1]["x"], moves[-1]["y"]) if moves else None,
            "clicked": len(clicks) == 1 and clicks[0]["id"] == "target-btn",
        }


def _ensure_server():
    """Connect to FOXCLI_URL if running; otherwise start a temporary server."""
    global BASE
    try:
        urllib.request.urlopen(BASE + "/api/app", timeout=1.5).read()
        return None
    except Exception:
        pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    tmp = tempfile.mkdtemp(prefix="foxcli-hc-")
    os.environ.setdefault("FOXCLI_HUMAN_SEED", "42")
    env = dict(
        os.environ,
        FOXCLI_PORT=str(port),
        FOXCLI_DATA=tmp,
        FOXCLI_NO_OPEN="1",
        FOXCLI_HUMAN_SEED=os.environ["FOXCLI_HUMAN_SEED"],
    )
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    BASE = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(BASE + "/api/app", timeout=1.0).read()
            return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("Could not start temporary FoxLogin server")


def main() -> None:
    os.environ.setdefault("FOXCLI_HUMAN_SEED", "42")
    srv_proc = _ensure_server()
    try:
        # 0. Deterministic unit check for Cursory + CursorTrajectory.js glue code
        t_a = generate_trajectory(10, 10, 800, 500, max_time=1.5, seed=42)
        t_b = generate_trajectory(10, 10, 800, 500, max_time=1.5, seed=42)
        t_scaled = generate_trajectory(10, 10, 800, 500, max_time=0.4, seed=42)
        scaled_ms = sum(s["duration"] for s in t_scaled)
        det_ok = (
            t_a == t_b
            and len(t_a) > 20
            and (t_a[-1]["x"], t_a[-1]["y"]) == (800, 500)
            and 350 <= scaled_ms <= 400
            and (t_scaled[-1]["x"], t_scaled[-1]["y"]) == (800, 500)
        )

        max_time = 1.5
        p_on = api("/api/v1/profiles", "POST", {
            "name": "hc-on",
            "human_cursor": {"mode": "on", "max_time": max_time},
        })
        p_off = api("/api/v1/profiles", "POST", {
            "name": "hc-off",
            "human_cursor": {"mode": "off", "max_time": max_time},
        })
        try:
            print(f"1. Starting profile {p_on['id']} (human_cursor=on, max_time={max_time}s)...")
            r_on = api(f"/api/v1/profiles/{p_on['id']}/start?headless=true", "POST")
            bidi_on = asyncio.run(test_bidi(r_on["wsUrl"], humanized=True))
            print("   BiDi (on):     ", bidi_on)
            native_on = asyncio.run(test_human_api(p_on["id"], r_on["wsUrl"]))
            print("   /human/* (on): ", native_on)
            api(f"/api/v1/profiles/{p_on['id']}/stop", "POST")

            print(f"2. Starting profile {p_off['id']} (human_cursor=off)...")
            r_off = api(f"/api/v1/profiles/{p_off['id']}/start?headless=true", "POST")
            bidi_off = asyncio.run(test_bidi(r_off["wsUrl"], humanized=False))
            print("   BiDi (off):    ", bidi_off)
            native_off = asyncio.run(test_human_api(p_off["id"], r_off["wsUrl"], click=False))
            print("   /human/* (off):", native_off)
            api(f"/api/v1/profiles/{p_off['id']}/stop", "POST")
        finally:
            for pid in (p_on["id"], p_off["id"]):
                try:
                    api(f"/api/v1/profiles/{pid}/stop", "POST")
                    api(f"/api/v1/profiles/{pid}", "DELETE")
                except Exception:
                    pass

        checks = [
            ("trajectory generator is deterministic under a seed", det_ok),
            ("BiDi (on): > 20 mousemove events", bidi_on["count"] > 20),
            ("BiDi (on): curved path (max perp distance > 5 px)", bidi_on["perp"] > 5.0),
            ("BiDi (on): total duration <= max_time", bidi_on["span_s"] <= max_time),
            ("BiDi (on): final point equals target (800, 500)", bidi_on["last"] == (800, 500)),
            ("BiDi (on): element-origin move + click fires on button", bidi_on.get("clicked") is True and bidi_on.get("el_moves", 0) > 10),
            ("BiDi (on): wheel scroll splits into multiple notches", bidi_on.get("wheel_notches", 0) >= 4 and abs(bidi_on.get("wheel_sum", 0) - 450) < 1),
            ("BiDi (off): single straight jump (1 event)", bidi_off["count"] == 1 and bidi_off["last"] == (800, 500)),
            ("/human/move (on): multi-step curved trajectory", native_on["count"] > 10 and native_on["perp"] > 2.0 and native_on["last"] == (800, 500)),
            ("/human/click (on): clicks button and runs handler", native_on["clicked"] is True),
            ("/human/move (off): single jump (launch option off)", native_off["count"] == 1 and native_off["last"] == (800, 500)),
        ]
        print()
        for desc, cond in checks:
            print(("PASS " if cond else "FAIL ") + desc)
        ok = all(c for _, c in checks)
        print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
        sys.exit(0 if ok else 1)
    finally:
        if srv_proc is not None:
            srv_proc.terminate()
            try:
                srv_proc.wait(timeout=5)
            except Exception:
                srv_proc.kill()


if __name__ == "__main__":
    main()
