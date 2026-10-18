"""Open a profile headful on the checker sites, save screenshots and verdicts.

    python3 tests/check_sites.py <profile_id> [out_dir]

Uses the same launch options as the Run button.
"""
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camoufox.sync_api import Camoufox  # noqa: E402

from app import core  # noqa: E402

pid = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "check-results"
os.makedirs(out, exist_ok=True)
p = core.get_profile(pid)
kw, loc = core.launch_kwargs(p)
udir = core._pdir(pid) / "userdata"
udir.mkdir(exist_ok=True)

SITES = [
    ("pixelscan", "https://pixelscan.net/fingerprint-check", 35),
    ("iphey", "https://iphey.com/", 30),
    ("browserscan", "https://www.browserscan.net/", 30),
    ("creepjs", "https://abrahamjuliot.github.io/creepjs/", 30),
]
only = os.environ.get("SITES")
results = {"profile": p["name"], "os": p["os"], "location": loc}
with Camoufox(persistent_context=True, user_data_dir=str(udir), **kw) as ctx:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for name, url, wait in SITES:
        if only and name not in only.split(","):
            continue
        try:
            page.goto(url, timeout=90000, wait_until="domcontentloaded")
        except Exception as e:
            results[name] = f"load error: {e}"
            continue
        time.sleep(wait)
        page.screenshot(path=f"{out}/{name}.png", full_page=False)
        try:
            page.screenshot(path=f"{out}/{name}-full.png", full_page=True)
        except Exception:
            pass
        results[name] = page.inner_text("body")[:6000]
json.dump(results, open(f"{out}/results.json", "w"), ensure_ascii=False, indent=1)
print(f"saved to {out}")
