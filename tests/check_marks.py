"""Verify that every mark changes the value it should, and only that.

Profiles A and B are fully masked, R1 and R2 are all "Real". Expectations:
  * masked fields differ between A and B, and from the real ones;
  * real fields are identical between R1 and R2 (the host's real value);
  * relaunching A gives the same stable values (GPU, audio, media, fonts).
Needs the server running (python3 run.py) for the /fptest page.
"""
import json
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("FOXCLI_DATA", tempfile.mkdtemp(prefix="foxcli-test-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camoufox.sync_api import Camoufox  # noqa: E402

from app import core  # noqa: E402

URL = os.environ.get("FPTEST_URL", "http://127.0.0.1:8765/fptest")
HEADLESS = os.environ.get("HEADFUL") is None


def measure(p):
    kw = core.camoufox_kwargs(p, headless=HEADLESS)
    # auto-grant getUserMedia so enumerateDevices lists every device
    kw["firefox_user_prefs"]["media.navigator.permission.disabled"] = True
    with Camoufox(**kw) as b:
        page = b.new_page()
        page.goto(URL + "?gum=1")
        page.wait_for_function("document.title === 'done'", timeout=30000)
        return json.loads(page.inner_text("#out"))


REAL = {"canvas": "real", "webgl_image": "real", "audio": "real",
        "webgl_info": {"mode": "real"}, "media_devices": {"mode": "real"}}
# WebGL Image noise is opt-in (pixelscan detects it), so A and B turn it on
A = core.create_profile({"name": "A", "webgl_image": "noise"})
B = core.create_profile({"name": "B", "webgl_image": "noise", "media_devices": {"mode": "masked", "webcams": 2, "micros": 1, "speakers": 2}})
R1 = core.create_profile(dict(REAL, name="R1"))
R2 = core.create_profile(dict(REAL, name="R2"))
W1 = core.create_profile({"name": "W1", "os": "windows"})
W2 = core.create_profile({"name": "W2", "os": "windows"})
while W2["webgl_info"]["renderer"] == W1["webgl_info"]["renderer"]:
    W2 = core.update_profile(W2["id"], {})  # redraw until the GPUs differ
    core.new_fingerprint(W2); core.save_profile(W2); W2 = core.get_profile(W2["id"])

res = {}
for name, p in (("A", A), ("A2", A), ("B", B), ("R1", R1), ("R2", R2), ("W1", W1), ("W2", W2)):
    res[name] = measure(p)
    print(name, json.dumps({k: res[name][k] for k in (
        "canvasHash", "webglImageHash", "webglPixelsHash", "webglRenderer", "audioHash", "mediaDevices",
        "screen", "fonts", "clientRects", "timezone", "languages")}, ensure_ascii=False))

ok = True


def check(desc, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + desc)


a, a2, b, r1, r2 = (res[k] for k in ("A", "A2", "B", "R1", "R2"))
for f in ("canvasHash", "webglImageHash", "webglPixelsHash", "audioHash"):
    check(f"{f}: masked A != B", a[f] != b[f])
    check(f"{f}: masked A != real", a[f] != r1[f] and b[f] != r1[f])
    check(f"{f}: real R1 == R2 (host value)", r1[f] == r2[f])
w1, w2 = res["W1"], res["W2"]
check("webglRenderer: Windows W1 != W2", w1["webglRenderer"] != w2["webglRenderer"])
check("webglRenderer: Windows masked != host real", w1["webglRenderer"] != r1["webglRenderer"])
check("webgl renderer applied = profile choice (W1)", w1["webglRenderer"] == W1["webgl_info"]["renderer"])
check("userAgent: Windows identity", "Windows NT" in w1["userAgent"])
check("webglRenderer: real R1 == R2", r1["webglRenderer"] == r2["webglRenderer"])
check("mediaDevices B = cam 2 / mic 1 / sp 2", b["mediaDevices"] == "cam 2 / mic 1 / sp 2")
check("mediaDevices A = cam 1 / mic 1 / sp 1", a["mediaDevices"] == "cam 1 / mic 1 / sp 1")
for f in ("audioHash", "webglRenderer", "webglParams", "mediaDevices", "userAgent", "fonts"):
    check(f"{f}: stable across relaunch of A", a[f] == a2[f])
check("canvas stable within one session", all(x["canvasRepeatSame"] for x in res.values()))
check("solid-colour WebGL buffer untouched by noise (red-box probe)",
      len({x["webglSolidHash"] for x in res.values()}) == 1)
print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
