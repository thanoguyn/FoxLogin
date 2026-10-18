"""Profile storage, fingerprint generation and Camoufox launch options.

Every profile lives in data/profiles/<id>/:
    profile.json         settings shown in the UI
    fingerprint.json.gz  the fpgen fingerprint that pins the identity
    userdata/            the persistent Firefox profile (cookies, storage, ...)
    applied.json         what the browser actually presented on its last launch
    cookies_import.json  cookies queued to be added on the next launch
"""
from __future__ import annotations

import copy
import gzip
import json
import os
import random
import shutil
import subprocess
import sys
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

VERSION = "1.0.0"

# Packaged by PyInstaller: one executable re-invokes itself in other modes
FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(__file__).resolve().parent.parent


def _default_data() -> Path:
    if not FROZEN:
        return ROOT / "data"
    # The app bundle is read-only: keep profiles in the user's app-data folder
    from platformdirs import user_data_dir

    return Path(user_data_dir("FoxLogin", appauthor=False, roaming=True))


DATA = Path(os.environ.get("FOXCLI_DATA") or _default_data())
PROFILES = DATA / "profiles"
PROFILES.mkdir(parents=True, exist_ok=True)

OS_KEYS = {"macos": "mac", "windows": "win", "linux": "lin"}
OS_ALIASES = {"mac": "macos", "osx": "macos", "win": "windows", "lin": "linux"}

# Resolutions offered in the UI (GoLogin-like list). "auto" lets fpgen pick
# a real-world screen for the chosen OS.
RESOLUTIONS = [
    "1280x720", "1280x800", "1366x768", "1440x900", "1512x982", "1536x864",
    "1600x900", "1680x1050", "1728x1117", "1920x1080", "1920x1200",
    "2560x1440", "2560x1600",
]

DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "",
    "notes": "",
    "folder": "",
    "os": "macos",
    "start_url": "",
    "proxy": {"type": "none", "host": "", "port": "", "username": "", "password": ""},
    "timezone": {"mode": "ip", "value": ""},
    "geolocation": {"mode": "ip", "lat": "", "lon": "", "accuracy": "50", "permission": "prompt"},
    "language": {"mode": "ip", "value": ""},
    "webrtc": {"mode": "ip"},
    "resolution": "auto",
    "canvas": "noise",
    # Off by default: WebGL read-back noise is caught by pixelscan's probes
    "webgl_image": "real",
    "webgl_info": {"mode": "masked", "vendor": "", "renderer": ""},
    "audio": "noise",
    "media_devices": {"mode": "masked", "webcams": 1, "micros": 1, "speakers": 1},
    "allow_extensions": True,
    "ublock": False,
    "block_images": False,
    "browser": "",      # Camoufox build for this profile ("" = app default)
    "pinned": False,
    "device": "",       # human label of the drawn hardware, e.g. MacBook Pro 14"
    # Number/letters badged on the Camoufox Dock icon (macOS) to tell windows apart
    "dock_badge": {"mode": "auto", "text": ""},
}


# --------------------------------------------------------------------------- store

def _pdir(pid: str) -> Path:
    return PROFILES / pid


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def _merge(base: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in p.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def _merge_defaults(p: Dict[str, Any]) -> Dict[str, Any]:
    return _merge(DEFAULT_PROFILE, p)


# ------------------------------------------------------------------ app settings

# Profile fields the Settings page can preset for new profiles
TEMPLATE_KEYS = (
    "os", "start_url", "timezone", "geolocation", "language", "webrtc", "resolution",
    "canvas", "webgl_image", "webgl_info", "audio", "media_devices",
    "allow_extensions", "ublock", "block_images", "dock_badge",
)

# Fields "Reset to defaults" copies from the template onto an existing profile.
# OS and resolution stay: they are the device identity, not a preference.
RESET_KEYS = tuple(k for k in TEMPLATE_KEYS if k not in ("os", "resolution", "start_url"))


def get_settings() -> Dict[str, Any]:
    s = _read_json(DATA / "settings.json", {}) or {}
    tmpl = {k: copy.deepcopy(DEFAULT_PROFILE[k]) for k in TEMPLATE_KEYS}
    tmpl["os"] = host_os()
    tmpl = _merge(tmpl, s.get("defaults", {}))
    return {"defaults": tmpl, "browser": s.get("browser", ""), "api_token": s.get("api_token", "")}


def save_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    cur = _read_json(DATA / "settings.json", {}) or {}
    if changes.get("reset_defaults"):
        # Drop the saved template so the recommended code defaults apply again
        cur.pop("defaults", None)
    if "defaults" in changes:
        d = {k: v for k, v in changes["defaults"].items() if k in TEMPLATE_KEYS}
        cur["defaults"] = _merge(cur.get("defaults", {}), d)
    for k in ("browser", "api_token"):
        if k in changes:
            cur[k] = changes[k]
    _write_json(DATA / "settings.json", cur)
    return get_settings()


def list_profiles() -> List[Dict[str, Any]]:
    items = []
    for d in PROFILES.iterdir():
        p = _read_json(d / "profile.json")
        if p:
            p = _merge_defaults(p)
            p["applied"] = _read_json(d / "applied.json", {})
            p["cookies"] = _read_json(d / "cookies_summary.json", {})
            items.append(p)
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return items


def get_profile(pid: str) -> Optional[Dict[str, Any]]:
    p = _read_json(_pdir(pid) / "profile.json")
    if not p:
        return None
    p = _merge_defaults(p)
    p["applied"] = _read_json(_pdir(pid) / "applied.json", {})
    p["cookies"] = _read_json(_pdir(pid) / "cookies_summary.json", {})
    return p


def save_profile(p: Dict[str, Any]) -> None:
    p = {k: v for k, v in p.items() if k not in ("applied", "cookies", "preview")}
    p["updated_at"] = time.time()
    _write_json(_pdir(p["id"]) / "profile.json", p)


def list_folders() -> List[str]:
    return _read_json(DATA / "folders.json", [])


def add_folder(name: str) -> List[str]:
    folders = sorted(set(list_folders()) | {name})
    _write_json(DATA / "folders.json", folders)
    return folders


def next_profile_name() -> str:
    names = {p.get("name") for p in list_profiles()}
    n = len(names) + 1
    while f"profile {n}" in names:
        n += 1
    return f"profile {n}"


def create_profile(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = data or {}
    p = _merge_defaults(_merge(get_settings()["defaults"], data))
    p["id"] = uuid.uuid4().hex[:12]
    p["name"] = (data.get("name") or "").strip() or next_profile_name()
    p["created_at"] = time.time()
    p["audio_seed"] = random.randint(1, 0xFFFFFFFF)
    _pdir(p["id"]).mkdir(parents=True, exist_ok=True)
    new_fingerprint(p, keep_gpu=True)
    save_profile(p)
    return get_profile(p["id"])


def update_profile(pid: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    p = get_profile(pid)
    if p is None:
        raise KeyError(pid)
    regen = False
    for k, v in changes.items():
        if k in ("id", "created_at", "audio_seed"):
            continue
        if k in ("os", "resolution") and v != p.get(k):
            regen = True
        if isinstance(v, dict) and isinstance(p.get(k), dict):
            p[k].update(v)
        else:
            p[k] = v
    if regen:
        new_fingerprint(p, keep_gpu=True)
    save_profile(p)
    return get_profile(pid)


def reset_profile(pid: str) -> Dict[str, Any]:
    """Re-apply the default template's masks and location settings to a profile."""
    tmpl = get_settings()["defaults"]
    changes = {k: copy.deepcopy(tmpl[k]) for k in RESET_KEYS}
    # Keep the profile's own GPU and badge text; only their modes come from the template
    changes["webgl_info"] = {"mode": tmpl["webgl_info"]["mode"]}
    changes["dock_badge"] = {"mode": tmpl["dock_badge"]["mode"]}
    # Device counts were drawn to fit the device (a Mac mini has no webcam)
    changes["media_devices"] = {"mode": tmpl["media_devices"]["mode"]}
    return update_profile(pid, changes)


def delete_profile(pid: str) -> None:
    shutil.rmtree(_pdir(pid), ignore_errors=True)


def clone_profile(pid: str) -> Dict[str, Any]:
    src = get_profile(pid)
    data = {k: v for k, v in src.items() if k not in ("id", "created_at", "applied", "cookies", "audio_seed", "pinned")}
    data["name"] = src["name"] + " (copy)"
    # A clone is a new device: it gets its own fingerprint and seeds.
    data["webgl_info"] = dict(src["webgl_info"], vendor="", renderer="")
    return create_profile(data)


# --------------------------------------------------------------------- fingerprint

def _screen_bound(resolution: str):
    from camoufox.fingerprints import Screen

    if not resolution or resolution == "auto":
        return None
    w, h = (int(x) for x in resolution.lower().split("x"))
    return Screen(min_width=w, max_width=w, min_height=h, max_height=h)


def new_fingerprint(p: Dict[str, Any], keep_gpu: bool = False) -> None:
    """Draw a fresh fpgen identity for the profile (Refresh fingerprint)."""
    from camoufox.fingerprints import generate_fingerprint
    from camoufox.webgl import firefox_gpus

    screen = _screen_bound(p.get("resolution", "auto"))
    try:
        fp = generate_fingerprint(os=p["os"], screen=screen)
    except Exception:
        fp = generate_fingerprint(os=p["os"])
    with gzip.open(_pdir(p["id"]) / "fingerprint.json.gz", "wt") as f:
        json.dump(fp, f)

    # A new device gets a new audio seed and (when masked) a new GPU that a
    # real machine with this OS, screen and core count could have.
    p["audio_seed"] = random.randint(1, 0xFFFFFFFF)
    wi = p["webgl_info"]
    choices = coherent_gpus(p["os"], fp)
    if wi.get("mode") == "masked" and not (keep_gpu and (wi.get("vendor"), wi.get("renderer")) in choices):
        vendor, renderer = random.choice(choices)
        p["webgl_info"].update(vendor=vendor, renderer=renderer)
    p["fingerprint_at"] = time.time()
    (_pdir(p["id"]) / "applied.json").unlink(missing_ok=True)


def load_fingerprint(pid: str) -> Dict[str, Any]:
    with gzip.open(_pdir(pid) / "fingerprint.json.gz", "rt") as f:
        return json.load(f)


def gpu_list(os_name: str) -> List[Tuple[str, str]]:
    from camoufox.webgl import firefox_gpus

    return sorted(firefox_gpus(OS_KEYS[os_name]))


def coherent_gpus(os_name: str, fp: Optional[Dict[str, Any]] = None) -> List[Tuple[str, str]]:
    """GPUs Firefox reports on this OS that fit the identity's screen and the
    core count the browser will present (camoufox snaps it to the host's).
    On an Apple Silicon host a macOS identity only fits "Apple M1, or similar",
    which is what Firefox reports for every M-series Mac."""
    from camoufox.coherence import gpu_fits_machine, gpu_fits_os

    key = OS_KEYS[os_name]
    rg = real_gpu(os_name)
    if rg:
        # The identity is the host's own OS on Apple Silicon: an Intel/AMD Mac
        # GPU would contradict the M-series rendering and timing a page sees.
        return [rg]
    scr = (fp or {}).get("screen") or {}
    out = [
        g for g in gpu_list(os_name)
        if gpu_fits_os(g[1], key)
        and gpu_fits_machine(g[1], key, os.cpu_count(), scr.get("width"), scr.get("height"))
    ]
    return out or gpu_list(os_name)


def host_os() -> str:
    import platform

    s = platform.system()
    return "macos" if s == "Darwin" else "windows" if s == "Windows" else "linux"


def real_gpu(os_name: str) -> Optional[Tuple[str, str]]:
    """The host GPU as Firefox names it, when it is a pair fpgen knows."""
    if os_name != host_os() or os_name != "macos":
        return None
    import platform

    if platform.machine() == "arm64":
        return ("Apple", "Apple M1, or similar")
    return None


# ------------------------------------------------------------------ launch options

def proxy_dict(proxy: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not proxy or proxy.get("type", "none") == "none" or not proxy.get("host"):
        return None
    scheme = {"http": "http", "https": "http", "socks5": "socks5", "socks4": "socks4"}[proxy["type"]]
    out = {"server": f"{scheme}://{proxy['host']}:{proxy['port']}"}
    if proxy.get("username"):
        out["username"] = proxy["username"]
        out["password"] = proxy.get("password", "")
    return out


def _main_language(cc: str) -> str:
    """The most spoken language of a territory (CLDR), e.g. VN -> vi."""
    from camoufox.locales import SELECTOR

    langs, probs = SELECTOR._load_territory_data(cc)
    return str(langs[int(probs.argmax())]).replace("_", "-")


def resolve_ip_location(proxy: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Public IP (through the proxy when set) -> country, timezone, languages.

    Camoufox's own geoip draws the language at random from every language
    spoken in the country on each launch (vi-VN one time, blt-VN the next);
    a real user keeps the country's main language, plus English like GoLogin.
    """
    from camoufox.geolocation import get_geolocation
    from camoufox.ip import Proxy, public_ip

    ip = public_ip(Proxy(**proxy).as_string()) if proxy else public_ip()
    geo = get_geolocation(ip)
    cc = (geo.locale.region or "").upper()
    lang = _main_language(cc) if cc else "en"
    first = f"{lang}-{cc}" if cc and "-" not in lang else lang
    locales = [first, lang.split("-")[0]]
    if not lang.startswith("en"):
        locales += ["en-US", "en"]
    return {"ip": ip, "country": cc, "timezone": geo.timezone, "lat": geo.latitude,
            "lon": geo.longitude, "locales": list(dict.fromkeys(locales))}


def camoufox_kwargs(p: Dict[str, Any], headless: bool = False, geoip: bool = True) -> Dict[str, Any]:
    """Camoufox launch options for the profile (see launch_kwargs)."""
    return launch_kwargs(p, headless, geoip)[0]


def browser_spec(p: Dict[str, Any]) -> str:
    """The Camoufox build a profile runs: its own pin, else the app default."""
    return p.get("browser") or get_settings()["browser"] or ""


def launch_kwargs(
    p: Dict[str, Any], headless: bool = False, geoip: bool = True, debug_port: Optional[int] = None
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Map the profile's GoLogin-style options onto Camoufox launch options.

    Returns the options and the IP location they were resolved from, if any."""
    from camoufox.addons import DefaultAddons
    from camoufox.fingerprints import draw_media_devices

    config: Dict[str, Any] = {}
    prefs: Dict[str, Any] = {}
    kw: Dict[str, Any] = {
        "os": p["os"],
        "fingerprint": load_fingerprint(p["id"]),
        "headless": headless,
        "i_know_what_im_doing": True,
        "config": config,
        "firefox_user_prefs": prefs,
    }
    if browser_spec(p):
        kw["browser"] = browser_spec(p)
    if debug_port:
        # WebDriver BiDi for Puppeteer / Selenium; only opened when automating
        kw["args"] = [f"--remote-debugging-port={debug_port}"]

    # Proxy & location -------------------------------------------------------
    proxy = proxy_dict(p["proxy"])
    if proxy:
        kw["proxy"] = proxy
    use_ip = any(
        p[k]["mode"] == "ip" for k in ("timezone", "geolocation", "language", "webrtc")
    )
    loc = None
    if use_ip and geoip:
        loc = resolve_ip_location(proxy)
        kw["geoip"] = loc["ip"]

    if p["timezone"]["mode"] == "custom" and p["timezone"]["value"]:
        config["timezone"] = p["timezone"]["value"]

    # Geolocation: the coordinates come from the IP or the profile; whether a
    # site gets them without asking is the permission. "prompt" is what a real
    # Firefox does, and checkers that compare GPS with their own IP database
    # (pixelscan truncates lat/lon) only see coordinates once the user allows.
    geo = p["geolocation"]
    if geo["mode"] == "custom" and geo.get("lat") not in ("", None) and geo.get("lon") not in ("", None):
        config["geolocation:latitude"] = float(geo["lat"])
        config["geolocation:longitude"] = float(geo["lon"])
        config["geolocation:accuracy"] = float(geo.get("accuracy") or 50)
    if geo["mode"] == "block":
        prefs["permissions.default.geo"] = 2
    else:
        prefs["permissions.default.geo"] = 1 if geo.get("permission") == "allow" else 0

    lang = p["language"]
    if lang["mode"] == "custom" and lang["value"]:
        kw["locale"] = [x.strip() for x in lang["value"].split(",") if x.strip()]
    elif lang["mode"] == "ip" and loc:
        kw["locale"] = loc["locales"]

    if p["webrtc"]["mode"] == "disabled":
        kw["block_webrtc"] = True

    # Hardware ----------------------------------------------------------------
    # Canvas & WebGL image. Firefox 145+ adds per-session noise to 2D canvas
    # read-back in its C++ code (baseline fingerprinting protection); its
    # CanvasRandomization target extends that to WebGL readPixels. Both leave
    # single-colour buffers untouched, so "is this a noise injector" probes
    # still read the hardware's exact bytes. "Real" turns all of it off.
    noise_2d = p["canvas"] == "noise" or p["webgl_image"] == "noise"
    prefs["privacy.baselineFingerprintingProtection.overrides"] = (
        "" if noise_2d else "-CanvasRandomization,-EfficientCanvasRandomization"
    )
    if p["webgl_image"] == "noise":
        prefs["privacy.fingerprintingProtection"] = True
        prefs["privacy.fingerprintingProtection.overrides"] = "-AllTargets,+CanvasRandomization"
    else:
        prefs["privacy.fingerprintingProtection"] = False
        prefs["privacy.fingerprintingProtection.overrides"] = ""

    # WebGL metadata (vendor / renderer + the parameters recorded for that GPU)
    wi = p["webgl_info"]
    if wi["mode"] == "masked" and wi.get("vendor") and wi.get("renderer"):
        kw["webgl_config"] = (wi["vendor"], wi["renderer"])
    elif wi["mode"] == "real":
        rg = real_gpu(p["os"])
        if rg:
            kw["webgl_config"] = rg
    elif wi["mode"] == "off":
        kw["block_webgl"] = True

    # AudioContext: a per-profile seed gives stable noise; 0 disables it.
    config["audio:seed"] = int(p.get("audio_seed") or 1) if p["audio"] == "noise" else 0

    md = p["media_devices"]
    if md["mode"] == "masked":
        from camoufox.fingerprints import identity_salt

        drawn = draw_media_devices(OS_KEYS[p["os"]], identity_salt(p["id"]))
        config.update(_resize_media(drawn, md))
    else:
        # "Real": the host's own devices, no spoofed list.
        config["mediaDevices:enabled"] = False

    # Fonts: on its own OS the browser renders with the real system fonts, so
    # every system font is allowed, exactly like a stock Firefox on this
    # machine. Camoufox's default claims only the OS base set, which hides
    # system fonts (Times, STIX*, Marion, ...) that checkers expect on macOS.
    if p["os"] == host_os() and p["os"] in ("macos", "windows"):
        from camoufox.fingerprints import _load_os_fonts

        kw["fonts"] = list(_load_os_fonts()[OS_KEYS[p["os"]]])

    # Extensions --------------------------------------------------------------
    prefs["xpinstall.enabled"] = bool(p.get("allow_extensions", True))
    if not p.get("ublock"):
        kw["exclude_addons"] = [DefaultAddons.UBO]
    if p.get("block_images"):
        kw["block_images"] = True
    return kw, loc


def _resize_media(drawn: Dict[str, Any], want: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the OS-style labels camoufox drew, at the device counts asked for."""
    out = dict(drawn)
    for kind, key in (("webcams", "webcam"), ("micros", "microphone"), ("speakers", "speaker")):
        n = max(0, min(4, int(want.get(kind, drawn.get(f"mediaDevices:{kind}", 1)))))
        labels = list(drawn.get(f"mediaDevices:{key}Labels", []))
        groups = list(drawn.get(f"mediaDevices:{key}Groups", []))
        base = labels[0] if labels else {"webcam": "FaceTime HD Camera", "microphone": "Microphone", "speaker": "Speakers"}[key]
        while len(labels) < n:
            labels.append(f"{base} ({len(labels) + 1})")
            groups.append(f"hw-x{kind}{len(groups) + 1}")
        out[f"mediaDevices:{kind}"] = n
        out[f"mediaDevices:{key}Labels"] = labels[:n]
        out[f"mediaDevices:{key}Groups"] = groups[:n]
    return out


def preview(p: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the launch config without starting the browser (UI summary)."""
    from camoufox.utils import launch_options

    opts = launch_options(**camoufox_kwargs(p, headless=True, geoip=False))
    env = opts.get("env", {})
    chunks = sorted((k for k in env if k.startswith("CAMOU_CONFIG_")), key=lambda k: int(k.rsplit("_", 1)[1]))
    cfg = json.loads("".join(env[k] for k in chunks)) if chunks else {}
    return {
        "userAgent": cfg.get("navigator.userAgent"),
        "platform": cfg.get("navigator.platform"),
        "screen": f"{cfg.get('screen.width')}x{cfg.get('screen.height')}",
        "threads": cfg.get("navigator.hardwareConcurrency"),
        "webglVendor": cfg.get("webGl:vendor"),
        "webglRenderer": cfg.get("webGl:renderer"),
        "fonts": len(cfg.get("fonts") or []),
        "voices": len(cfg.get("voices") or []),
        "webcams": cfg.get("mediaDevices:webcams"),
        "micros": cfg.get("mediaDevices:micros"),
        "speakers": cfg.get("mediaDevices:speakers"),
        "audioSeed": cfg.get("audio:seed"),
    }


# ----------------------------------------------------------------- random device

# Real machines per OS: (label, screen, weight, kind). Only screens fpgen has
# recorded for the OS, so the generated identity keeps the exact size.
DEVICES = {
    "macos": [
        ('MacBook Air 13" (Apple Silicon)', "1470x956", 26, "laptop"),
        ('MacBook Air 13" M1', "1440x900", 14, "laptop"),
        ('MacBook Pro 14"', "1512x982", 22, "laptop"),
        ('MacBook Air 15"', "1710x1107", 10, "laptop"),
        ('MacBook Pro 16"', "1728x1117", 12, "laptop"),
        ('Mac mini / Studio + 27" QHD', "2560x1440", 8, "desktop"),
    ],
    "windows": [
        ("Laptop / desktop FHD", "1920x1080", 34, "any"),
        ("Laptop 15.6\" FHD at 125%", "1536x864", 16, "laptop"),
        ("Budget laptop HD", "1366x768", 14, "laptop"),
        ("Desktop QHD monitor", "2560x1440", 10, "desktop"),
        ("Laptop 1440x900", "1440x900", 5, "laptop"),
        ("Desktop 1680x1050", "1680x1050", 4, "desktop"),
        ("Laptop HD at 150%", "1280x720", 4, "laptop"),
    ],
    "linux": [
        ("Desktop FHD", "1920x1080", 60, "desktop"),
        ("Laptop HD", "1366x768", 25, "laptop"),
        ("Laptop HD+", "1600x900", 15, "laptop"),
    ],
}


def random_device(os_name: str) -> Dict[str, Any]:
    """A plausible device for the OS: screen, media devices and GPU fit together.

    Firefox exposes neither RAM (no navigator.deviceMemory) nor a free choice
    of CPU threads (they follow the host, or worker timing gives it away), so
    the coherent parts left to draw are the screen, the camera/mic/speaker set
    and the GPU, which coherent_gpus() filters against the screen and cores.
    """
    rows = DEVICES[os_name]
    label, res, _, kind = random.choices(rows, weights=[r[2] for r in rows])[0]
    if kind == "any":
        kind = random.choice(["laptop", "desktop"])
    if kind == "laptop":   # built-in camera, mic and speakers, sometimes a headset
        cams, mics, sps = 1, random.choice([1, 1, 1, 2]), random.choice([1, 1, 2])
    else:                  # desktop: webcam optional, monitor speakers / headset
        cams, mics, sps = random.choice([0, 1, 1]), random.choice([1, 1, 2]), random.choice([1, 2, 2])
    if os_name == "macos" and kind == "desktop":
        cams = random.choice([0, 1])
    return {
        "device": label,
        "resolution": res,
        "media_devices": {"mode": "masked", "webcams": cams, "micros": mics, "speakers": sps},
    }


def randomize_profile(pid: str) -> Dict[str, Any]:
    """New device + new fingerprint, keeping name, proxy, cookies and data."""
    p = get_profile(pid)
    dev = random_device(p["os"])
    p.update(device=dev["device"], resolution=dev["resolution"])
    p["media_devices"].update(dev["media_devices"])
    if p["webgl_info"].get("mode") == "masked":
        p["webgl_info"].update(vendor="", renderer="")
    new_fingerprint(p)
    save_profile(p)
    return get_profile(pid)


# ------------------------------------------------------------------------ proxies

def parse_proxy(text: str, default_type: str = "http") -> Optional[Dict[str, str]]:
    """Parse one proxy in the formats Webshare and most providers export:

        http://user:pass@host:port/      socks5://user:pass@host:port
        host:port:user:pass              user:pass@host:port
        host:port                        user:pass:host:port (when port is last)
    """
    t = text.strip().strip("/")
    if not t or t.startswith("#"):
        return None
    ptype = default_type
    if "://" in t:
        scheme, t = t.split("://", 1)
        ptype = {"https": "http", "socks5h": "socks5", "socks": "socks5"}.get(scheme.lower(), scheme.lower())
    user = pwd = ""
    if "@" in t:
        cred, hostport = t.rsplit("@", 1)
        user, _, pwd = cred.partition(":")
        host, _, port = hostport.partition(":")
    else:
        parts = t.split(":")
        if len(parts) == 2:
            host, port = parts
        elif len(parts) >= 4 and parts[1].isdigit():
            host, port, user, pwd = parts[0], parts[1], parts[2], ":".join(parts[3:])
        elif len(parts) == 4 and parts[3].isdigit():
            user, pwd, host, port = parts
        else:
            return None
    if not host or not port.isdigit() or ptype not in ("http", "socks5", "socks4"):
        return None
    return {"type": ptype, "host": host, "port": port, "username": user, "password": pwd}


def proxy_label(px: Dict[str, Any]) -> str:
    return f"{px['host']}:{px['port']}"


def list_proxies() -> List[Dict[str, Any]]:
    return _read_json(DATA / "proxies.json", [])


def _save_proxies(items: List[Dict[str, Any]]) -> None:
    _write_json(DATA / "proxies.json", items)


def add_proxies(text: str, default_type: str = "http") -> Dict[str, Any]:
    items = list_proxies()
    seen = {(x["type"], x["host"], x["port"], x["username"]) for x in items}
    added, bad = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        px = parse_proxy(line, default_type)
        if not px:
            bad.append(line.strip())
            continue
        key = (px["type"], px["host"], px["port"], px["username"])
        if key in seen:
            continue
        seen.add(key)
        px.update(id=uuid.uuid4().hex[:10], name="", created_at=time.time(), check={})
        items.append(px)
        added.append(px)
    _save_proxies(items)
    return {"added": added, "invalid": bad}


def update_proxy(xid: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    items = list_proxies()
    for x in items:
        if x["id"] == xid:
            x.update({k: v for k, v in changes.items() if k != "id"})
            _save_proxies(items)
            return x
    raise KeyError(xid)


def delete_proxies(ids: List[str]) -> None:
    _save_proxies([x for x in list_proxies() if x["id"] not in set(ids)])


def check_proxy(px: Dict[str, Any]) -> Dict[str, Any]:
    import requests

    pd = proxy_dict(px)
    if not pd:
        return {"ok": False, "error": "No proxy"}
    server = pd["server"]
    if pd.get("username"):
        scheme, rest = server.split("://", 1)
        server = f"{scheme}://{pd['username']}:{pd['password']}@{rest}"
    if server.startswith("socks5://"):
        server = "socks5h://" + server[len("socks5://"):]
    t = time.time()
    try:
        r = requests.get("http://ip-api.com/json/", proxies={"http": server, "https": server}, timeout=15)
        j = r.json()
        return {"ok": True, "ip": j.get("query"), "country": j.get("country"), "countryCode": j.get("countryCode"),
                "city": j.get("city"), "timezone": j.get("timezone"), "ms": int((time.time() - t) * 1000),
                "at": time.time()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "at": time.time()}


# ------------------------------------------------------------------ bulk import

def import_profiles(text: str, template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One profile per line:  name|proxy|notes|folder|os|start_url

    Every field after the name is optional; proxy takes any parse_proxy format.
    """
    created, errors = [], []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        f = [x.strip() for x in line.split("|")] + [""] * 6
        name, proxy, notes, folder, os_name, url = f[:6]
        data = dict(template or {})
        data.update(name=name, notes=notes, folder=folder or data.get("folder", ""), start_url=url)
        if os_name:
            os_name = OS_ALIASES.get(os_name.lower(), os_name.lower())
            if os_name not in OS_KEYS:
                errors.append(f"line {n}: unknown OS {f[4]!r}")
                continue
            data["os"] = os_name
        if proxy:
            px = parse_proxy(proxy)
            if not px:
                errors.append(f"line {n}: cannot read proxy {proxy!r}")
                continue
            data["proxy"] = px
        for k in [k for k, v in data.items() if v == ""]:
            if k not in ("name",):
                data.pop(k)
        created.append(create_profile(data)["id"])
    return {"created": created, "errors": errors}


# --------------------------------------------------------------- browser builds

def browser_versions() -> Dict[str, Any]:
    """Installed Camoufox builds and the ones the repositories offer."""
    from camoufox.multiversion import list_installed, load_repo_cache

    installed = [{
        "repo": iv.repo_name, "version": iv.version.full_string, "path": iv.relative_path,
        "active": iv.is_active, "prerelease": iv.is_prerelease, "date": iv.created_at,
    } for iv in list_installed()]
    have = {(i["repo"], i["version"]) for i in installed}
    available = []
    for repo in load_repo_cache().get("repos", []):
        rname = repo.get("name", "").lower()
        for v in repo.get("versions", []):
            full = f"{v['version']}-{v['build']}"
            available.append({
                "repo": rname, "version": full, "prerelease": bool(v.get("is_prerelease")),
                "date": v.get("created_at"), "size": v.get("asset_size"),
                "installed": (rname, full) in have,
            })
    return {"installed": installed, "available": available, "default": get_settings()["browser"]}


# ------------------------------------------------------------------ macOS Dock

def hide_dock_icon() -> None:
    """Keep this Python process out of the Dock.

    Camoufox measures the screen through screeninfo -> AppKit NSScreen, which
    turns a framework Python into a Foreground app with its own Dock icon."""
    import sys

    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().setActivationPolicy_(2)  # Prohibited
    except Exception:
        pass


def dock_label(p: Dict[str, Any]) -> str:
    """Badge text for the profile's Dock icon: "" when disabled."""
    b = p.get("dock_badge") or {}
    mode = b.get("mode", "auto")
    if mode == "off":
        return ""
    if mode == "custom":
        return (b.get("text") or "").strip()[:4]
    name = (p.get("name") or "").strip()
    last = name.split()[-1] if name else ""
    if last and len(last) <= 4:      # "profile 3" -> "3", "mac B" -> "B"
        return last.upper()
    return name[:2].upper()


DOCK_MARK = "// FOXCLI-DOCK-BADGE v3"
DOCK_HOOK = DOCK_MARK + """
// Added by FoxLogin: badges the Dock icon with FOXCLI_DOCK_BADGE so several
// profile windows can be told apart. No-op without the variable or off macOS.
// Firefox clears the badge during startup, so it is re-applied by a timer.
(() => {
  try {
    const text = getenv("FOXCLI_DOCK_BADGE");
    if (!text) return;
    const dock = Components.classes["@mozilla.org/widget/macdocksupport;1"]
      .getService(Components.interfaces.nsIMacDockSupport);
    const timer = Components.classes["@mozilla.org/timer;1"].createInstance(Components.interfaces.nsITimer);
    globalThis.__foxcliDockTimer = timer;
    timer.initWithCallback({ notify() { try { if (dock.badgeText != text) dock.badgeText = text; } catch (e) {} } },
      1000, Components.interfaces.nsITimer.TYPE_REPEATING_SLACK);
  } catch (e) {}
})();
// FOXCLI-DOCK-BADGE end
"""


def install_dock_hook() -> None:
    """Make sure every installed macOS Camoufox build carries DOCK_HOOK.

    Re-run before each launch: a newly installed build starts without it, and
    an older version of the block is replaced."""
    import re
    import sys

    if sys.platform != "darwin":
        return
    from camoufox.pkgman import INSTALL_DIR

    for cfg in Path(INSTALL_DIR).glob("browsers/*/*/Camoufox.app/Contents/Resources/camoufox.cfg"):
        try:
            text = cfg.read_text()
            # Leave an equal or newer block alone: another FoxLogin build may share this cache
            have = [int(v) for v in re.findall(r"// FOXCLI-DOCK-BADGE v(\d+)", text)]
            if have and max(have) >= int(DOCK_MARK.rsplit("v", 1)[1]):
                continue
            text = re.sub(r"\n?// FOXCLI-DOCK-BADGE v\d+.*?// FOXCLI-DOCK-BADGE end\n", "", text, flags=re.S)
            tmp = cfg.with_suffix(".cfg.tmp")   # a launching Firefox never sees half a file
            tmp.write_text(text.rstrip("\n") + "\n\n" + DOCK_HOOK)
            tmp.replace(cfg)
        except OSError:
            pass


# ------------------------------------------------------------------ processes

def self_cmd(mode: str, *args: str) -> List[str]:
    """Command line that runs another part of FoxLogin ("runner" or "camoufox").

    From source that is `python -m <module>`; the packaged app has no Python
    to hand modules to, so it re-runs its own executable with --<mode>."""
    if FROZEN:
        return [sys.executable, f"--{mode}", *args]
    module = {"runner": "app.runner", "camoufox": "camoufox"}[mode]
    return [sys.executable, "-W", "ignore", "-m", module, *args]


def popen_kwargs() -> Dict[str, Any]:
    """Keep child processes alive and console-less after the app window closes."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def runner_alive(os_pid: int, profile_id: str) -> bool:
    """Is `os_pid` still the runner of `profile_id`? (pids get reused)

    os.kill(pid, 0) is not usable here: on Windows it terminates the process."""
    import psutil

    try:
        cmd = psutil.Process(os_pid).cmdline()
    except (psutil.Error, OSError):
        return False
    return profile_id in cmd


def stop_runner(os_pid: int, profile_id: str, timeout: float = 15) -> None:
    """Ask a runner to close its browser and save cookies, then make sure it is gone.

    The stop.flag file works on every OS; Windows has no SIGTERM to catch."""
    import psutil

    (_pdir(profile_id) / "stop.flag").write_text("1")
    try:
        proc = psutil.Process(os_pid)
        if os.name != "nt":
            proc.terminate()
        proc.wait(timeout)
    except psutil.TimeoutExpired:
        for p in proc.children(recursive=True) + [proc]:
            try:
                p.kill()
            except psutil.Error:
                pass
    except psutil.Error:
        pass
