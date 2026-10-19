# FoxLogin

**A local, GoLogin-style browser profile manager built on the [Camoufox](https://camoufox.com) engine (Firefox).**

FoxLogin runs on your own machine as a small web app. You can create any number of browser profiles. Each profile has its own consistent fingerprint, its own proxy, and its own cookies and Firefox storage. You can run profiles by hand or automate them through a GoLogin-compatible REST API that uses WebDriver BiDi.

> 🇻🇳 Vietnamese version: [README.vi.md](README.vi.md)

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

This page lists every endpoint, with ready-to-copy code snippets that already contain the selected profile's ID.

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

## Automation API

Camoufox is Firefox, so automation uses **WebDriver BiDi**:

- Puppeteer, Selenium 4 and any other BiDi client work, and `navigator.webdriver` stays `false`.
- Playwright `connect()` **cannot** attach to a running profile.
- Profiles started with the **Run** button do not open an automation port. Use the API to start them instead.

### Puppeteer

```js
const puppeteer = require('puppeteer');

const { wsUrl } = await (await fetch(
  'http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/start', { method: 'POST' })).json();
const browser = await puppeteer.connect({ browserWSEndpoint: wsUrl, protocol: 'webDriverBiDi' });
const page = (await browser.pages())[0] ?? await browser.newPage();
await page.goto('https://example.com');
```

### Raw WebDriver BiDi (Python)

See [`tests/check_api.py`](tests/check_api.py). It starts a profile, sends `session.new`, `browsingContext.navigate` and `script.evaluate` over the `wsUrl`, and then stops the profile.

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
| POST | `/api/v1/profiles` | Create: `{"name", "os", "proxy": "http://u:p@host:port", "folder", ...}` |
| PATCH | `/api/v1/profiles/{id}` | Update any field. `proxy` may be a string in Webshare format |
| DELETE | `/api/v1/profiles/{id}` | Delete a profile and its data |
| POST | `/api/v1/profiles/{id}/start` | Start with automation. Query `headless=true`. Returns `{wsUrl, wsEndpoint, port}` |
| POST | `/api/v1/profiles/{id}/stop` | Stop the profile (cookies are saved) |
| GET | `/api/v1/running` | Running profiles and their endpoints |
| POST | `/api/v1/profiles/{id}/randomize` | New realistic random device and fingerprint |
| POST | `/api/v1/profiles/{id}/cookies` | Queue cookies (JSON array) for the next start |
| GET | `/api/v1/profiles/{id}/cookies` | Export cookies |
| POST | `/api/v1/profiles/import` | `{"text": "name\|proxy\|notes\|folder\|os\|start_url\n..."}` |
| GET | `/api/v1/proxies` | Saved proxies with check results |
| POST | `/api/v1/proxies/import` | `{"text": "one proxy per line"}` |

## Desktop app packaging

The plan for shipping FoxLogin as an installable desktop app for macOS, Windows and Linux is in [docs/PACKAGING.md](docs/PACKAGING.md).

The `desktop-tauri` branch builds that app with a [Tauri](https://tauri.app) shell around the same Python backend. See [docs/PACKAGING-TAURI.md](docs/PACKAGING-TAURI.md) for its design, build steps and test results.

## Project layout

```
FoxLogin/
├── run.py               # entry point: python3 run.py -> http://127.0.0.1:8765
├── start.command        # macOS double-click launcher
├── requirements.txt
├── app/
│   ├── server.py        # FastAPI app: UI, REST API, BiDi websocket proxy
│   ├── core.py          # profile storage, fingerprint generation, Camoufox launch options
│   ├── runner.py        # runs one profile's browser in its own process
│   └── static/          # single-page UI (index.html, app.js, style.css) and fptest.html
├── tests/
│   ├── check_marks.py   # 27 checks: each mask changes exactly what it should
│   ├── check_api.py     # REST start/stop + WebDriver BiDi automation
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
