# Third-party notices

FoxLogin's own source code is released under the [MIT License](LICENSE).

**This repository does not include any third-party code or binaries.** Python packages come from PyPI through `requirements.txt`. FoxLogin downloads the Camoufox browser and its add-ons at runtime into the user's Camoufox cache. Each component stays under its own license:

| Component | How FoxLogin uses it | License |
|---|---|---|
| [Camoufox](https://github.com/daijro/camoufox) browser (a Firefox fork) | Downloaded at runtime. Launched as a separate process | [MPL-2.0](https://www.mozilla.org/MPL/2.0/) |
| Mozilla Firefox (the base of Camoufox) | Part of the Camoufox download | [MPL-2.0](https://www.mozilla.org/MPL/2.0/) |
| [camoufox](https://pypi.org/project/camoufox/) Python package | pip dependency (launcher and fingerprint generation) | MIT |
| [uBlock Origin](https://github.com/gorhill/uBlock) | Optional add-on downloaded by Camoufox at runtime | GPL-3.0 |
| [Playwright](https://github.com/microsoft/playwright-python) | pip dependency (browser driver) | Apache-2.0 |
| [FastAPI](https://github.com/fastapi/fastapi) | pip dependency (web server) | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | pip dependency (ASGI server) | BSD-3-Clause |
| [Requests](https://github.com/psf/requests) | pip dependency | Apache-2.0 |
| [PySocks](https://github.com/Anorov/PySocks) | pip dependency (SOCKS proxy checks) | BSD-3-Clause |
| [websockets](https://github.com/python-websockets/websockets) | Used only by `tests/check_api.py` | BSD-3-Clause |

"Firefox" is a trademark of the Mozilla Foundation. FoxLogin is not affiliated with or endorsed by Mozilla, Camoufox or GoLogin.

## If you redistribute a packaged build

The MIT License covers FoxLogin's own code only. A packaged build that **bundles** any of the components above also has to meet their terms:

- **Camoufox / Firefox (MPL-2.0).** Ship the license text and tell users where to get the source code of the browser build you included. Any changes you make to MPL-licensed files must stay under MPL-2.0. Downloading the browser at first launch, as FoxLogin does today, avoids redistributing it.
- **Playwright (Apache-2.0) and any other bundled libraries.** Include their license and NOTICE files.
- **uBlock Origin (GPL-3.0).** If you bundle it, ship the GPL-3.0 license and offer its source code.
