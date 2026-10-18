"""Start a profile through the REST API and drive it over WebDriver BiDi.

Creates a throwaway Windows profile, starts it headless via
POST /api/v1/profiles/{id}/start, opens a page over the returned wsUrl,
checks navigator.webdriver and the spoofed identity, then stops and deletes it.
Needs the server running (python3 run.py) and `pip3 install websockets`.
"""
import asyncio
import json
import os
import sys
import urllib.request

import websockets

BASE = os.environ.get("FOXCLI_URL", "http://127.0.0.1:8765")


def api(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read() or "null")


async def drive(ws_url):
    async with websockets.connect(ws_url, max_size=None) as ws:
        n = 0

        async def cmd(method, params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == n:
                    return m

        await cmd("session.new", {"capabilities": {}})
        ctx = (await cmd("browsingContext.getTree", {}))["result"]["contexts"][0]["context"]
        await cmd("browsingContext.navigate", {"context": ctx, "url": "https://example.com/", "wait": "complete"})
        out = {}
        for expr in ("document.title", "navigator.webdriver", "navigator.userAgent", "navigator.platform",
                     "Intl.DateTimeFormat().resolvedOptions().timeZone", "screen.width + 'x' + screen.height"):
            res = await cmd("script.evaluate", {"expression": expr, "target": {"context": ctx}, "awaitPromise": False})
            out[expr] = res["result"]["result"].get("value")
            print(f"  {expr:52} = {out[expr]!r}")
        return out


p = api("/api/v1/profiles", "POST", {"name": "api-test", "os": "windows"})
try:
    print(f"POST /api/v1/profiles/{p['id']}/start?headless=true")
    r = api(f"/api/v1/profiles/{p['id']}/start?headless=true", "POST")
    print("  wsUrl:", r["wsUrl"])
    out = asyncio.run(drive(r["wsUrl"]))
    print("POST /browser/stop-profile ->", api("/browser/stop-profile", "POST", {"profileId": p["id"]})["state"])
finally:
    api(f"/api/v1/profiles/{p['id']}", "DELETE")

checks = [
    ("page loaded over BiDi", out["document.title"] == "Example Domain"),
    ("navigator.webdriver is false", out["navigator.webdriver"] is False),
    ("Windows identity (userAgent + platform)", "Windows NT" in out["navigator.userAgent"] and out["navigator.platform"] == "Win32"),
]
for desc, cond in checks:
    print(("PASS " if cond else "FAIL ") + desc)
ok = all(c for _, c in checks)
print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
