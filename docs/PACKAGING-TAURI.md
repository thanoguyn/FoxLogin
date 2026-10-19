# Desktop app with Tauri

`packaging/tauri/` packages FoxLogin as an installable desktop app. The window is a [Tauri 2](https://tauri.app) shell and the Python backend is unchanged. It is built alongside the pywebview app in [PACKAGING.md](PACKAGING.md). The web version (`python3 run.py`) keeps working as before.

## How it fits together

```
FoxLogin.app / FoxLogin.exe            Tauri shell (Rust, packaging/tauri/src-tauri)
 ├─ window (WKWebView / WebView2 / WebKitGTK) -> http://127.0.0.1:<random port>/
 ├─ tray icon: Open FoxLogin · Quit FoxLogin
 └─ Resources/backend/foxlogin-backend   PyInstaller one-dir build of packaging/tauri/backend.py
      ├─ --server --port N   FastAPI UI + REST API          (started by the shell)
      ├─ --runner <id>       one profile's Camoufox browser (started by the server, own session)
      └─ --camoufox <args>   camoufox CLI (install/update browser cores from Settings)
```

**Start-up**
- The shell picks a free port and starts `foxlogin-backend --server --port N`.
- A loading page shows until `/api/meta` answers, then the window switches to the UI.

**Closing and quitting**
- **Closing the window** only hides it. The server keeps running and the app stays in the tray, or in the Dock on macOS. Clicking the Dock icon or choosing *Open FoxLogin* brings the window back.
- **Quit** (tray menu or ⌘Q) stops the server.
- **Running profiles** live in their own process sessions, so they keep running after Quit. The next launch adopts them.
- **If the shell is killed** without a chance to clean up, the backend notices that its parent is gone (`FOXLOGIN_PARENT_PID`) and exits within about 2 s.

**One instance only**
- Opening the app a second time just brings the first window to the front (`tauri-plugin-single-instance`).

**Links and downloads**
- `target=_blank` links and `window.open` (for example *Fingerprint self-test*) open in the default browser (`on_new_window`).
- Downloads (cookie export) go to the Downloads folder. A name that is already taken gets ` (1)`, ` (2)`, … appended, and a toast confirms the save.

**Data folder**
- In the installed app, data lives in the user's app-data folder:
  - macOS: `~/Library/Application Support/FoxLogin`
  - Windows: `%APPDATA%\FoxLogin`
  - Linux: `~/.local/share/FoxLogin`
- `FOXCLI_DATA` overrides it.

## Changes outside `packaging/tauri/`

**Shared with the pywebview branch** (copied verbatim, so the two branches merge cleanly):
- `core.FROZEN`, `_default_data()`, `self_cmd()`, `popen_kwargs()`, `runner_alive()`, `stop_runner()`
- the runner's `stop.flag` (Windows has no SIGTERM to catch)
- `runner.cli()`
- the `/api/app` endpoints

**Specific to this branch**

| Change | Why |
|---|---|
| `confirm()` replaced by an in-page `ask()` modal (`app.js`) | WKWebView in Tauri does not implement `window.confirm`. It silently returns `false`, so Delete, Reset and Remove would do nothing. The modal works in every browser and webview |
| `websockets` added to `requirements.txt` | Uvicorn needs it for the `/ws/<id>` automation proxy. A clean install had no WebSocket support, so `wsUrl` returned 404. It only worked before because `websockets` happened to be installed globally |
| `psutil`, `platformdirs` added to `requirements.txt` | Used by the shared process and data-folder helpers |
| `install_dock_hook()` leaves an equal or newer `FOXCLI-DOCK-BADGE` block alone | Several FoxLogin builds share the Camoufox cache. An older build must not rewrite a newer build's hook |
| The fpgen model is installed at build time (`build.py`) | Camoufox downloads its pinned fpgen model into the package folder on first use. Inside an installed app that folder is read-only, so the model is bundled, with the 2100-01-01 date Camoufox gives it |

## Building

Requirements:
- Python 3.10+
- Rust (`rustup`)
- Node.js 18+
- Linux only: `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`

```bash
python3 packaging/tauri/build.py          # backend + app + installers for this OS
python3 packaging/tauri/build.py --backend
python3 packaging/tauri/smoke_test.py     # checks the packaged backend
```

Output goes to `packaging/tauri/src-tauri/target/release/bundle/`:

| OS | Files |
|---|---|
| macOS | `FoxLogin.app`, `FoxLogin_<ver>_<arch>.dmg` (≈79 MB, app ≈215 MB) |
| Windows | `.msi` and NSIS `-setup.exe` (per-user install, no admin) |
| Linux | `.AppImage`, `.deb`, `.rpm` |

On macOS, set `CI=true` when building where Finder cannot be scripted (CI, SSH). Otherwise `create-dmg` waits for Finder and times out.

### CI

The `tauri` job in `.github/workflows/build.yml` runs next to the pywebview build on every push to `main` and every pull request, and can also be started by hand. It builds on four machines:
- macOS arm64 (`macos-14`)
- macOS x64 (`macos-15-intel`)
- Windows x64
- Linux x64

Each build runs the smoke test and uploads its installers as artifacts. A `v*` tag publishes them in the same GitHub Release as the pywebview installers, renamed `FoxLogin-Tauri_<version>_…` to tell them apart.

### Signing

- **macOS.** Builds are ad-hoc signed (`signingIdentity: "-"`), so the bundle is sealed and macOS does not report the app as "damaged". It is not notarized, so on first launch the user needs right-click › Open (or System Settings › Privacy & Security › Open Anyway). For a seamless install, set `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` and `APPLE_TEAM_ID` in CI, which needs an Apple Developer account.
- **Windows.** Unsigned builds show a SmartScreen warning. Set `bundle.windows.certificateThumbprint`, or use Azure Trusted Signing.

## Test results (macOS 26, Apple Silicon, 2026-10-18)

All runs below used a temporary data folder (`FOXCLI_DATA`) and random ports. They never touched the user's own profiles or the port-8765 instances.

| Test | Result |
|---|---|
| `tests/check_api.py` against the backend **inside the signed `.app`** (REST start → WebDriver BiDi → stop) | 3/3 PASS |
| `packaging/tauri/smoke_test.py` (packaged backend: UI, create / list / delete profile, runner mode) | 6/6 PASS |
| Quit the app while a profile runs → profile keeps running → relaunch adopts it (new port, `wsUrl` updated) → Stop saves cookies | PASS |
| Second launch exits right away and no second backend starts (bringing the first window to the front was not checked: no screen access) | PASS |
| Signed **`.app` bundle** (hardened runtime, debug build): WKWebView loads the UI from the backend, cookie export reaches `~/Downloads`, toast shown | PASS |
| Shell killed with SIGKILL → backend exits on its own | PASS |
| Real WKWebView, scripted self-test (bare debug binary, `FOXLOGIN_SELFTEST`): UI loaded, cookie export saved to `~/Downloads`, a taken name becomes `… (1).json`, toast "Saved to the Downloads folder" | PASS |
| In-page `ask()` modal (Chrome): shown, Cancel keeps the profile, OK deletes it | PASS |
| `codesign --verify --deep --strict` on the app, before and after running it | valid |
| Backend start-up | 0.9 s (about 15 s on the very first launch after install, while macOS scans the new binaries) |

**Not verified on this machine.** This session has no Screen Recording or Accessibility permission, so there are no screenshots of the Tauri window and no real mouse clicks. WKWebView ignores pop-ups opened by script, so the `target=_blank` → default-browser path still needs one manual click to confirm. Windows and Linux builds are only exercised in CI.
