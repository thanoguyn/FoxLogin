# FoxLogin: quản lý profile kiểu GoLogin, chạy trên nhân Camoufox

## Chạy

```bash
pip3 install -r requirements.txt     # lần đầu
python3 run.py                        # hoặc double-click start.command
```

Giao diện mở tại http://127.0.0.1:8765. Số profile không giới hạn. Mỗi profile có fingerprint, cookie và dữ liệu Firefox riêng trong `data/profiles/<id>/`.

Khi tắt hoặc khởi động lại server, các browser đang mở vẫn chạy. Lần sau server khởi động sẽ tự nhận lại chúng.

## Giao diện

- **Sidebar**
  - Thu gọn/mở rộng bằng nút ở góc trên, hoặc phím `Ctrl/⌘+B`.
  - Các mục: All profiles, Proxies, API & Automation, Settings, Folders, Fingerprint self-test.
- **Add profile** mở form tạo profile, có nút **Random fingerprint**. Mũi tên cạnh nút có thêm Quick profile, Create multiple profiles và Import profiles.
- **Bảng profile**
  - Đổi tên: double-click vào tên.
  - Ghi chú: click vào cột Notes (`+ Add note`) để sửa ngay tại chỗ.
  - Proxy: click vào ô *Proxy & Location* để chọn proxy đã lưu, hoặc dán proxy vào (📋).
  - Nút cột (⚙ trên phải): bật/tắt các cột Proxy Port/Username/Password, Folder, OS, Device, Browser Version, ngày tạo, lần chạy cuối…
  - Menu `•••`: Settings, Folders, Clone, Run/Stop, Cookies (import/export), Random fingerprint, Refresh fingerprint, Update browser, Copy "Run" link, Copy ID, Pin, Delete, Automation.
  - Chọn nhiều profile để làm hàng loạt: Run, Stop, Set proxy (dán N proxy thì gán lần lượt cho từng profile), Move to folder, Random fingerprint, Delete.
- **Proxies**
  - Thêm hàng loạt, mỗi dòng một proxy, nhận đúng định dạng Webshare:
    - `http://user:pass@host:port/`
    - `host:port:user:pass`
    - `socks5://…`
    - `host:port`
  - Check proxy để xem IP, quốc gia và độ trễ. Bảng có cột cho biết proxy đang được bao nhiêu profile dùng.
- **Import profiles**: mỗi dòng có dạng `tên|proxy|ghi chú|folder|os|start_url`, trong đó chỉ tên là bắt buộc.
- **Settings**
  - Cấu hình mặc định cho profile mới: OS, ngôn ngữ, timezone, geolocation, WebRTC, độ phân giải, các mask, extension.
  - Lần đầu mở app, FoxLogin hiện danh sách bản Camoufox để tải (chọn sẵn bản stable mới nhất). Nếu bỏ qua, bản stable mới nhất sẽ được tải khi Run profile đầu tiên, tiến độ hiện trên nút Run và thanh thông báo phía trên.
  - **Browser core**: xem các bản Camoufox đã cài, *Check for updates*, cài bản mới hơn hoặc cũ hơn (≈1,2 GB mỗi bản), chọn bản mặc định, gỡ bản không dùng. Từng profile cũng có thể chọn bản riêng.
  - **API token** (tuỳ chọn).

## Random fingerprint hợp lý

Mỗi lần random sẽ chọn một máy thật theo OS và đảm bảo các thông số khớp nhau:

- **macOS**: MacBook Air 13" (1470×956 hoặc 1440×900), MacBook Pro 14"/16", Air 15", Mac mini/Studio với màn QHD.
- **Windows/Linux**: laptop hoặc desktop với các độ phân giải phổ biến.
- **Thiết bị media**: laptop có sẵn camera, micro và loa; desktop có thể không có webcam.
- **GPU**: chỉ chọn GPU khớp với màn hình và số nhân CPU.

Firefox không cung cấp thông số RAM (`navigator.deviceMemory` không tồn tại). Số luồng CPU luôn theo máy thật, vì nếu giả thì sẽ bị lộ qua đo tốc độ Worker. Vì vậy hai thông số này không được random.

## API tự động hoá (giống GoLogin)

Xem trang **API & Automation** trong app để có danh sách endpoint và đoạn code mẫu có sẵn ID profile. Ví dụ với Puppeteer:

```js
const { wsUrl } = await (await fetch('http://127.0.0.1:8765/api/v1/profiles/ID/start', { method: 'POST' })).json();
const browser = await puppeteer.connect({ browserWSEndpoint: wsUrl, protocol: 'webDriverBiDi' });
```

- **Endpoint tương thích GoLogin**: `POST /browser/start-profile {"profileId"}` trả về `wsUrl`, và `POST /browser/stop-profile`.
- **Các endpoint khác**:
  - `GET /api/v1/profiles`, `GET /api/v1/profiles/{id}` (có `port` khi profile đang chạy)
  - `POST`/`PATCH`/`DELETE` profile
  - `/start`, `/stop`, `/randomize`, `/cookies`, `/import`, `/api/v1/running`, `/api/v1/proxies`
- Camoufox là Firefox, nên automation dùng **WebDriver BiDi**. Dùng được với Puppeteer, Selenium 4 hoặc client BiDi khác; `navigator.webdriver` vẫn là `false`. Playwright `connect()` thì không gắn được vào profile đang chạy.

## Các tuỳ chọn mask

| Tuỳ chọn | Masked / Noise | Real / Off |
|---|---|---|
| Canvas | Nhiễu do engine Firefox tạo (C++), khác nhau giữa các profile và mỗi phiên | Hash phần cứng thật |
| WebGL Image | Nhiễu khi đọc `readPixels`. **pixelscan phát hiện được**, nên mặc định là Off | Không nhiễu |
| Audio Context | Seed riêng cho mỗi profile, giữ nguyên qua các lần chạy | Không nhiễu |
| WebGL info | GPU khớp với OS, màn hình và CPU | GPU thật |
| Media devices | Số lượng và tên camera/mic/loa theo profile | Thiết bị thật |
| Timezone / Ngôn ngữ / Geo / WebRTC | Theo IP (qua proxy nếu có) hoặc Custom. Geolocation mặc định là **Prompt** (hỏi quyền) | |

## Kiểm tra

```bash
python3 run.py &
python3 tests/check_marks.py                       # 27 kiểm tra: mark có làm thông số khác đi không
python3 tests/check_api.py                         # API REST + WebDriver BiDi (cần pip3 install websockets)
python3 tests/check_sites.py <profile_id> out_dir  # pixelscan, iphey, browserscan, creepjs (chụp màn hình)
```

## Giấy phép

FoxLogin phát hành theo [giấy phép MIT](LICENSE). FoxLogin tải về và chạy trình duyệt [Camoufox](https://github.com/daijro/camoufox) (nhân Firefox, giấy phép **MPL-2.0**). Gói Python `camoufox` dùng giấy phép MIT. Repo này không chứa Camoufox. Giấy phép của mọi thành phần bên thứ ba xem ở [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
