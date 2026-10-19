//! FoxLogin desktop shell.
//!
//! Starts the Python backend (`foxlogin-backend --server --port N`) on a free
//! port, shows a loading page until http://127.0.0.1:N answers, then points the
//! window at it. Closing the window hides it and the server keeps running in
//! the tray; Quit stops the server. Running profiles live in their own process
//! sessions, so they outlive both and are adopted again on the next start.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::webview::{DownloadEvent, NewWindowResponse};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_opener::OpenerExt;

/// The backend process and the port it serves on.
struct Backend {
    child: Mutex<Option<Child>>,
    port: u16,
}

/// Debug builds only: `FOXLOGIN_SELFTEST=<port>` drives the real webview (UI
/// loaded, cookie download + toast) and reports each step to 127.0.0.1:<port>.
#[cfg(debug_assertions)]
const SELFTEST_JS: &str = r#"
(async () => {
  // each step reports to the probe port given in FOXLOGIN_SELFTEST
  const say = (step, data) => fetch('http://127.0.0.1:__PROBE__/' + step + '?' + new URLSearchParams(data || {}), { mode: 'no-cors' }).catch(() => {});
  const wait = (ms) => new Promise(res => setTimeout(res, ms));
  say('ui', { nav: !!document.querySelector('#nav'), ask: typeof ask, ua: navigator.userAgent });
  const p = await (await fetch('/api/v1/profiles', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name: 'selftest' }) })).json();
  const a = document.createElement('a');
  a.href = '/api/profiles/' + p.id + '/cookies/export'; a.download = 'cookies-selftest.json';
  document.body.appendChild(a); a.click();
  await wait(2500);
  say('after-download', { toast: [...document.querySelectorAll('.toast')].map(t => t.textContent).join(' | ') });
  say('done');
})();
"#;

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

/// `FOXLOGIN_BACKEND="python3 packaging/tauri/backend.py"` runs the backend from
/// source (development); otherwise the PyInstaller build bundled as a resource.
fn backend_command(app: &AppHandle) -> Command {
    if let Ok(cmdline) = std::env::var("FOXLOGIN_BACKEND") {
        let mut parts = cmdline.split_whitespace();
        let mut cmd = Command::new(parts.next().unwrap_or("python3"));
        cmd.args(parts);
        return cmd;
    }
    let dir: PathBuf = app
        .path()
        .resource_dir()
        .map(|d| d.join("backend"))
        .unwrap_or_default();
    let exe = if cfg!(windows) { "foxlogin-backend.exe" } else { "foxlogin-backend" };
    let mut cmd = Command::new(dir.join(exe));
    cmd.current_dir(&dir);
    cmd
}

fn spawn_backend(app: &AppHandle, port: u16) -> std::io::Result<Child> {
    let mut cmd = backend_command(app);
    cmd.args(["--server", "--port", &port.to_string()])
        .env("FOXCLI_NO_OPEN", "1")
        .env("FOXLOGIN_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::null());
    if !cfg!(debug_assertions) {
        // the backend writes its own log to <data>/logs/app.log
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn()
}

/// True once GET /api/meta answers 200.
fn backend_ready(port: u16) -> bool {
    let Ok(mut s) = TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_millis(300)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    if s.write_all(b"GET /api/meta HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n").is_err() {
        return false;
    }
    let mut head = [0u8; 16];
    matches!(s.read(&mut head), Ok(n) if n >= 12 && head[9..12] == *b"200")
}

fn stop_backend(app: &AppHandle) {
    if let Some(b) = app.try_state::<Backend>() {
        if let Some(mut child) = b.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn downloads_dir(app: &AppHandle) -> PathBuf {
    app.path()
        .download_dir()
        .or_else(|_| app.path().home_dir())
        .unwrap_or_else(|_| std::env::temp_dir())
}

/// `cookies.json` -> `cookies (1).json` ... when the name is taken, like browsers do.
fn unique_path(path: PathBuf) -> PathBuf {
    if !path.exists() {
        return path;
    }
    let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let ext = path.extension().map(|e| format!(".{}", e.to_string_lossy())).unwrap_or_default();
    (1..)
        .map(|i| path.with_file_name(format!("{stem} ({i}){ext}")))
        .find(|p| !p.exists())
        .unwrap_or(path)
}

fn build_window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    let opener = app.clone();
    let dl = app.clone();
    WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title("FoxLogin")
        .inner_size(1380.0, 880.0)
        .min_inner_size(980.0, 620.0)
        // target=_blank links and window.open (e.g. Fingerprint self-test) open in the default browser
        .on_new_window(move |url, _features| {
            let _ = opener.opener().open_url(url.as_str(), None::<&str>);
            NewWindowResponse::Deny
        })
        .on_download(move |webview, event| {
            match event {
                DownloadEvent::Requested { url, destination } => {
                    // Keep the server's file name (Content-Disposition) when the webview provides one
                    let name = destination
                        .file_name()
                        .map(|n| n.to_owned())
                        .or_else(|| url.path_segments().and_then(|s| s.last()).map(Into::into))
                        .unwrap_or_else(|| "download".into());
                    *destination = unique_path(downloads_dir(&dl).join(name));
                }
                DownloadEvent::Finished { path, success, .. } => {
                    let msg = match (success, path) {
                        (true, Some(p)) => format!("Saved to {}", p.display()),
                        // WKWebView does not report the path; it is the one set on Requested
                        (true, None) => "Saved to the Downloads folder".to_string(),
                        (false, _) => "Download failed".to_string(),
                    };
                    let js = format!("typeof toast === 'function' && toast({:?})", msg);
                    let _ = webview.eval(&js);
                }
                _ => {}
            }
            true
        })
        .build()
}

fn main() {
    let app = tauri::Builder::default()
        // A second launch only brings the running window to the front
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let port = free_port();
            let child = spawn_backend(&handle, port);
            let spawn_error = child.as_ref().err().map(|e| e.to_string());
            app.manage(Backend { child: Mutex::new(child.ok()), port });

            let window = build_window(&handle)?;
            window.on_window_event({
                let w = window.clone();
                move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        // Keep the server (and the tray) alive; Quit really exits
                        api.prevent_close();
                        let _ = w.hide();
                    }
                }
            });

            let open = MenuItem::with_id(app, "open", "Open FoxLogin", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit FoxLogin", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().cloned().expect("bundle icon"))
                .tooltip("FoxLogin")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => show_main(app),
                    "quit" => {
                        stop_backend(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            thread::spawn(move || {
                let fail = |text: String| {
                    if let Some(w) = handle.get_webview_window("main") {
                        let _ = w.eval(&format!("window.foxloginError({:?})", text));
                    }
                };
                if let Some(e) = spawn_error {
                    return fail(format!("The backend could not be started: {e}"));
                }
                let port = handle.state::<Backend>().port;
                let deadline = Instant::now() + Duration::from_secs(90);
                while Instant::now() < deadline {
                    if backend_ready(port) {
                        if let (Some(w), Ok(url)) = (
                            handle.get_webview_window("main"),
                            url::Url::parse(&format!("http://127.0.0.1:{port}/")),
                        ) {
                            let _ = w.navigate(url);
                            #[cfg(debug_assertions)]
                            if std::env::var_os("FOXLOGIN_SELFTEST").is_some() {
                                thread::sleep(Duration::from_secs(4));
                                let _ = w.set_always_on_top(true); // an occluded WKWebView throttles timers
                                let probe = std::env::var("FOXLOGIN_SELFTEST").unwrap_or_default();
                                let _ = w.eval(SELFTEST_JS.replace("__PROBE__", &probe));
                            }
                        }
                        return;
                    }
                    let exited = handle
                        .state::<Backend>()
                        .child
                        .lock()
                        .unwrap()
                        .as_mut()
                        .map(|c| matches!(c.try_wait(), Ok(Some(_))))
                        .unwrap_or(true);
                    if exited {
                        return fail("The backend exited during start-up. See logs/app.log in the FoxLogin data folder.".into());
                    }
                    thread::sleep(Duration::from_millis(150));
                }
                fail("The backend did not answer within 90 seconds.".into());
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building FoxLogin");

    app.run(|app, event| match event {
        // macOS: clicking the Dock icon brings the hidden window back
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_main(app),
        RunEvent::Exit => stop_backend(app),
        _ => {}
    });
}
