# Kế hoạch: đóng gói FoxLogin thành app desktop (macOS, Windows, Linux)

Mục tiêu: người dùng tải một file cài đặt, cài xong mở như app bình thường. App hiện trong cửa sổ riêng (không phải tab trình duyệt) và không cần cài Python, pip hay chạy lệnh.

## 0. Trạng thái (nhánh `packaging`)

Đã làm:
- `foxlogin.py` là một file thực thi chạy được nhiều chế độ: cửa sổ app, `--server`, `--runner`, `--camoufox`.
- Cửa sổ app viết trong `app/desktop.py`, dùng pywebview. Mỗi lúc chỉ chạy một phiên: mở app lần hai thì cửa sổ cũ được đưa lên trước. Nếu port 8765 đã bị chương trình khác chiếm, app tự chọn port khác. Nếu không mở được cửa sổ native, app mở giao diện trong trình duyệt mặc định.
- Dữ liệu nằm trong thư mục app-data của người dùng. Bản chạy từ mã nguồn vẫn dùng `./data`.
- Quản lý tiến trình chạy được trên cả ba hệ điều hành:
  - Kiểm tra tiến trình bằng `psutil`.
  - Dừng profile bằng file `stop.flag`, rồi mới tắt cưỡng bức nếu cần.
  - Tiến trình con có session riêng, không mở cửa sổ console.
- Lần đầu mở app có màn hình cài core Camoufox.
- `packaging/foxlogin.spec` cho PyInstaller và `packaging/build.py` để build venv riêng theo từng kiến trúc rồi tạo bộ cài: dmg, Inno Setup, AppImage.
- Icon tạm nằm ở `packaging/make_icons.py`.
- GitHub Actions build đủ 5 bản: macOS arm64/Intel, Windows x64, Linux x86_64/arm64, cùng 4 bản Tauri (xem [PACKAGING-TAURI.md](PACKAGING-TAURI.md)). Mỗi bản có smoke test; push tag `v*` thì tự tạo một Release chứa cả hai.
- Ra bản mới: sửa version ở `app/core.py`, `packaging/foxlogin.spec`, `packaging/windows/foxlogin.iss`, `packaging/tauri/package.json`, `packaging/tauri/src-tauri/Cargo.toml` và `tauri.conf.json`, rồi push tag `vX.Y.Z` (CI kiểm tra tag khớp `app/core.py`).

Đã kiểm tra trên máy dev (macOS Apple Silicon):
- Bản arm64 build xong:
  - Cửa sổ app hiển thị đúng.
  - Mở app lần hai thì cửa sổ cũ được đưa lên trước.
  - Chạy và dừng profile được.
  - Runner không hiện icon trên Dock.
- Bản Intel build qua Rosetta.
- GitHub Actions build xanh cả 5 bản. Windows và Linux mới qua smoke test trên CI (server khởi động, tạo profile), chưa chạy thử trên máy thật.

Hệ điều hành tối thiểu:
- **macOS 11:** pip bị ép chọn các package build cho macOS 11. `indexed_zstd` được tự build kèm zstd nhúng tĩnh. Driver Playwright dùng Node 22 vì Node 24 đòi macOS 13.5.
- **Windows 10/11 x64:** Windows 11 ARM chạy bản x64 qua giả lập.
- **Linux glibc 2.28:** dùng Qt WebEngine 6.7.

Chưa làm: ký số và notarize (cần chứng thư), overlay số profile trên taskbar Windows, icon trên khay hệ thống, auto-update.

## 1. Chọn công nghệ

| Phương án | Cách làm | Ưu | Nhược |
|---|---|---|---|
| **A. pywebview + PyInstaller** (đề xuất) | Giữ nguyên backend Python. pywebview mở cửa sổ native (WKWebView trên macOS, WebView2 trên Windows, WebKitGTK trên Linux) trỏ vào server nội bộ | Dùng lại 100% code hiện tại; file cài ~150–250 MB | Linux cần WebKitGTK (đa số distro có sẵn) |
| B. Tauri / Electron + Python sidecar | Giao diện chạy trong Tauri/Electron, backend là file thực thi PyInstaller chạy kèm | Có sẵn auto-update và menu tray | Thêm một toolchain (Rust hoặc Node); Electron nặng thêm ~150 MB |

Chọn **A**. Chỉ chuyển sang B nếu sau này cần auto-update phức tạp hoặc khay hệ thống đẹp hơn.

## 2. Thay đổi kiến trúc cần làm trước khi đóng gói

1. **Một file thực thi, nhiều chế độ.** App sau khi đóng gói không có `python -m app.runner`, nên chính file `FoxLogin` tự gọi lại chính nó:
   - `FoxLogin`: mở server ở thread nền và một cửa sổ pywebview.
   - `FoxLogin --runner <id> [--port N]`: chạy một profile (thay cho `python -m app.runner`).
   - `FoxLogin --server`: chỉ chạy API, không mở cửa sổ (cho máy chủ hoặc automation).
   - `FoxLogin --camoufox fetch …`: thay cho `python -m camoufox` khi cài core.
   - Trong `server.py`, `start_profile` và job cài browser đổi `[sys.executable, "-m", …]` thành `[sys.executable, "--runner", …]` khi `sys.frozen`.
2. **Thư mục dữ liệu.** Bundle app là chỉ-đọc, nên `data/` chuyển sang thư mục dữ liệu của user (dùng `platformdirs`):
   - macOS: `~/Library/Application Support/FoxLogin`
   - Windows: `%APPDATA%\FoxLogin`
   - Linux: `~/.local/share/FoxLogin`
   - Lần đầu chạy tự chép `./data` cũ sang. Biến `FOXCLI_DATA` vẫn dùng được để ghi đè.
3. **Không nhét Camoufox vào bộ cài.** Mỗi bản Camoufox ≈1,2 GB, nên lần đầu mở app sẽ hiện màn hình "Cài core":
   - Tải bản stable mới nhất, có thanh tiến trình (dùng job cài browser đang có ở Settings).
   - Tải kèm GeoIP, fpgen và addon uBlock vào cache của Camoufox.
   - Có nút chọn thư mục cache cho máy ít dung lượng ổ hệ thống.
4. **Playwright.** Chỉ cần driver Node của Playwright (≈100 MB, PyInstaller gom được qua hook có sẵn), không cần Chromium/Firefox của Playwright.
5. **Quản lý tiến trình đa nền tảng**:
   - Windows không có `SIGTERM`. `os.kill(pid, 0)` trên Windows sẽ **giết** tiến trình chứ không chỉ kiểm tra. Thay bằng `psutil.pid_exists` và `psutil.Process.terminate()`.
   - Runner nhận lệnh dừng qua một file cờ `stop` hoặc qua HTTP, thay cho signal.
   - Trên Windows, runner chạy với `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` để không bật cửa sổ console.
6. **Cửa sổ và vòng đời**:
   - Đóng cửa sổ app **không** tắt profile đang chạy (giống hiện tại). Server vẫn chạy nền với icon ở menu bar/khay (pystray) và mục "Mở FoxLogin" / "Thoát hẳn".
   - Chạy một phiên duy nhất: mở app lần hai thì gọi API của phiên đang chạy để focus cửa sổ cũ.
   - Port 8765 bị chiếm thì tự chọn port khác. Port cho automation cấu hình được trong Settings.
7. **Icon trên Dock/taskbar**:
   - macOS: giữ `hide_dock_icon()` cho runner. Runner trong bản đóng gói chính là FoxLogin.app, nên không ẩn thì mỗi profile sẽ thêm một icon FoxLogin.
   - Windows: số profile hiển thị bằng *overlay icon* trên taskbar (`ITaskbarList3::SetOverlayIcon`, Firefox có `nsIWinTaskbar`), làm tương tự hook `camoufox.cfg` hiện có cho macOS.
   - Linux: thêm số vào tiêu đề cửa sổ.

## 3. Build từng hệ điều hành

PyInstaller không build chéo được, nên mỗi OS phải build trên chính OS đó, qua GitHub Actions matrix:

| Runner CI | Kết quả | Công cụ |
|---|---|---|
| `macos-14` (Apple Silicon) và `macos-13` (Intel), hoặc build `universal2` | `FoxLogin.app` → `FoxLogin-x.y.z.dmg` | PyInstaller `--windowed --onedir`, `create-dmg` |
| `windows-latest` | `FoxLogin-Setup-x.y.z.exe` | PyInstaller `--onedir` + Inno Setup (tạo shortcut Start Menu/Desktop, gỡ cài đặt sạch) |
| `ubuntu-22.04` | `FoxLogin-x.y.z.AppImage` (+ `.deb`) | PyInstaller + `appimagetool`; `.deb` qua `fpm`, khai báo phụ thuộc `libwebkit2gtk-4.1` |

- Dùng `--onedir`, không dùng `--onefile`: khởi động nhanh hơn, mỗi runner không phải giải nén lại, ít bị antivirus nghi ngờ.
- Mỗi lần build chạy smoke test: mở app ở chế độ `--server`, tạo profile, chạy headless, gọi `/api/v1/profiles/{id}/start` và `/stop`, rồi `tests/check_marks.py`.

## 4. Ký số (để "cài là chạy", không bị chặn)

- **macOS**:
  - Cần tài khoản Apple Developer (99 USD/năm): ký bằng Developer ID, rồi notarize bằng `notarytool` và staple vào `.dmg`.
  - Không ký thì người dùng phải chuột phải › Open, hoặc vào System Settings › Privacy & Security để cho phép.
  - App cần `NSCameraUsageDescription` và `NSMicrophoneUsageDescription`, nếu thiếu thì macOS sẽ chặn hoặc treo `getUserMedia`.
- **Windows**:
  - Không có chứng thư code-signing thì SmartScreen hiện "Windows protected your PC".
  - Chứng thư OV (~200–400 USD/năm) cần thời gian tích uy tín; EV hoặc Azure Trusted Signing hết cảnh báo nhanh hơn.
- **Linux**: không cần ký. AppImage chạy được ngay sau `chmod +x`.

## 5. Cập nhật app

- Giai đoạn 1: khi mở app, kiểm tra GitHub Releases; có bản mới thì hiện thông báo kèm link tải.
- Giai đoạn 2 (tuỳ chọn): auto-update thật bằng Sparkle (macOS) và WinSparkle (Windows), hoặc chuyển sang phương án B.
- Core Camoufox vẫn cập nhật độc lập trong Settings như hiện tại.

## 6. Lộ trình và ước lượng

| Giai đoạn | Việc | Ước lượng |
|---|---|---|
| 1 | Entry point đa chế độ, thư mục dữ liệu user, quản lý tiến trình bằng psutil, cửa sổ pywebview, single-instance | 2–3 ngày |
| 2 | Màn hình cài core lần đầu, tray icon, tự chọn port | 1–2 ngày |
| 3 | PyInstaller spec cho 3 OS, bộ cài (dmg / Inno Setup / AppImage), CI matrix + smoke test | 2–3 ngày |
| 4 | Ký số và notarize (phụ thuộc thời gian cấp chứng thư), overlay số trên taskbar Windows | 1–2 ngày + thời gian chờ chứng thư |
| 5 | Test thật trên máy sạch: macOS 13+, Windows 10/11, Ubuntu 22.04/24.04 | 1–2 ngày |

Cần bạn quyết định trước khi bắt đầu:
- Có mua chứng thư ký số Apple/Windows không?
- Hỗ trợ Mac Intel, hay chỉ Apple Silicon?
- Tên và icon chính thức của app.
