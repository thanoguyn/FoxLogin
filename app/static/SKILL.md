---
name: foxlogin
description: Automate and manage anti-detect browser profiles through the local FoxLogin app (Camoufox / Firefox engine) running at http://127.0.0.1:8765. Use whenever the user wants to create, update, clone, randomize, delete, or launch isolated browser profiles; import or check proxies in bulk; import or export cookies; drive profiles over WebDriver BiDi (Puppeteer, Selenium 4, or raw WebSocket BiDi); or simulate realistic human mouse trajectories, wheel scrolling, and keyboard typing via human_cursor and the /human/* API.
---

# FoxLogin: Camoufox Browser Profile Management & Automation

FoxLogin is a local, GoLogin-style anti-detect browser profile manager built on the **Camoufox** engine (C++-patched Firefox). Each profile has its own coherent hardware/OS fingerprint, proxy, isolated Firefox storage and cookies, and can be driven programmatically over **WebDriver BiDi** and **Humanized Input** while keeping `navigator.webdriver` set to `false`.

## Connection & Authentication

By default, the local server listens at:

```
http://127.0.0.1:8765
```

- Override the port or base URL via `FOXCLI_PORT` or `FOXCLI_URL`. Note that the packaged Tauri desktop app may pick a free port if `8765` is already in use.
- Two API route prefixes share the same backend handlers:
  - `/api/v1/...` and `/browser/...`: Official automation API. When an **API token** is configured in Settings, every request to these routes requires `Authorization: Bearer <token>` or `?token=<token>`.
  - `/api/...`: Local UI API (bound to `127.0.0.1`).

---

## Step 0: Pre-flight Check

Before running any automation task, verify that FoxLogin is running and a Camoufox browser build is installed:

```bash
# 1) Verify the FoxLogin server is reachable
curl -s http://127.0.0.1:8765/api/app
# -> {"app": "FoxLogin", "version": "1.0.3", "window": true}

# 2) Check whether an API token is set and inspect default profile settings
curl -s http://127.0.0.1:8765/api/settings

# 3) Check installed Camoufox browser builds
curl -s http://127.0.0.1:8765/api/browsers
```

**Handling common pre-flight states:**
- **Connection refused:** FoxLogin is not running. Start it with `python3 run.py` from the project directory or launch the FoxLogin desktop app.
- **`installed` is empty in `/api/browsers`:** No Camoufox build (~1.2 GB) is installed yet. Trigger `POST /api/browsers/setup` (or `POST /api/browsers/install` with `{"version": "...", "repo": "official"}`) and wait for the job to finish before starting a profile. Starting an automated profile while the browser is still downloading returns HTTP `503`.
- **Profile is already running manually (`state: "running"`, `port: null`):** Clicking **Run** in the UI launches the browser without opening a WebDriver BiDi port. Calling `/start` on that profile returns HTTP `409 Profile is running without automation; stop it first`. Stop it first with `POST /api/v1/profiles/{id}/stop`, then start it via `POST /api/v1/profiles/{id}/start`.

---

## 1. Profile Management

### List & Search Profiles: `GET /api/v1/profiles`

```bash
# List all profiles (includes state: "ready" | "running" | "downloading", and port when running via API)
curl -s "http://127.0.0.1:8765/api/v1/profiles"

# Filter by folder or search query (matches name and notes)
curl -s "http://127.0.0.1:8765/api/v1/profiles?folder=Shops&q=acc01"

# Inspect a single profile
curl -s "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID"
```

### Create a Profile: `POST /api/v1/profiles`

When creating a profile, FoxLogin automatically draws a coherent, realistic device fingerprint matching the target `os`. If you plan to automate mouse/keyboard actions or look up elements by CSS selector via `/human/*`, **enable `human_cursor` when creating the profile**:

```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Shop Account 01",
    "os": "macos",
    "folder": "Shops",
    "notes": "Main store account",
    "proxy": "http://user:pass@203.0.113.10:8080",
    "start_url": "https://example.com",
    "human_cursor": {"mode": "on", "max_time": 1.5}
  }'
```

| Field | Type / Allowed Values | Default | Notes |
|---|---|---|---|
| `name` | string | `"profile N"` | Display name |
| `os` | `"macos"`, `"windows"`, `"linux"` | Host OS | Target OS identity (drives screen, GPU, fonts, and voices) |
| `proxy` | string or object | `{"type": "none"}` | Accepts any Webshare string (`http://u:p@host:port`, `host:port:u:p`, `socks5://u:p@host:port`) or `{"type": "http"\|"socks5"\|"none", "host": "...", "port": "...", "username": "...", "password": "..."}` |
| `human_cursor` | `{"mode": "on"\|"off", "max_time": 1.5}` | `{"mode": "off", "max_time": 1.5}` | **Recommended `"on"` for automation:** enables humanized input over `wsUrl` and allows CSS `selector` lookups in `/human/*` |
| `folder` | string | `""` | Folder name |
| `notes` | string | `""` | Profile notes |
| `start_url` | string | `""` | URL opened automatically on launch |
| `resolution` | `"auto"` or `"1920x1080"`, etc. | `"auto"` | `"auto"` picks a real-world screen resolution for `os` |
| `timezone` | `{"mode": "ip"\|"custom", "value": "..."}` | `{"mode": "ip"}` | `"ip"` resolves timezone from the proxy exit IP |
| `language` | `{"mode": "ip"\|"custom", "value": "..."}` | `{"mode": "ip"}` | `"ip"` sets `Accept-Language` / `navigator.languages` from the exit IP country |
| `geolocation` | `{"mode": "ip"\|"custom"\|"block", "lat": "", "lon": "", "accuracy": "50", "permission": "prompt"\|"allow"}` | `{"mode": "ip", "permission": "prompt"}` | Coordinates from the exit IP or custom coordinates |
| `webrtc` | `{"mode": "ip"\|"real"\|"disabled"}` | `{"mode": "ip"}` | Spoofs WebRTC public IP to match the proxy IP |
| `canvas` | `"noise"` \| `"real"` | `"noise"` | C++ engine-level Canvas noise |
| `webgl_image` | `"real"` \| `"noise"` | `"real"` | Keep `"real"` (off); pixelscan flags `readPixels` noise |
| `webgl_info` | `{"mode": "masked"\|"real"\|"off", "vendor": "...", "renderer": "..."}` | `{"mode": "masked"}` | Picks a GPU coherent with the OS, screen, and CPU |
| `audio` | `"noise"` \| `"real"` | `"noise"` | Per-profile persistent audio seed |
| `media_devices` | `{"mode": "masked"\|"real", "webcams": 1, "micros": 1, "speakers": 1}` | `{"mode": "masked"}` | Masked camera, microphone, and speaker counts |
| `ublock` | bool | `false` | Built-in uBlock Origin extension |
| `block_images` | bool | `false` | Block images to save proxy bandwidth |
| `dock_badge` | `{"mode": "auto"\|"custom"\|"off", "text": ""}` | `{"mode": "auto"}` | Up to 4 characters shown on the Dock/taskbar icon and left of the address bar |

### Bulk Create & Text Import

```bash
# Bulk-create N profiles with distinct random devices
curl -s -X POST http://127.0.0.1:8765/api/profiles/bulk \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "prefix": "Worker", "randomize": true, "template": {"os": "windows", "folder": "Farm", "human_cursor": {"mode": "on", "max_time": 1.5}}}'

# Import line-by-line: name|proxy|notes|folder|os|start_url (only name is required)
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/import \
  -H "Content-Type: application/json" \
  -d '{"text": "acc 01|http://u:p@1.2.3.4:8080|note 1|Shops|mac|https://example.com\nacc 02|1.2.3.5:8080:u:p||Shops|windows"}'
```

### Update, Randomize, Refresh, Reset, Clone & Delete

- **Update (`PATCH /api/v1/profiles/{id}`):** Pass any fields to update. *Note:* While a profile is `running`, only `name`, `notes`, `folder`, `pinned`, and `dock_badge` can be changed. Stop the profile first before changing `proxy`, `os`, `human_cursor`, or mask settings (otherwise HTTP `409` is returned).
- **Randomize device (`POST /api/v1/profiles/{id}/randomize`):** Draws a new realistic hardware model (screen, GPU, media devices, and fingerprint) for the profile's OS. Profile must be stopped.
- **Refresh fingerprint (`POST /api/profiles/{id}/refresh`):** Regenerates the fingerprint while keeping the current device settings.
- **Reset to defaults (`POST /api/v1/profiles/{id}/reset`):** Re-applies default mask and location settings from Settings (preserves name, proxy, OS, and device).
- **Clone (`POST /api/profiles/{id}/clone`):** Duplicates the profile configuration with a fresh fingerprint and audio seed.
- **Delete (`DELETE /api/v1/profiles/{id}`):** Stops (if running) and permanently deletes the profile and its browser userdata. To delete multiple profiles at once: `POST /api/profiles/delete` with body `["id1", "id2"]`.

---

## 2. Proxies & Cookies

### Proxies

```bash
# List saved proxies (with check results and number of assigned profiles)
curl -s http://127.0.0.1:8765/api/v1/proxies

# Import proxies in bulk (one per line, any Webshare format)
curl -s -X POST http://127.0.0.1:8765/api/v1/proxies/import \
  -H "Content-Type: application/json" \
  -d '{"text": "http://user:pass@203.0.113.10:8080\n203.0.113.11:8080:user:pass\nsocks5://user:pass@1.2.3.4:1080", "type": "http"}'

# Check exit IP, country, timezone, and latency (ms) for saved proxy IDs
curl -s -X POST http://127.0.0.1:8765/api/proxies/check \
  -H "Content-Type: application/json" \
  -d '["PROXY_ID_1", "PROXY_ID_2"]'
```

### Cookies (Import & Export)

```bash
# Queue cookies (EditThisCookie, Cookie-Editor, or Playwright JSON array)
# Queued cookies are injected automatically on the next profile start
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/cookies \
  -H "Content-Type: application/json" \
  -d '[{"name": "session_id", "value": "xyz123", "domain": ".example.com", "path": "/", "secure": true, "httpOnly": true}]'

# Export cookies saved in the profile (safe to call even while the profile is running)
curl -s http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/cookies
```

---

## 3. Starting & Driving Profiles (WebDriver BiDi)

### Start a Profile with Automation Enabled

Two equivalent endpoints start a profile, wait up to 90 seconds for the browser and BiDi port to become ready, and return the connection endpoints:

```bash
# Option 1: Native API (pass ?headless=true for headless mode)
curl -s -X POST "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/start"
curl -s -X POST "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/start?headless=true"

# Option 2: GoLogin-compatible API
curl -s -X POST "http://127.0.0.1:8765/browser/start-profile" \
  -H "Content-Type: application/json" \
  -d '{"profileId": "PROFILE_ID", "headless": false}'
```

Response:

```json
{
  "status": "success",
  "profileId": "a1b2c3d4e5f6",
  "state": "running",
  "port": 54321,
  "wsUrl": "ws://127.0.0.1:8765/ws/a1b2c3d4e5f6",
  "wsEndpoint": "ws://127.0.0.1:54321/session"
}
```

### `wsUrl` vs. `wsEndpoint` (Important)

- **Always prefer `wsUrl` (`ws://127.0.0.1:8765/ws/{id}`):**
  1. Routes through FoxLogin's WebDriver BiDi relay, which rewrites `"browserName": "firefox"` so Puppeteer (`protocol: 'webDriverBiDi'`) connects cleanly.
  2. Automatically humanizes mouse moves, clicks, wheel scrolls, and keystrokes (**BiDi Humanizer**) whenever `human_cursor.mode` is `"on"`.
  3. Automatically sends `session.end` to Firefox when the client disconnects, allowing subsequent scripts to reconnect to the same running browser without session conflicts.
- **`wsEndpoint` (`ws://127.0.0.1:{port}/session`):** Direct connection to Firefox's raw BiDi socket (bypasses the relay and does not humanize BiDi input).
- **Do not use `playwright.firefox.connect()`:** Playwright uses its own proprietary Juggler protocol and cannot attach to a running profile. Use **Puppeteer** (`protocol: 'webDriverBiDi'`), **Selenium 4**, or **raw WebSocket BiDi + `/human/*`** as shown below.

### List Running Profiles & Stop a Profile

```bash
# List all currently running profiles and their wsUrl / port
curl -s http://127.0.0.1:8765/api/v1/running

# Stop a profile (saves cookie summary and closes the browser cleanly)
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/stop
# or GoLogin-compatible:
curl -s -X POST http://127.0.0.1:8765/browser/stop-profile \
  -H "Content-Type: application/json" -d '{"profileId": "PROFILE_ID"}'
```

---

## 4. Humanized Input (`human_cursor` & `/human/*`)

When a profile has `"human_cursor": {"mode": "on", "max_time": 1.5}`, FoxLogin provides **two ways** to generate realistic human input:

### Method 1: Transparent WebDriver BiDi Relay (`wsUrl`)
Every standard BiDi input action sent over `wsUrl` (`page.click()`, `page.mouse.move()`, `page.mouse.wheel()`, `page.keyboard.type()` in Puppeteer, or `input.performActions` in raw BiDi) is automatically transformed by the relay:
- **Mouse movement (`pointerMove`):** Expands straight moves into curved trajectories drawn from 2,357 recorded human movements (`cursory`), resampled at ~60 Hz and scaled within `[0, max_time]`. Supports both viewport coordinates and element-origin moves (`origin: {type: "element"}`).
- **Clicks (`pointerDown` / `pointerUp`):** Inserts natural 40–120 ms pauses before pressing and releasing mouse buttons.
- **Wheel scrolling (`wheel`):** Splits large scroll deltas (> 120 px) into realistic ~88–112 px wheel notches separated by 18–45 ms pauses.
- **Typing (`keyDown` / `keyUp`):** Adds 30–90 ms inter-keystroke delays between characters.

### Method 2: Direct HTTP API `/api/v1/profiles/{id}/human/{action}`
Drive Camoufox's built-in C++/Juggler trajectory generator directly through the profile runner over HTTP—no WebSocket or BiDi client required:

| Endpoint | JSON Body | Description |
|---|---|---|
| `POST .../human/move` | `{"x": 400, "y": 300, "page"?: 0}` | Move the cursor along a curved human path to `(x, y)` |
| `POST .../human/click` | `{"selector": "button.submit", "button"?: "left", "clickCount"?: 1, "delay"?: 65, "page"?: 0}` or `{"x": 400, "y": 300}` | Scroll element into view, pick a slightly jittered point near its center, move along a curved path, and click |
| `POST .../human/hover` | `{"selector": "a.menu", "page"?: 0}` or `{"x": 200, "y": 150}` | Scroll element into view and move the cursor over it |
| `POST .../human/scroll` | `{"deltaY": 500, "deltaX"?: 0, "x"?: 400, "y"?: 300, "page"?: 0}` | Optionally move to `(x, y)` first, then scroll using native wheel notches |
| `POST .../human/type` | `{"selector"?: "input[name=q]", "text": "hello", "delay"?: 50, "page"?: 0}` | If `selector` is given, click the element first, then type each character with natural 30–90 ms delays |

**Important rules for `/human/*`:**
1. **`"page"` selector (optional):** Chooses which open tab to target. Pass an integer index into `ctx.pages` (`0` for the first tab, `-1` for the most recently opened tab — default is `-1`) or a substring matching the tab's URL or title (e.g. `"page": "example.com"`).
2. **`"selector"` requires `human_cursor` on:** Looking up DOM elements by CSS selector (especially after BiDi navigation) runs in the page's main world, which FoxLogin enables only when the profile is started with `"human_cursor": {"mode": "on"}`. If `human_cursor` is `"off"`, pass explicit `x` and `y` coordinates instead.

---

## 5. Copy-Paste Automation Recipes

### Recipe 1: Node.js + Puppeteer (`puppeteer-core`)

```javascript
// npm install puppeteer-core
const puppeteer = require('puppeteer-core');

const BASE = process.env.FOXCLI_URL || 'http://127.0.0.1:8765';
const HEADERS = {
  'Content-Type': 'application/json',
  // Uncomment if an API token is configured in Settings:
  // 'Authorization': 'Bearer YOUR_TOKEN',
};

async function api(path, method = 'GET', body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: HEADERS,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

(async () => {
  // 1) Create (or pick) a profile with human_cursor enabled
  const profile = await api('/api/v1/profiles', 'POST', {
    name: 'Auto Worker',
    os: 'macos',
    human_cursor: { mode: 'on', max_time: 1.5 },
  });

  try {
    // 2) Start the profile with automation enabled
    const { wsUrl } = await api(`/api/v1/profiles/${profile.id}/start`, 'POST');

    // 3) Connect Puppeteer over WebDriver BiDi
    const browser = await puppeteer.connect({
      browserWSEndpoint: wsUrl,
      protocol: 'webDriverBiDi',
    });
    const page = (await browser.pages())[0] || (await browser.newPage());
    await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });

    // Standard BiDi actions over wsUrl are humanized automatically by the relay,
    // or you can invoke Camoufox's native humanize engine by CSS selector:
    await api(`/api/v1/profiles/${profile.id}/human/click`, 'POST', {
      selector: 'a',
      page: 'example.com',
    });

    console.log('Title:', await page.title());
    await browser.disconnect();
  } finally {
    // 4) Stop the profile to persist cookies
    await api(`/api/v1/profiles/${profile.id}/stop`, 'POST');
  }
})();
```

### Recipe 2: Python (WebDriver BiDi + `/human/*`, only requires `websockets`)

Lightweight Python pattern ideal for AI agents: use raw WebDriver BiDi for navigation and JavaScript evaluation, and `/human/*` for realistic clicks, scrolling, and typing without needing Selenium or Node.js.

```python
import asyncio
import json
import os
import urllib.request
import websockets

BASE = os.environ.get("FOXCLI_URL", "http://127.0.0.1:8765")
TOKEN = os.environ.get("FOXCLI_TOKEN", "")


def api(path: str, method: str = "GET", body=None):
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read() or b"null")


async def run_task(pid: str, ws_url: str):
    async with websockets.connect(ws_url, max_size=None) as ws:
        seq = 0

        async def bidi(method: str, params: dict):
            nonlocal seq
            seq += 1
            cid = seq
            await ws.send(json.dumps({"id": cid, "method": method, "params": params}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == cid:
                    if msg.get("type") == "error":
                        raise RuntimeError(f"BiDi {method} error: {msg}")
                    return msg["result"]

        # Start a BiDi session and grab the first tab's browsingContext
        await bidi("session.new", {"capabilities": {}})
        tree = await bidi("browsingContext.getTree", {})
        ctx = tree["contexts"][0]["context"]

        # Navigate to the target page
        await bidi("browsingContext.navigate", {
            "context": ctx,
            "url": "https://example.com/",
            "wait": "complete",
        })

        # Drive humanized interactions via /human/* (CSS selectors work when human_cursor is "on")
        api(f"/api/v1/profiles/{pid}/human/scroll", "POST", {"deltaY": 350})
        api(f"/api/v1/profiles/{pid}/human/hover", "POST", {"selector": "a"})

        # Evaluate JavaScript in the page
        res = await bidi("script.evaluate", {
            "expression": "JSON.stringify({ title: document.title, url: location.href, webdriver: navigator.webdriver })",
            "target": {"context": ctx},
            "awaitPromise": True,
        })
        print("Page info:", json.loads(res["result"]["value"]))
        await bidi("session.end", {})


# 1) Create or pick a profile with human_cursor enabled
profile = api("/api/v1/profiles", "POST", {
    "name": "Python BiDi Agent",
    "os": "macos",
    "human_cursor": {"mode": "on", "max_time": 1.5},
})

try:
    # 2) Start the profile (append ?headless=true for headless execution)
    start_info = api(f"/api/v1/profiles/{profile['id']}/start", "POST")
    asyncio.run(run_task(profile["id"], start_info["wsUrl"]))
finally:
    # 3) Stop the profile when finished
    api(f"/api/v1/profiles/{profile['id']}/stop", "POST")
```
