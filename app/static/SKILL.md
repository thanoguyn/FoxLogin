---
name: foxlogin
description: Quản lý và tự động hoá trình duyệt chống phát hiện (anti-detect browser) qua app FoxLogin (Camoufox / Firefox engine) chạy local tại http://127.0.0.1:8765. Dùng khi người dùng cần tạo, chỉnh sửa, nhân bản, xoá hoặc khởi chạy profile trình duyệt ẩn danh; gắn/kiểm tra proxy hàng loạt; nhập/xuất cookie; điều khiển trình duyệt tự động qua WebDriver BiDi (Puppeteer, Selenium 4, WebSocket BiDi); hoặc giả lập thao tác chuột cong, cuộn trang và gõ phím như người thật (human_cursor / humanize API). Automate and manage Camoufox anti-detect browser profiles, proxies, cookies, WebDriver BiDi sessions, and humanized input via the local FoxLogin API.
---

# FoxLogin: Quản lý & Tự động hoá trình duyệt Camoufox qua API local

FoxLogin là ứng dụng quản lý profile trình duyệt chống phát hiện (anti-detect browser) kiểu GoLogin, xây dựng trên nhân **Camoufox** (Firefox tuỳ biến cấp độ C++). Mỗi profile có fingerprint nhất quán theo thiết bị thật, proxy riêng, thư mục lưu trữ Firefox và cookie độc lập, cùng khả năng điều khiển tự động qua **WebDriver BiDi** và **Humanized Input** (`navigator.webdriver` luôn bằng `false`).

## Kết nối & Xác thực

Server mặc định lắng nghe tại:

```
http://127.0.0.1:8765
```

- Có thể đổi cổng qua biến môi trường `FOXCLI_PORT` (hoặc `FOXCLI_URL`). Bản desktop Tauri có thể chọn cổng trống nếu `8765` đang bận.
- Hai nhóm đường dẫn dùng chung handler:
  - `/api/v1/...` và `/browser/...`: API tự động hoá chính thức. Nếu người dùng đặt **API token** trong Settings, mọi request vào hai nhóm này phải gửi header `Authorization: Bearer <token>` hoặc query `?token=<token>`.
  - `/api/...`: API nội bộ của giao diện web (chỉ lắng nghe trên `127.0.0.1`).

---

## Bước 0: Kiểm tra trước khi chạy (Pre-flight Check)

Luôn kiểm tra trạng thái FoxLogin trước khi gọi lệnh tự động hoá:

```bash
# 1) Kiểm tra app đã mở chưa và xem phiên bản
curl -s http://127.0.0.1:8765/api/app
# -> {"app": "FoxLogin", "version": "1.0.3", "window": true}

# 2) Kiểm tra xem có bật API token hay chưa, và xem cấu hình mặc định
curl -s http://127.0.0.1:8765/api/settings

# 3) Kiểm tra nhân trình duyệt Camoufox đã cài đặt chưa
curl -s http://127.0.0.1:8765/api/browsers
```

**Xử lý các tình huống thường gặp ở Bước 0:**
- **Connection refused:** FoxLogin chưa chạy. Khởi động bằng `python3 run.py` trong thư mục dự án hoặc mở ứng dụng FoxLogin desktop.
- **`installed` rỗng trong `/api/browsers`:** Máy chưa tải nhân Camoufox (~1.2 GB). Gọi `POST /api/browsers/setup` (hoặc cài bản cụ thể qua `POST /api/browsers/install` với `{"version": "...", "repo": "official"}`) và chờ job hoàn tất trước khi gọi `/start`. Nếu gọi `/start` khi đang tải sẽ nhận HTTP `503`.
- **Profile đang chạy thủ công (`state: "running"` nhưng `port: null`):** Bấm nút **Run** trên giao diện chỉ mở trình duyệt thường, **không** mở cổng tự động hoá. Gọi `/start` lúc này sẽ báo lỗi `409 Profile is running without automation; stop it first`. Cách xử lý: gọi `POST /api/v1/profiles/{id}/stop` trước, sau đó gọi `POST /api/v1/profiles/{id}/start`.

---

## 1. Quản lý Profile

### Liệt kê & Tìm kiếm Profile: `GET /api/v1/profiles`

```bash
# Lấy tất cả profile (kèm state: "ready" | "running" | "downloading" và port nếu đang chạy API)
curl -s "http://127.0.0.1:8765/api/v1/profiles"

# Lọc theo thư mục hoặc từ khoá tìm kiếm (tên, ghi chú)
curl -s "http://127.0.0.1:8765/api/v1/profiles?folder=Shops&q=acc01"

# Xem chi tiết 1 profile
curl -s "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID"
```

### Tạo Profile mới: `POST /api/v1/profiles`

Khi tạo mới, FoxLogin tự động sinh một bộ fingerprint nhất quán từ thiết bị thật theo `os` đã chọn. Nếu dự định dùng tự động hoá có tương tác chuột/phím hoặc tìm phần tử theo CSS selector qua `/human/*`, **nên bật sẵn `human_cursor`**:

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

| Trường | Kiểu / Giá trị hợp lệ | Mặc định | Ghi chú |
|---|---|---|---|
| `name` | string | `"profile N"` | Tên hiển thị |
| `os` | `"macos"`, `"windows"`, `"linux"` | OS của máy chủ | Chọn hệ điều hành giả lập (kéo theo screen, GPU, font, voices hợp lệ) |
| `proxy` | string hoặc object | `{"type": "none"}` | Nhận thẳng chuỗi Webshare (`http://u:p@host:port`, `host:port:u:p`, `socks5://u:p@host:port`) hoặc object `{"type": "http"\|"socks5"\|"none", "host": "...", "port": "...", "username": "...", "password": "..."}` |
| `human_cursor` | `{"mode": "on"\|"off", "max_time": 1.5}` | `{"mode": "off", "max_time": 1.5}` | **Khuyên bật `"on"` khi chạy automation** để làm mượt quỹ đạo chuột/phím/cuộn và cho phép tìm selector qua `/human/*` |
| `folder` | string | `""` | Tên thư mục phân loại |
| `notes` | string | `""` | Ghi chú |
| `start_url` | string | `""` | URL tự mở khi khởi chạy profile |
| `resolution` | `"auto"` hoặc `"1920x1080"`, v.v. | `"auto"` | `"auto"` chọn độ phân giải thực tế khớp với `os` |
| `timezone` | `{"mode": "ip"\|"custom", "value": "..."}` | `{"mode": "ip"}` | `"ip"` tự động lấy múi giờ theo IP của proxy |
| `language` | `{"mode": "ip"\|"custom", "value": "..."}` | `{"mode": "ip"}` | `"ip"` tự động lấy ngôn ngữ chính của quốc gia IP |
| `geolocation` | `{"mode": "ip"\|"custom"\|"block", "lat": "", "lon": "", "accuracy": "50", "permission": "prompt"\|"allow"}` | `{"mode": "ip", "permission": "prompt"}` | Toạ độ địa lý theo IP hoặc tuỳ chỉnh |
| `webrtc` | `{"mode": "ip"\|"real"\|"disabled"}` | `{"mode": "ip"}` | Gắn WebRTC public IP theo IP proxy |
| `canvas` | `"noise"` \| `"real"` | `"noise"` | Nhiễu Canvas ở tầng C++ của Firefox |
| `webgl_image` | `"real"` \| `"noise"` | `"real"` | Để `"real"` (tắt noise) vì pixelscan phát hiện nhiễu `readPixels` |
| `webgl_info` | `{"mode": "masked"\|"real"\|"off", "vendor": "...", "renderer": "..."}` | `{"mode": "masked"}` | Tự chọn GPU khớp với OS, màn hình và CPU |
| `audio` | `"noise"` \| `"real"` | `"noise"` | Seed âm thanh cố định theo từng profile |
| `media_devices` | `{"mode": "masked"\|"real", "webcams": 1, "micros": 1, "speakers": 1}` | `{"mode": "masked"}` | Số lượng thiết bị thu/phát |
| `ublock` | bool | `false` | Bật/tắt uBlock Origin tích hợp |
| `block_images` | bool | `false` | Chặn tải ảnh để tiết kiệm băng thông proxy |
| `dock_badge` | `{"mode": "auto"\|"custom"\|"off", "text": ""}` | `{"mode": "auto"}` | Nhãn ký hiệu trên icon Dock/Taskbar và cạnh thanh địa chỉ (tối đa 4 ký tự) |

### Tạo hàng loạt & Import từ văn bản

```bash
# Tạo nhanh N profile với thiết bị ngẫu nhiên thực tế
curl -s -X POST http://127.0.0.1:8765/api/profiles/bulk \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "prefix": "Worker", "randomize": true, "template": {"os": "windows", "folder": "Farm", "human_cursor": {"mode": "on", "max_time": 1.5}}}'

# Import theo dòng: name|proxy|notes|folder|os|start_url (chỉ bắt buộc cột name)
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/import \
  -H "Content-Type: application/json" \
  -d '{"text": "acc 01|http://u:p@1.2.3.4:8080|note 1|Shops|mac|https://example.com\nacc 02|1.2.3.5:8080:u:p||Shops|windows"}'
```

### Cập nhật, Làm mới Fingerprint, Nhân bản & Xoá

- **Cập nhật (`PATCH /api/v1/profiles/{id}`):** Gửi các trường cần sửa. *Lưu ý:* Khi profile đang `running`, chỉ sửa được `name`, `notes`, `folder`, `pinned`, `dock_badge`. Muốn đổi `proxy`, `os`, `human_cursor` hay các tuỳ chọn mask thì phải `stop` profile trước (nếu không sẽ nhận lỗi HTTP `409`).
- **Đổi thiết bị ngẫu nhiên mới (`POST /api/v1/profiles/{id}/randomize`):** Rút một mẫu máy tính thực tế mới (màn hình, GPU, media devices, fingerprint) cho OS hiện tại. Profile phải đang dừng.
- **Làm mới fingerprint (`POST /api/profiles/{id}/refresh`):** Sinh lại fingerprint mới nhưng giữ nguyên cấu hình thiết bị.
- **Khôi phục mặc định (`POST /api/v1/profiles/{id}/reset`):** Áp lại bộ mask mặc định từ Settings (giữ nguyên tên, proxy, OS, thiết bị).
- **Nhân bản (`POST /api/profiles/{id}/clone`):** Tạo bản sao cấu hình với fingerprint và audio seed mới.
- **Xoá (`DELETE /api/v1/profiles/{id}`):** Dừng (nếu đang chạy) và xoá toàn bộ dữ liệu/cookie của profile. Xoá nhiều profile cùng lúc: `POST /api/profiles/delete` với body `["id1", "id2"]`.

---

## 2. Quản lý Proxy & Cookie

### Proxy

```bash
# Liệt kê các proxy đã lưu (kèm kết quả kiểm tra IP, quốc gia, độ trễ và số profile đang dùng)
curl -s http://127.0.0.1:8765/api/v1/proxies

# Nhập danh sách proxy (mỗi dòng 1 proxy, hỗ trợ mọi định dạng Webshare)
curl -s -X POST http://127.0.0.1:8765/api/v1/proxies/import \
  -H "Content-Type: application/json" \
  -d '{"text": "http://user:pass@203.0.113.10:8080\n203.0.113.11:8080:user:pass\nsocks5://user:pass@1.2.3.4:1080", "type": "http"}'

# Kiểm tra trạng thái hoạt động, IP ra, quốc gia, múi giờ, độ trễ (ms) cho danh sách ID proxy
curl -s -X POST http://127.0.0.1:8765/api/proxies/check \
  -H "Content-Type: application/json" \
  -d '["PROXY_ID_1", "PROXY_ID_2"]'
```

### Cookie (Import & Export)

```bash
# Nhập cookie (định dạng JSON của EditThisCookie, Cookie-Editor hoặc Playwright)
# Cookie được xếp hàng và nạp vào trình duyệt ở lần khởi chạy (start) tiếp theo
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/cookies \
  -H "Content-Type: application/json" \
  -d '[{"name": "session_id", "value": "xyz123", "domain": ".example.com", "path": "/", "secure": true, "httpOnly": true}]'

# Xuất toàn bộ cookie hiện có trong profile (đọc an toàn cả khi profile đang mở)
curl -s http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/cookies
```

---

## 3. Khởi chạy & Điều khiển tự động (WebDriver BiDi)

### Khởi chạy Profile ở chế độ Automation

Có 2 endpoint tương đương (đều chờ trình duyệt mở xong cổng BiDi tối đa 90 giây rồi trả về kết quả):

```bash
# Cách 1: Native API (thêm ?headless=true nếu muốn chạy ngầm không hiện cửa sổ)
curl -s -X POST "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/start"
curl -s -X POST "http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/start?headless=true"

# Cách 2: GoLogin-compatible API
curl -s -X POST "http://127.0.0.1:8765/browser/start-profile" \
  -H "Content-Type: application/json" \
  -d '{"profileId": "PROFILE_ID", "headless": false}'
```

Response trả về:

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

### Phân biệt `wsUrl` và `wsEndpoint` (Rất quan trọng)

- **Luôn ưu tiên dùng `wsUrl` (`ws://127.0.0.1:8765/ws/{id}`):**
  1. Đi qua WebDriver BiDi relay của FoxLogin, tự động chuẩn hoá `"browserName": "firefox"` để Puppeteer (`protocol: 'webDriverBiDi'`) kết nối không bị từ chối.
  2. Tự động kích hoạt bộ làm mượt thao tác người thật (**BiDi Humanizer**) cho chuột, cuộn trang và bàn phím khi profile bật `human_cursor.mode = "on"`.
  3. Khi client đóng WebSocket, relay tự gửi lệnh `session.end` lên Firefox để các script sau có thể kết nối lại vào đúng trình duyệt đang mở mà không bị kẹt phiên.
- **`wsEndpoint` (`ws://127.0.0.1:{port}/session`):** Cổng BiDi gốc của Firefox. Chỉ dùng khi cần kết nối thô không qua relay (không có humanize tự động qua BiDi).
- **Không dùng `playwright.firefox.connect()`:** Giao thức kết nối từ xa của Playwright không dùng WebDriver BiDi nên không gắn vào profile đang chạy được. Hãy dùng **Puppeteer** (`protocol: 'webDriverBiDi'`), **Selenium 4**, hoặc **WebSocket BiDi + `/human/*` API** như các mẫu bên dưới.

### Xem các Profile đang chạy & Dừng Profile

```bash
# Danh sách tất cả profile đang chạy kèm wsUrl và port
curl -s http://127.0.0.1:8765/api/v1/running

# Dừng profile (lưu lại cookie summary và đóng trình duyệt)
curl -s -X POST http://127.0.0.1:8765/api/v1/profiles/PROFILE_ID/stop
# hoặc GoLogin-compatible:
curl -s -X POST http://127.0.0.1:8765/browser/stop-profile \
  -H "Content-Type: application/json" -d '{"profileId": "PROFILE_ID"}'
```

---

## 4. Giả lập thao tác người thật (`human_cursor` & `/human/*`)

Khi profile được cấu hình `"human_cursor": {"mode": "on", "max_time": 1.5}`, FoxLogin cung cấp **2 cơ chế** tạo chuyển động như người thật:

### Cơ chế 1: Tự động trên luồng WebDriver BiDi (`wsUrl`)
Mọi lệnh chuẩn gửi qua `wsUrl` (như `page.click()`, `page.mouse.move()`, `page.mouse.wheel()`, `page.keyboard.type()` trong Puppeteer hoặc `input.performActions` trong BiDi) được relay tự động biến đổi:
- **Di chuyển chuột (`pointerMove`):** Sinh quỹ đạo cong tự nhiên từ thư viện 2.357 mẫu chuyển động người thật (`cursory`), lấy mẫu ở tần số ~60 Hz và co giãn thời gian trong khoảng `[0, max_time]`. Hỗ trợ cả toạ độ viewport lẫn tâm phần tử (`origin: {type: "element"}`).
- **Nhấn chuột (`pointerDown` / `pointerUp`):** Chèn khoảng nghỉ ngẫu nhiên 40–120 ms trước khi nhấn và trước khi nhả chuột.
- **Cuộn trang (`wheel`):** Tự động tách các cú cuộn dài (> 120 px) thành nhiều nấc lăn chuột ~88–112 px kèm nhịp nghỉ 18–45 ms.
- **Gõ phím (`keyDown` / `keyUp`):** Chèn độ trễ tự nhiên 30–90 ms giữa các ký tự liên tiếp.

### Cơ chế 2: Gọi trực tiếp HTTP API `/api/v1/profiles/{id}/human/{action}`
Điều khiển trực tiếp bộ `humanize` gốc ở tầng engine Camoufox thông qua runner mà **không cần viết code WebSocket/BiDi phức tạp**:

| Endpoint | Body JSON | Mô tả |
|---|---|---|
| `POST .../human/move` | `{"x": 400, "y": 300, "page"?: 0}` | Di chuyển chuột theo đường cong tự nhiên tới `(x, y)` |
| `POST .../human/click` | `{"selector": "button.submit", "button"?: "left", "clickCount"?: 1, "delay"?: 65, "page"?: 0}` hoặc `{"x": 400, "y": 300}` | Tự cuộn phần tử vào vùng nhìn thấy, lệch tâm ngẫu nhiên nhẹ, di chuyển chuột cong tới đích và click |
| `POST .../human/hover` | `{"selector": "a.menu", "page"?: 0}` hoặc `{"x": 200, "y": 150}` | Cuộn phần tử vào tầm nhìn và rê chuột cong tới phần tử |
| `POST .../human/scroll` | `{"deltaY": 500, "deltaX"?: 0, "x"?: 400, "y"?: 300, "page"?: 0}` | Rê chuột tới `(x, y)` (nếu có) và lăn chuột theo từng nấc tự nhiên |
| `POST .../human/type` | `{"selector"?: "input[name=q]", "text": "hello", "delay"?: 50, "page"?: 0}` | Nếu truyền `selector`, tự động click vào ô input trước rồi gõ từng ký tự với nhịp ngẫu nhiên 30–90 ms |

**Quy tắc quan trọng khi dùng `/human/*`:**
1. **Tham số `"page"` (tuỳ chọn):** Chọn tab cần thao tác. Có thể truyền số nguyên (`0` là tab đầu tiên, `-1` là tab mới mở gần nhất — mặc định là `-1`) hoặc một chuỗi con nằm trong URL hay tiêu đề (`title`) của tab (ví dụ `"page": "google.com"`).
2. **Dùng `"selector"` cần bật `human_cursor`:** Để tìm phần tử bằng CSS selector (đặc biệt sau khi trang đã điều hướng qua BiDi), profile **phải được bật `"human_cursor": {"mode": "on"}` trước khi start** (để Camoufox bật `allowMainWorld`). Nếu `human_cursor` đang `"off"`, chỉ truyền được toạ độ `x`, `y`.

---

## 5. Mẫu code thực tế (Copy-Paste Recipes)

### Mẫu 1: Node.js + Puppeteer (`puppeteer-core`)

```javascript
// npm install puppeteer-core
const puppeteer = require('puppeteer-core');

const BASE = process.env.FOXCLI_URL || 'http://127.0.0.1:8765';
const HEADERS = {
  'Content-Type': 'application/json',
  // Nếu có đặt API token trong Settings:
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
  // 1) Tạo (hoặc chọn) một profile có bật human_cursor
  const profile = await api('/api/v1/profiles', 'POST', {
    name: 'Auto Worker',
    os: 'macos',
    human_cursor: { mode: 'on', max_time: 1.5 },
  });

  try {
    // 2) Khởi chạy với cổng automation
    const { wsUrl } = await api(`/api/v1/profiles/${profile.id}/start`, 'POST');

    // 3) Kết nối Puppeteer qua giao thức WebDriver BiDi
    const browser = await puppeteer.connect({
      browserWSEndpoint: wsUrl,
      protocol: 'webDriverBiDi',
    });
    const page = (await browser.pages())[0] || (await browser.newPage());
    await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });

    // Mọi thao tác chuột/phím qua Puppeteer trên wsUrl đều tự động được humanize
    // Hoặc có thể gọi trực tiếp engine humanize của Camoufox theo CSS selector:
    await api(`/api/v1/profiles/${profile.id}/human/click`, 'POST', {
      selector: 'a',
      page: 'example.com',
    });

    console.log('Title:', await page.title());
    await browser.disconnect();
  } finally {
    // 4) Dừng profile để lưu cookie
    await api(`/api/v1/profiles/${profile.id}/stop`, 'POST');
  }
})();
```

### Mẫu 2: Python (WebDriver BiDi + `/human/*`, chỉ cần `websockets`)

Mẫu này cực gọn cho AI Agent khi cần chạy script Python tự động hoá mà không cần cài đặt Selenium hay Puppeteer: dùng WebDriver BiDi để điều hướng + đọc DOM/JS, và dùng `/human/*` để click, gõ chữ, cuộn trang như người thật.

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

        # Khởi tạo phiên BiDi và lấy tab đầu tiên
        await bidi("session.new", {"capabilities": {}})
        tree = await bidi("browsingContext.getTree", {})
        ctx = tree["contexts"][0]["context"]

        # Điều hướng tới trang đích
        await bidi("browsingContext.navigate", {
            "context": ctx,
            "url": "https://example.com/",
            "wait": "complete",
        })

        # Tương tác như người thật qua /human/* (hỗ trợ CSS selector khi human_cursor = "on")
        api(f"/api/v1/profiles/{pid}/human/scroll", "POST", {"deltaY": 350})
        api(f"/api/v1/profiles/{pid}/human/hover", "POST", {"selector": "a"})

        # Đọc dữ liệu từ trang bằng script.evaluate
        res = await bidi("script.evaluate", {
            "expression": "JSON.stringify({ title: document.title, url: location.href, webdriver: navigator.webdriver })",
            "target": {"context": ctx},
            "awaitPromise": True,
        })
        print("Page info:", json.loads(res["result"]["value"]))
        await bidi("session.end", {})


# 1) Tạo hoặc lấy profile (đảm bảo human_cursor đang bật)
profile = api("/api/v1/profiles", "POST", {
    "name": "Python BiDi Agent",
    "os": "macos",
    "human_cursor": {"mode": "on", "max_time": 1.5},
})

try:
    # 2) Start profile (thêm ?headless=true nếu muốn chạy ngầm)
    start_info = api(f"/api/v1/profiles/{profile['id']}/start", "POST")
    asyncio.run(run_task(profile["id"], start_info["wsUrl"]))
finally:
    # 3) Dừng profile khi xong việc
    api(f"/api/v1/profiles/{profile['id']}/stop", "POST")
```
