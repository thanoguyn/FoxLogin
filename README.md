# FoxLogin

**A local, GoLogin-style browser profile manager built on the [Camoufox](https://camoufox.com) engine (Firefox).**

FoxLogin runs on your own machine as a small web app. You can create any number of browser profiles. Each profile has its own consistent fingerprint, its own proxy, and its own cookies and Firefox storage. You can run profiles by hand or automate them through a GoLogin-compatible REST API that uses WebDriver BiDi.

You can also package it as a desktop app (macOS, Windows, Linux) that installs like any other program and needs no Python. See [Desktop app packaging](#desktop-app-packaging).

![Profiles](docs/screenshots/ui-profiles.png)

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation & running](#installation--running)
- [User interface tour](#user-interface-tour)
- [Realistic random fingerprints](#realistic-random-fingerprints)
- [Mask options](#mask-options)
- [Automation API](#automation-api)
- [Desktop app packaging](#desktop-app-packaging)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Test results (evidence)](#test-results-evidence)
- [Known limitations](#known-limitations)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Features

- **Unlimited profiles.** Each profile keeps its fingerprint, cookies and Firefox user data in `data/profiles/<id>/`.
- **Consistent fingerprints.** The OS, screen, GPU, fonts and media devices are drawn together from real-world device models. They are not random values that contradict each other.
- **Engine-level masking.** Camoufox applies Canvas, WebGL and Audio noise in C++, so no JavaScript injection is involved and `navigator.webdriver` stays `false`.
- **Proxy manager.** Paste proxies in bulk in any common Webshare format. You can check each proxy's IP, country and latency, and assign proxies to profiles one by one or many at once.
- **Location from the IP.** Timezone, language, geolocation and the WebRTC public IP all follow the proxy's exit IP automatically.
- **Bulk actions.** Run, stop, set proxy, move to a folder, re-randomize or delete many profiles at once. You can also import profiles from text.
- **Cookie import and export** for each profile.
- **Browser-core manager.** Install, switch and remove Camoufox versions, either as the global default or per profile.
- **GoLogin-compatible REST API.** `POST /browser/start-profile` returns a `wsUrl` that Puppeteer, Selenium 4 and other WebDriver BiDi clients can connect to.
- **Browsers survive a server restart.** Browsers keep running when the server stops, and the server picks them up again when it starts.
- **App updates from GitHub Releases.** The desktop app tells you when a new release is out and can install it for you.

## Requirements

- macOS, Windows or Linux with **Python 3.10+** (developed on Python 3.13 / macOS).
- About 1.2 GB of disk space for each Camoufox browser build. On first start FoxLogin offers the list of builds (newest stable preselected); skip it and the newest stable build downloads the first time a profile runs, with its progress shown on the Run button and in a banner.

## Installation & running

```bash
git clone https://github.com/thanoguyn/FoxLogin.git
cd FoxLogin
pip3 install -r requirements.txt
python3 run.py            # macOS: you can also double-click start.command
```

The UI opens at **http://127.0.0.1:8765**.

| Environment variable | Default | Meaning |
|---|---|---|
| `FOXCLI_PORT` | `8765` | HTTP port of the UI/API |
| `FOXCLI_DATA` | `./data` | Where profiles, proxies and settings are stored |
| `FOXCLI_NO_OPEN` | *(unset)* | Set it to stop the browser tab from opening on start |

> `data/` holds your proxies (including passwords) and every profile's cookies. It is listed in `.gitignore`, so never commit it.

## User interface tour

### Profiles

![Profiles list](docs/screenshots/ui-profiles.png)

- **Sidebar.** Collapse it with the top-left button or `Ctrl/⌘+B`. It has All profiles, Proxies, API & Automation, Settings, Folders and the Fingerprint self-test.
- **Rename** a profile by double-clicking its name. **Notes** can be edited inline by clicking the *Notes* cell.
- **Proxy & Location cell.** Click it to pick a saved proxy, or paste one (📋).
- **Column picker** (⚙, top right). Shows or hides the columns for proxy port, username and password, folder, OS, device, browser version, created date, last run, and more.
- **Row menu `•••`.** Settings, Folders, Clone, Run/Stop, Cookies (import/export), Random fingerprint, Refresh fingerprint, Update browser, Copy "Run" link, Copy ID, Pin, Delete, Automation.
- **Multi-select** for bulk Run, Stop, Set proxy, Move to folder, Random fingerprint and Delete. When you paste *N* proxies onto *N* profiles, each profile gets one proxy in order.

### Creating a profile

![Create profile drawer](docs/screenshots/ui-new-profile.png)

**Add profile** opens the drawer, which has a **Random fingerprint** button. The arrow next to Add profile offers **Quick profile**, **Create multiple profiles** and **Import profiles**.

Import format, one profile per line (only `name` is required):

```
name|proxy|notes|folder|os|start_url
```

### Proxies

![Proxies](docs/screenshots/ui-proxies.png)

Add proxies in bulk, one per line. All Webshare formats are accepted:

```
http://user:pass@host:port/
host:port:user:pass
socks5://user:pass@host:port
host:port
```

**Check** shows each proxy's exit IP, country and latency. The *Profiles* column shows how many profiles use each proxy.

### Settings

![Settings](docs/screenshots/ui-settings.png)

- **Defaults for new profiles.** OS, language, timezone, geolocation, WebRTC, resolution, every mask, and extensions.
- **Browser core.** Lists the installed Camoufox builds and has *Check for updates*. You can install a newer or older build (about 1.2 GB each), choose the default, or remove unused builds. Each profile can also pin its own build.
- **API token** (optional). When it is set, every `/api/v1` and `/browser` call needs `Authorization: Bearer <token>` or `?token=<token>`.
- **FoxLogin updates.** Shows the installed version and checks GitHub Releases for a newer one (on start, unless *Check on start* is off, or with *Check now*). How the update is installed depends on the copy:
  - **Windows installer, Linux AppImage:** *Update now* downloads the release, checks its SHA-256, then FoxLogin closes, installs it and opens again. On Windows, running profiles are closed first, because the installer replaces the program they run from. On Linux they keep running.
  - **macOS:** the `.dmg` is saved to Downloads and opened, and FoxLogin quits so you can drag the new FoxLogin into Applications. Running profiles stay open. If Finder says FoxLogin is in use, close the profile windows and drag again.
  - **From source, `.tar.gz`, `.deb` or `.msi` installs:** a link to the release page (`git pull` for a checkout).
- **Reset to recommended** restores the recommended defaults. Inside a profile, **Reset to defaults** applies the current defaults to that profile. It keeps the name, proxy, OS and device.

### Profile badge

Each profile window can be told apart in two places:

- **App icon.**
  - *macOS:* each profile runs a private copy of its Camoufox build. Its Dock icon shows the number or letters (up to 4 characters) large on a round tile, with the Camoufox icon shrunk to a badge in the corner, and every profile gets its own Dock tile named "Camoufox 3". The copy is an APFS clone (almost no extra disk space; see `cp -c`) kept in `~/Library/Caches/FoxLogin/browsers/<id>/` (outside Documents, which macOS protects and which breaks the browser's bundled fonts) and rebuilt when the badge or the browser build changes. macOS does not draw the badge text a Camoufox window sets on its own Dock tile, hence the copy.
  - *Windows:* the text is shown as a taskbar overlay icon.
  - *Linux:* the text is added to the window title as `[3]`.
- **Address bar.** A small red label just left of the address bar shows the same text on every system.

Settings: **Auto** derives the text from the name ("profile 3" → `3`, "mac B" → `B`). **Custom** takes up to 4 characters. **Off** shows nothing. Changes apply from the next launch. The background Python processes no longer add their own Dock icon.

### Default search engine

Stock Camoufox has a search engine called "None" that points at 127.0.0.1, so anything typed in the address bar went to localhost. FoxLogin makes Google the default: on macOS in each profile's browser copy, on Windows and Linux in the installed Camoufox builds (`distribution/policies.json`, re-applied before every launch).

### API & Automation

![API page](docs/screenshots/ui-api.png)

This page lists every endpoint, with ready-to-copy code snippets that already contain the selected profile's ID, and lets you download the **AI Agent Skill** (`foxlogin.skill` or `SKILL.md`) for Claude Code, Claude Desktop, Antigravity, Cursor and Codex.

## Realistic random fingerprints

Each randomization picks one real machine for the chosen OS and keeps every value consistent with it:

- **macOS.** MacBook Air 13" (1470×956 or 1440×900), MacBook Pro 14"/16", Air 15", Mac mini or Mac Studio with a QHD display.
- **Windows / Linux.** Laptops and desktops with common resolutions.
- **Media devices.** Laptops have a built-in camera, microphone and speakers. Desktops may have no webcam.
- **GPU.** Only GPUs that fit the screen and CPU class are picked.

Two values are deliberately **not** randomized:

- **Device memory.** Firefox has no `navigator.deviceMemory`.
- **CPU thread count.** Always the real one. A fake value is exposed by timing Web Workers.

## Mask options

| Option | Masked / Noise | Real / Off |
|---|---|---|
| Canvas | Noise generated inside the Firefox engine (C++), the same as stock Firefox 145+. Changes on every browser launch and differs per profile | Real hardware hash, identical for every profile on the same machine |
| WebGL image | Noise on `readPixels`. **pixelscan detects it, so it is Off by default** | No noise |
| Audio context | Per-profile seed, stable across launches | No noise |
| WebGL info | A GPU that fits the OS, screen and CPU | Real GPU |
| Media devices | Number and names of cameras, mics and speakers per profile | Real devices |
| Timezone / Language / Geo / WebRTC | From the IP (through the proxy, if any) or Custom. Geolocation permission defaults to **Prompt** | |
| Human cursor | Curved, human-paced mouse trajectories, wheel-sized scroll notches, and natural click/typing pauses (capped at `max_time`, default `1.5` s) | Off by default (direct jumps) |

## Automation API

Camoufox is Firefox, so automation uses **WebDriver BiDi**:

- Puppeteer, Selenium 4 and any other BiDi client work, and `navigator.webdriver` stays `false`.
- Playwright `connect()` **cannot** attach to a running profile.
- Profiles started with the **Run** button do not open an automation port. Use the API to start them instead.

### Humanized input (`human_cursor`)

When a profile has `"human_cursor": {"mode": "on", "max_time": 1.5}` (or **Human cursor › On** in the UI), FoxLogin provides human-like input in two ways:

1. **Transparent WebDriver BiDi relay (`wsUrl` / `/ws/<id>`).**
   - `input.performActions` mouse moves (`pointerType: "mouse"` or omitted) are expanded through [`cursory.generate_trajectory`](https://pypi.org/project/cursory/) (the same library of 2,357 recorded human movements that Camoufox's built-in `humanize` uses) and scaled/resampled to ~60 Hz inside `[0, max_time]` following `CursorTrajectory.js`.
   - Element origins (`origin: {type: "element", element: {sharedId}}`, used by Selenium's `move_to_element`) are resolved to the element's on-screen centre before generating the path.
   - Short random pauses (40–120 ms) are inserted before `pointerDown` and `pointerUp`, large `wheel` scrolls are split into ~100 px notches, and `key` sequences get 30–90 ms typing gaps.
   - *Limits:* Only `wsUrl` (`ws://127.0.0.1:<port>/ws/<id>`) goes through the relay; `wsEndpoint` (the raw BiDi port) bypasses it and stays unhumanized. `pointerType: "touch"` and `"pen"` are passed through untouched.

2. **Camoufox's native `humanize` via `/api/v1/profiles/{id}/human/{move|click|scroll|type|hover}`.**
   - Passes `humanize=<max_time>` to Camoufox on launch and drives the browser's built-in Juggler/Cursory trajectory generator through the profile runner.
   - Each endpoint accepts an optional `page` field (an integer index into `ctx.pages`, default `-1`, or a URL/title substring; BiDi `browsingContext` IDs are not visible to Playwright):
     - `POST .../human/move` — `{"x": 400, "y": 300, "page"?: 0}`
     - `POST .../human/click` — `{"selector": "button.submit"}` or `{"x": 400, "y": 300, "button"?: "left", "clickCount"?: 1}`
     - `POST .../human/scroll` — `{"deltaY": 500, "deltaX"?: 0, "x"?: 400, "y"?: 300}` (native wheel notches)
     - `POST .../human/type` — `{"selector"?: "input[name=q]", "text": "hello", "delay"?: 50}`
     - `POST .../human/hover` — `{"selector": "a.menu"}` or `{"x": 200, "y": 150}`
   - `selector` lookups run in the page's main world, which FoxLogin allows only for profiles with Human cursor on. With it off, use `x`/`y`.

### Puppeteer

```js
const puppeteer = require('puppeteer');

const API = 'http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID';
const { wsUrl } = await (await fetch(`${API}/start`, { method: 'POST' })).json();
const browser = await puppeteer.connect({ browserWSEndpoint: wsUrl, protocol: 'webDriverBiDi' });
const page = (await browser.pages())[0] ?? await browser.newPage();
await page.goto('https://example.com');

// Option A: standard BiDi input over wsUrl (humanized automatically by the relay when human_cursor is on)
await page.click('a');

// Option B: Camoufox's native engine-level humanize through the runner's human input API
await fetch(`${API}/human/click`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ selector: 'a', page: 'example.com' }),
});
```

### Raw WebDriver BiDi (Python)

See [`tests/check_api.py`](tests/check_api.py) and [`tests/check_human_cursor.py`](tests/check_human_cursor.py). They start a profile, drive it over `wsUrl` and `/human/*`, and then stop and delete the profile.

### Endpoints

GoLogin-compatible:

| Method | Path | Description |
|---|---|---|
| POST | `/browser/start-profile` | Body `{"profileId": "..."}`. Returns `wsUrl` |
| POST | `/browser/stop-profile` | Body `{"profileId": "..."}` |

Native:

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/profiles` | List profiles (state, port, proxy, fingerprint settings). Query: `folder`, `q` |
| GET | `/api/v1/profiles/{id}` | One profile, including its automation `port` while running |
| POST | `/api/v1/profiles` | Create: `{"name", "os", "proxy": "http://u:p@host:port", "human_cursor": {"mode": "on", "max_time": 1.5}, "folder", ...}` |
| PATCH | `/api/v1/profiles/{id}` | Update any field. `proxy` may be a string in Webshare format |
| DELETE | `/api/v1/profiles/{id}` | Delete a profile and its data |
| POST | `/api/v1/profiles/{id}/start` | Start with automation. Query `headless=true`. Returns `{wsUrl, wsEndpoint, port}` |
| POST | `/api/v1/profiles/{id}/stop` | Stop the profile (cookies are saved) |
| POST | `/api/v1/profiles/{id}/human/{move\|click\|scroll\|type\|hover}` | Drive Camoufox's native humanized input (`{x, y}`, `{selector}`, `{deltaY}`, `{text}`, optional `page`) |
| GET | `/api/v1/running` | Running profiles and their endpoints |
| POST | `/api/v1/profiles/{id}/randomize` | New realistic random device and fingerprint |
| POST | `/api/v1/profiles/{id}/cookies` | Queue cookies (JSON array) for the next start |
| GET | `/api/v1/profiles/{id}/cookies` | Export cookies |
| POST | `/api/v1/profiles/import` | `{"text": "name\|proxy\|notes\|folder\|os\|start_url\n..."}` |
| GET | `/api/v1/proxies` | Saved proxies with check results |
| POST | `/api/v1/proxies/import` | `{"text": "one proxy per line"}` |
| GET | `/api/v1/skill/foxlogin.skill` | Download the packaged AI agent skill (`.skill` zip) |
| GET | `/api/v1/skill/SKILL.md` | Download the AI agent skill instructions (`SKILL.md`) |

## Desktop app packaging

FoxLogin can be packaged as a desktop app: an installer, a native window, no Python needed. There are two ways to build it. Both bundle the same Python backend (`app/`) with PyInstaller and differ only in the window around it:

| | pywebview (`packaging/pywebview/`) | Tauri (`packaging/tauri/`) |
|---|---|---|
| Window | pywebview in the same process as the server | Tauri 2 shell (Rust) that starts the backend as a separate process |
| Closing the window | Stops the server | Hides the window; the app stays in the tray/Dock until Quit |
| Toolchain | Python only | Python, Rust, Node.js |
| macOS | `FoxLogin-<ver>-macos-<arm64\|x86_64>.dmg` | `FoxLogin_<ver>_<aarch64\|x64>.dmg` |
| Windows x64 | `FoxLogin-<ver>-windows-x64-setup.exe` (Inno Setup) | `FoxLogin_<ver>_x64-setup.exe` (NSIS) and `.msi` |
| Linux | `FoxLogin-<ver>-linux-<x86_64\|arm64>.AppImage` and `.tar.gz` | `FoxLogin_<ver>_amd64.AppImage` and `.deb` (x86_64 only) |

What both apps have in common:
- **Minimum systems.** macOS 11 or later (Apple Silicon and Intel), Windows 10/11 x64 (Windows 11 ARM runs it through emulation), Linux with glibc 2.28 or later (Ubuntu 20.04+, Debian 11+, RHEL 8+).
- **One instance.** Opening the app a second time brings the first window to the front.
- **First launch.** The app offers to download a Camoufox build, about 1.2 GB, once.
- **Data** lives in the user's app-data folder instead of `./data` (`FOXCLI_DATA` still overrides it):
  - macOS: `~/Library/Application Support/FoxLogin`
  - Windows: `%APPDATA%\FoxLogin`
  - Linux: `~/.local/share/FoxLogin`
- **Running profiles keep running** after the app quits. The next launch adopts them.
- **Unsigned builds.** On macOS, right-click › Open the first time. On Windows, SmartScreen asks for "More info › Run anyway".

PyInstaller cannot cross-compile, so each OS builds its own installers. Output goes to the folders shown below.

### Build with pywebview

Requirements: Python 3.10+ (on macOS, a python.org universal2 build can make both the arm64 and the Intel app). On Windows, [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer (a `.zip` is made without it). On Linux, `appimagetool` on `PATH` for the AppImage (only the `.tar.gz` is made without it).

```bash
python3 packaging/pywebview/build.py                  # this machine's architecture
python3 packaging/pywebview/build.py --arch x86_64    # macOS: Intel build (via Rosetta)
python3 packaging/pywebview/build.py --no-installer   # stop after PyInstaller
```

- The script creates a virtualenv per architecture in `build/`, installs `requirements.txt` plus `packaging/pywebview/requirements-build.txt`, runs PyInstaller with `foxlogin.spec`, then makes the installer in `dist/`.
- Run it from source without packaging: `pip3 install -r requirements.txt -r packaging/pywebview/requirements-build.txt`, then `python3 packaging/pywebview/foxlogin.py` (`--server` for the API only).
- Optional macOS signing: set `FOXLOGIN_SIGN_ID` to a "Developer ID Application" identity (ad-hoc otherwise) and `FOXLOGIN_NOTARY_PROFILE` to a `notarytool` keychain profile to notarize.
- The icon is drawn by `packaging/pywebview/make_icons.py` into `packaging/pywebview/assets/`.

### Build with Tauri

Requirements: Python 3.10+, Rust (`rustup`), Node.js 18+. On Linux also `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`.

```bash
python3 packaging/tauri/build.py            # backend + app + installers for this OS
python3 packaging/tauri/build.py --backend  # only the PyInstaller backend
python3 packaging/tauri/smoke_test.py       # checks the packaged backend
```

- The backend (`packaging/tauri/backend.py`) is built into `packaging/tauri/src-tauri/resources/backend/`, then `npx tauri build` writes the installers to `packaging/tauri/src-tauri/target/release/bundle/`.
- On macOS, set `CI=true` where Finder cannot be scripted (CI, SSH); otherwise the `.dmg` step waits for Finder and times out.
- Builds are ad-hoc signed on macOS. For notarized builds set `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` and `APPLE_TEAM_ID`; on Windows set `bundle.windows.certificateThumbprint` in `tauri.conf.json`.

### CI and releases

`.github/workflows/build.yml` builds both apps on every push to `main` and every pull request: pywebview for macOS arm64/Intel, Windows x64 and Linux x86_64/arm64, Tauri for macOS arm64/Intel, Windows x64 and Linux x86_64. Each build runs a smoke test and uploads its installers as workflow artifacts.

Every push to `main` publishes a release. The workflow's `version` job runs `packaging/release.py patch` on the newest `main`: it bumps the patch version in every version file, commits `Release X.Y.Z` as `github-actions[bot]`, tags `vX.Y.Z` and pushes both. Both apps are then built from that tag and published as one GitHub Release (the Tauri installers are named `FoxLogin-Tauri_…`). Run `git pull` before your next push to pick up the release commit. Put `[skip release]` in a commit message to build without releasing, or `[skip ci]` to skip the workflow.

For a minor or major release, run the script yourself on `main` with everything committed:

```bash
python3 packaging/release.py minor        # or major, patch, or an explicit 1.2.3; --dry-run to preview
```

It writes the version into `app/core.py`, `packaging/pywebview/foxlogin.spec`, `packaging/pywebview/windows/foxlogin.iss`, `packaging/tauri/package.json` (+ lock), `packaging/tauri/src-tauri/Cargo.toml` (+ lock) and `packaging/tauri/src-tauri/tauri.conf.json`, commits `Release X.Y.Z`, tags `vX.Y.Z` and pushes both; CI does not bump again for a `Release …` commit. CI runs `release.py --check` against the tag before building. If a tag's build failed before any Release was published, fix the cause and rerun with `--retag` to move the tag.

## Project layout

```
FoxLogin/
├── run.py               # entry point: python3 run.py -> http://127.0.0.1:8765
├── start.command        # macOS double-click launcher
├── requirements.txt
├── packaging/
│   ├── pywebview/       # desktop app with a pywebview window (build.py, PyInstaller spec, installers)
│   └── tauri/           # desktop app with a Tauri shell (backend.py, src-tauri/, build.py)
├── app/
│   ├── server.py        # FastAPI app: UI, REST API, BiDi websocket proxy
│   ├── core.py          # profile storage, fingerprint generation, Camoufox launch options
│   ├── humanize.py      # humanized mouse/wheel/key actions for the BiDi relay
│   ├── updater.py       # app updates from GitHub Releases
│   ├── runner.py        # runs one profile's browser in its own process
│   └── static/          # single-page UI (index.html, app.js, style.css) and fptest.html
├── tests/
│   ├── check_marks.py   # 27 checks: each mask changes exactly what it should
│   ├── check_api.py     # REST start/stop + WebDriver BiDi automation
│   ├── check_human_cursor.py  # BiDi relay + native /human/* cursor checks (on vs off)
│   └── check_sites.py   # opens pixelscan / iphey / browserscan / creepjs and screenshots them
├── docs/
│   ├── screenshots/     # images used in this README
│   └── logs/            # raw output of the test runs below
└── data/                # (git-ignored) profiles, proxies, settings
```

Each profile lives in `data/profiles/<id>/`:

| File | Content |
|---|---|
| `profile.json` | Settings shown in the UI |
| `fingerprint.json.gz` | The fingerprint that pins the identity |
| `userdata/` | The persistent Firefox profile (cookies, storage, ...) |
| `applied.json` | What the browser actually presented on its last launch |
| `cookies_import.json` | Cookies queued for the next launch |

## Testing

Start the server first, then run the checks:

```bash
python3 run.py &
python3 tests/check_marks.py                       # 27 checks: masks change what they should, and only that
pip3 install websockets && python3 tests/check_api.py   # REST API + WebDriver BiDi automation
python3 tests/check_human_cursor.py                # humanized cursor over BiDi relay and /human/* API
python3 tests/check_sites.py <profile_id> out_dir  # pixelscan, iphey, browserscan, creepjs (screenshots)
```

- `check_marks.py` and `check_api.py` only use throwaway profiles. `check_marks.py` stores them in a temporary `FOXCLI_DATA` directory, and `check_api.py` deletes its profile when it finishes.
- `check_marks.py` loads the **`/fptest`** page from the running server.
- Set `FOXCLI_URL` to point `check_api.py` at another port.

## Test results (evidence)

All results below come from one run on **2026-10-18** on macOS (Apple Silicon), Camoufox 0.5.8 / Firefox 156.0. The UI screenshots come from a separate, clean instance (`FOXCLI_DATA=<tmp> FOXCLI_PORT=8766`) seeded with demo profiles. The proxies on the Proxies screenshot are documentation-range placeholders (RFC 5737).

### 1. Fingerprint mask checks: **27 / 27 PASS**

`tests/check_marks.py` launches seven browsers:

- **A** and **B** are fully masked.
- **A2** is A relaunched.
- **R1** and **R2** have every mask set to *Real*.
- **W1** and **W2** are Windows identities.

The test asserts that:

- masked values differ between profiles and from the real host;
- real values match the host;
- stable values (GPU, audio, media devices, fonts, UA) survive a relaunch;
- Canvas noise stays stable within one session;
- WebGL noise never touches solid-colour buffers.

![check_marks output](docs/screenshots/test-check-marks.png)

Raw log: [`docs/logs/check_marks.txt`](docs/logs/check_marks.txt)

### 2. REST API + WebDriver BiDi automation: **3 / 3 PASS**

`tests/check_api.py` runs the full flow end to end:

1. creates a Windows profile;
2. starts it headless through `POST /api/v1/profiles/{id}/start`;
3. connects to the returned `wsUrl`;
4. loads `https://example.com` over BiDi and reads `navigator.*`;
5. stops the profile through the GoLogin-compatible `POST /browser/stop-profile`.

`navigator.webdriver` is `false`, and the browser reports a Windows UA and `Win32` platform even though it runs on a Mac.

![check_api output](docs/screenshots/test-check-api.png)

Raw log: [`docs/logs/check_api.txt`](docs/logs/check_api.txt)

### 3. Built-in fingerprint self-test (`/fptest`)

This is the self-test page from a masked **Windows** profile, launched on a Mac. It shows:

- a Windows UA and `Win32` platform;
- a Direct3D (ANGLE) GPU;
- Canvas and WebGL hashes that are specific to this profile;
- `deviceMemory` not exposed, as on real Firefox;
- a masked media-device count.

![fptest in Camoufox](docs/screenshots/fptest-camoufox-windows.png)

### 4. Third-party fingerprint checkers

`tests/check_sites.py` ran a fresh macOS profile through an HTTP proxy, using the same launch options as the **Run** button. Before each screenshot, a script replaced every IP address on the page with `[IP redacted]`. Nothing else on the pages was changed.

| Site | Result |
|---|---|
| **iphey.com** | **"Your Digital Identity Looks Trustworthy"**: Browser ✔, Location ✔, IP ✔, Hardware ✔, Software ✔ |
| **browserscan.net** | **Browser fingerprint authenticity: 100%**, Bot detection: No, Proxy: No. The timezone, language and geolocation follow the proxy (Europe/London, en-GB) |
| **pixelscan.net** | Browser *Firefox 156 on Mac OS*, Fingerprint: **No masking detected**. *Proxy detected* is about the IP itself (a datacenter "hosting" IP), not about the browser. The *Bot check* tile was still at "Collecting Data…" after 70 s, so it is reported as not completed |
| **CreepJS** | `chromium: false`, **0% headless, 0% stealth** (6% "like headless"). The Worker scope reports the same GPU (Apple M1) and the same timezone as the main page, so nothing is inconsistent |

| iphey | browserscan |
|---|---|
| ![iphey](docs/screenshots/site-iphey.png) | ![browserscan](docs/screenshots/site-browserscan.png) |

| pixelscan | CreepJS |
|---|---|
| ![pixelscan](docs/screenshots/site-pixelscan.png) | ![creepjs](docs/screenshots/site-creepjs.png) |

## Known limitations

- **No RAM value.** `navigator.deviceMemory` does not exist in Firefox, so there is nothing to spoof.
- **CPU thread count is not spoofed.** It always matches the real CPU, because Worker timing would expose a fake value.
- **WebGL image noise is Off by default.** pixelscan detects read-back noise.
- **No Playwright `connect()`.** It cannot attach to a running profile. Use Puppeteer (`protocol: 'webDriverBiDi'`), Selenium 4 or another BiDi client.
- **Proxy detection depends on the IP.** Datacenter proxies are flagged as proxies by IP-reputation checks, whatever the browser does. Use residential or mobile proxies if that matters.

## License

FoxLogin is released under the [MIT License](LICENSE).

FoxLogin downloads and launches [Camoufox](https://github.com/daijro/camoufox), a Firefox-based browser licensed under **MPL-2.0**. The `camoufox` Python package it uses is MIT-licensed. Neither is included in this repository. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for every dependency and its license.

## Disclaimer

FoxLogin is intended for legitimate uses such as managing your own accounts, QA and testing, web-scraping research, and privacy protection. You are responsible for following the terms of service of the websites you visit and the laws that apply to you.
