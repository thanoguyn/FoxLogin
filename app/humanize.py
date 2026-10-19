# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Trajectory glue code ported from Camoufox's CursorTrajectory.js (MPL-2.0)
# on top of the PyPI `cursory` package.
"""Humanized mouse, wheel and keyboard input for the WebDriver BiDi relay."""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import cursory

from app import core

RESERVED_ID_START = 1 << 31
FREQUENCY_HZ = 60
DEFAULT_MAX_TIME_SECONDS = 1.5

ELEMENT_CENTRE_FN = (
    "el => { const r = el.getBoundingClientRect();"
    " return [r.x + r.width / 2, r.y + r.height / 2, r.width, r.height, window.innerWidth, window.innerHeight]; }"
)

VIEWPORT_SIZE_FN = "() => [window.innerWidth, window.innerHeight]"


def perpendicular_distance(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float
) -> float:
    """Perpendicular distance from (px, py) to the line through (x0, y0)-(x1, y1)."""
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return math.hypot(px - x0, py - y0)
    return abs(dy * px - dx * py + x1 * y0 - y1 * x0) / dist


def humanized_steps(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    max_time: float = DEFAULT_MAX_TIME_SECONDS,
    min_time: float = 0.0,
    seed: Optional[int] = None,
    viewport: Optional[Tuple[int, int]] = None,
) -> Tuple[List[Tuple[int, int, int]], int]:
    """Intermediate points of a humanized move from (from_x, from_y) to (to_x, to_y).

    Ported from Camoufox's `CursorTrajectory.js` (MPL-2.0):
      - Calls `cursory.generate_trajectory(start, end, frequency=60, seed=...)`.
      - Scales the whole path into `[min_time, max_time]` instead of cutting off the end.
      - When the time is scaled, calls `generate_trajectory` again with the same `seed`
        and `frequency = 60 * scale` so events still arrive at about 60 Hz.
      - Rounds points to whole pixels and drops points that land on the previous pixel,
        folding their elapsed time into the next point.
      - Never emits the destination early; the caller's final `pointerMove` lands on it.
    """
    if not (math.isfinite(from_x) and math.isfinite(from_y)):
        return [], 0

    max_ms = max(0.0, float(max_time) * 1000.0)
    min_ms = min(max(0.0, float(min_time) * 1000.0), max_ms)

    if seed is None:
        seed = random.getrandbits(48)

    start_pt = (float(from_x), float(from_y))
    end_pt = (float(to_x), float(to_y))
    if start_pt == end_pt:
        return [], 0

    points, timings = cursory.generate_trajectory(
        start_pt, end_pt, frequency=FREQUENCY_HZ, seed=seed
    )

    recorded_ms = float(timings[-1]) if timings else 0.0
    scale = (
        min(max(recorded_ms, min_ms), max_ms) / recorded_ms
        if recorded_ms > 0.0
        else 0.0
    )

    if scale > 0.0 and scale != 1.0:
        points, timings = cursory.generate_trajectory(
            start_pt,
            end_pt,
            frequency=max(1, FREQUENCY_HZ * scale),
            seed=seed,
        )

    vw, vh = viewport if viewport else (None, None)
    steps: List[Tuple[int, int, int]] = []
    prev_x = int(round(from_x))
    prev_y = int(round(from_y))
    dest_x = int(round(to_x))
    dest_y = int(round(to_y))
    dispatched_ms = 0

    for i in range(1, len(points) - 1):
        x = int(round(points[i][0]))
        y = int(round(points[i][1]))
        if x < 0 or y < 0:
            continue
        if vw is not None and x >= vw:
            continue
        if vh is not None and y >= vh:
            continue
        if x == prev_x and y == prev_y:
            continue
        if x == dest_x and y == dest_y:
            continue
        elapsed_ms = int(round(timings[i] * scale))
        steps.append((x, y, max(0, elapsed_ms - dispatched_ms)))
        dispatched_ms = elapsed_ms
        prev_x, prev_y = x, y

    total_ms = int(round(recorded_ms * scale))
    trailing_delay_ms = max(0, total_ms - dispatched_ms)
    return steps, trailing_delay_ms


def generate_trajectory(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    max_time: float = DEFAULT_MAX_TIME_SECONDS,
    min_time: float = 0.0,
    seed: Optional[int] = None,
    viewport: Optional[Tuple[int, int]] = None,
) -> List[Dict[str, Any]]:
    """Generate humanized BiDi `pointerMove` steps from (x0, y0) to (x1, y1)."""
    steps, trailing_delay_ms = humanized_steps(
        x0,
        y0,
        x1,
        y1,
        max_time=max_time,
        min_time=min_time,
        seed=seed,
        viewport=viewport,
    )
    out: List[Dict[str, Any]] = [
        {
            "type": "pointerMove",
            "origin": "viewport",
            "x": x,
            "y": y,
            "duration": delay_ms,
        }
        for x, y, delay_ms in steps
    ]
    out.append(
        {
            "type": "pointerMove",
            "origin": "viewport",
            "x": int(round(x1)),
            "y": int(round(y1)),
            "duration": trailing_delay_ms,
        }
    )
    return out


def split_wheel_scroll(
    action: Dict[str, Any], rng: Optional[random.Random] = None
) -> List[Dict[str, Any]]:
    """Split a wheel scroll with a large deltaY/deltaX into ~100 px notches with short pauses."""
    rng = rng or random.Random()
    dx = int(round(float(action.get("deltaX") or 0)))
    dy = int(round(float(action.get("deltaY") or 0)))
    x = int(round(float(action.get("x") or 0)))
    y = int(round(float(action.get("y") or 0)))
    origin = action.get("origin", "viewport")

    if abs(dy) <= 120 and abs(dx) <= 120:
        out = dict(action, x=x, y=y, deltaX=dx, deltaY=dy)
        if "duration" in out and out["duration"] is not None:
            out["duration"] = int(out["duration"])
        return [out]

    steps: List[Dict[str, Any]] = []
    rem_x, rem_y = dx, dy
    while rem_x != 0 or rem_y != 0:
        notch_y = rng.randint(88, 112)
        notch_x = rng.randint(88, 112)
        step_y = max(-notch_y, min(notch_y, rem_y)) if abs(rem_y) > 120 else rem_y
        step_x = max(-notch_x, min(notch_x, rem_x)) if abs(rem_x) > 120 else rem_x
        rem_y -= step_y
        rem_x -= step_x
        steps.append({
            "type": "scroll",
            "x": x,
            "y": y,
            "deltaX": int(step_x),
            "deltaY": int(step_y),
            "duration": rng.randint(10, 22),
            "origin": origin,
        })
        if rem_x != 0 or rem_y != 0:
            steps.append({"type": "pause", "duration": rng.randint(18, 45)})
    return steps


class BiDiHumanizer:
    """Per-connection state and action rewriter for `/ws/<pid>`."""

    def __init__(self, pid: str, seed: Optional[int] = None) -> None:
        if seed is None and os.environ.get("FOXCLI_HUMAN_SEED"):
            try:
                seed = int(os.environ["FOXCLI_HUMAN_SEED"])
            except ValueError:
                pass
        self.pid = pid
        self.rng = random.Random(seed)
        self.positions: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.viewports: Dict[str, Tuple[int, int]] = {}
        self.next_id = RESERVED_ID_START
        self.pending: Dict[int, asyncio.Future] = {}

    def _start_pos(self, key: Tuple[str, str]) -> Tuple[float, float]:
        if key not in self.positions:
            vw, vh = self.viewports.get(key[0], (800, 500))
            self.positions[key] = (
                float(self.rng.randint(40, max(80, vw - 40))),
                float(self.rng.randint(40, max(80, vh - 40))),
            )
        return self.positions[key]

    def reset_context(self, context: Optional[str] = None) -> None:
        if not context:
            self.positions.clear()
            self.viewports.clear()
            return
        self.viewports.pop(context, None)
        for k in [k for k in self.positions if k[0] == context]:
            self.positions.pop(k, None)

    def handle_upstream_text(self, text: str) -> Optional[str]:
        """Process an upstream frame from Firefox. Returns None when swallowed."""
        if self.pending or "browsingContext.contextDestroyed" in text:
            try:
                msg = json.loads(text)
            except ValueError:
                msg = None
            if isinstance(msg, dict):
                mid = msg.get("id")
                if isinstance(mid, int) and mid in self.pending:
                    fut = self.pending.pop(mid)
                    if not fut.done():
                        fut.set_result(msg)
                    return None
                if msg.get("method") == "browsingContext.contextDestroyed":
                    ctx = (msg.get("params") or {}).get("context")
                    if ctx:
                        self.reset_context(ctx)
        return text

    async def _ensure_viewport(
        self, context: str, send_up: Callable[[str], Awaitable[None]]
    ) -> Optional[Tuple[int, int]]:
        if context in self.viewports:
            return self.viewports[context]
        req_id = self.next_id
        self.next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self.pending[req_id] = fut
        cmd = {
            "id": req_id,
            "method": "script.callFunction",
            "params": {
                "functionDeclaration": VIEWPORT_SIZE_FN,
                "target": {"context": context},
                "arguments": [],
                "awaitPromise": False,
            },
        }
        try:
            await send_up(json.dumps(cmd))
            resp = await asyncio.wait_for(fut, timeout=3.0)
            vals = resp["result"]["result"]["value"]
            vw, vh = int(vals[0]["value"]), int(vals[1]["value"])
            if vw > 0 and vh > 0:
                self.viewports[context] = (vw, vh)
                return (vw, vh)
        except Exception:
            self.pending.pop(req_id, None)
        return None

    async def _resolve_element_centre(
        self,
        context: str,
        element_ref: Dict[str, Any],
        send_up: Callable[[str], Awaitable[None]],
    ) -> Optional[Tuple[float, float, float, float]]:
        req_id = self.next_id
        self.next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self.pending[req_id] = fut
        cmd = {
            "id": req_id,
            "method": "script.callFunction",
            "params": {
                "functionDeclaration": ELEMENT_CENTRE_FN,
                "target": {"context": context},
                "arguments": [element_ref],
                "awaitPromise": False,
            },
        }
        try:
            await send_up(json.dumps(cmd))
            resp = await asyncio.wait_for(fut, timeout=5.0)
        except Exception:
            self.pending.pop(req_id, None)
            return None
        try:
            vals = resp["result"]["result"]["value"]
            if len(vals) >= 6:
                vw, vh = int(vals[4]["value"]), int(vals[5]["value"])
                if vw > 0 and vh > 0:
                    self.viewports[context] = (vw, vh)
            return (
                float(vals[0]["value"]),
                float(vals[1]["value"]),
                float(vals[2]["value"]),
                float(vals[3]["value"]),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    async def _rewrite_pointer_source(
        self,
        context: str,
        source: Dict[str, Any],
        max_time: float,
        send_up: Callable[[str], Awaitable[None]],
    ) -> List[List[Dict[str, Any]]]:
        """One block of actions per original tick; the original action ends its block."""
        actions = list(source.get("actions") or [])
        params = source.get("parameters") or {}
        if params.get("pointerType", "mouse") != "mouse":
            return [[a] for a in actions]

        sid = str(source.get("id") or "mouse")
        key = (context, sid)
        viewport = await self._ensure_viewport(context, send_up)
        out: List[List[Dict[str, Any]]] = []
        prev_type: Optional[str] = None

        for i, act in enumerate(actions):
            atype = act.get("type")
            if atype == "pointerMove":
                origin = act.get("origin", "viewport")
                ox = float(act.get("x") or 0)
                oy = float(act.get("y") or 0)
                cur_x, cur_y = self._start_pos(key)

                if origin == "viewport" or origin is None:
                    tx, ty = ox, oy
                elif origin == "pointer":
                    tx, ty = cur_x + ox, cur_y + oy
                elif isinstance(origin, dict) and origin.get("type") == "element" and origin.get("element"):
                    rect = await self._resolve_element_centre(context, origin["element"], send_up)
                    if rect is None:
                        out.append([act])
                        prev_type = atype
                        continue
                    viewport = self.viewports.get(context, viewport)
                    cx, cy, w, h = rect
                    jx = self.rng.uniform(-min(3.0, w * 0.15), min(3.0, w * 0.15)) if w > 4 else 0.0
                    jy = self.rng.uniform(-min(3.0, h * 0.15), min(3.0, h * 0.15)) if h > 4 else 0.0
                    tx = cx + ox + jx
                    ty = cy + oy + jy
                else:
                    out.append([act])
                    prev_type = atype
                    continue

                # If a single performActions starts with an initial positioning pointerMove
                # immediately followed by another pointerMove, jump to the start point first
                # so the second pointerMove traces the trajectory between the two points.
                next_act = actions[i + 1] if i + 1 < len(actions) else None
                if i == 0 and next_act and next_act.get("type") == "pointerMove" and (origin in ("viewport", None)):
                    ix, iy = int(round(tx)), int(round(ty))
                    out.append([{"type": "pointerMove", "origin": "viewport", "x": ix, "y": iy, "duration": 0}])
                    self.positions[key] = (float(ix), float(iy))
                    prev_type = atype
                    continue

                steps = generate_trajectory(
                    cur_x,
                    cur_y,
                    tx,
                    ty,
                    max_time=max_time,
                    seed=self.rng.randint(1, 0x7FFFFFFF),
                    viewport=viewport,
                )
                # Firefox BiDi's moveOverTime awaits requestAnimationFrame (~16.67 ms) per
                # step and starts its Date.now() timer ~4 ms into the frame (after the
                # previous step's IPC dispatch). Trimming 5 ms off each positive step
                # duration prevents a single 16 ms step from spilling into a second
                # animation frame (33 ms) and keeps the total move inside max_time.
                for s in steps:
                    d = int(s.get("duration") or 0)
                    if d > 1:
                        s["duration"] = max(1, d - 5)
                out.append(steps)
                self.positions[key] = (float(steps[-1]["x"]), float(steps[-1]["y"]))
                prev_type = atype

            elif atype in ("pointerDown", "pointerUp"):
                blk = []
                if prev_type == ("pointerMove" if atype == "pointerDown" else "pointerDown"):
                    blk.append({"type": "pause", "duration": self.rng.randint(40, 120)})
                out.append(blk + [act])
                prev_type = atype

            else:
                out.append([act])
                prev_type = atype

        return out

    def _rewrite_wheel_source(self, source: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        return [
            split_wheel_scroll(act, self.rng) if act.get("type") == "scroll" else [act]
            for act in source.get("actions") or []
        ]

    def _rewrite_key_source(self, source: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        out: List[List[Dict[str, Any]]] = []
        prev_type: Optional[str] = None
        for act in source.get("actions") or []:
            atype = act.get("type")
            if atype in ("keyDown", "keyUp") and prev_type in ("keyDown", "keyUp"):
                out.append([{"type": "pause", "duration": self.rng.randint(30, 90)}, act])
            else:
                out.append([act])
            prev_type = atype
        return out

    async def handle_client_text(
        self, text: str, send_up: Callable[[str], Awaitable[None]]
    ) -> str:
        """Rewrite `input.performActions` when `human_cursor.mode == 'on'`."""
        if "performActions" not in text and "releaseActions" not in text:
            return text
        try:
            msg = json.loads(text)
        except ValueError:
            return text
        if not isinstance(msg, dict):
            return text

        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "input.releaseActions":
            self.reset_context(params.get("context"))
            return text
        if method != "input.performActions":
            return text

        p = core.get_profile(self.pid)
        hc = (p or {}).get("human_cursor") or {}
        if hc.get("mode") != "on":
            return text
        max_time = core.human_max_time(p)
        context = str(params.get("context") or "")
        sources = params.get("actions")
        if not isinstance(sources, list) or not sources:
            return text

        blocks: List[List[List[Dict[str, Any]]]] = []
        for src in sources:
            stype = src.get("type")
            if stype == "pointer":
                blocks.append(await self._rewrite_pointer_source(context, src, max_time, send_up))
            elif stype == "wheel":
                blocks.append(self._rewrite_wheel_source(src))
            elif stype == "key":
                blocks.append(self._rewrite_key_source(src))
            else:
                blocks.append([[a] for a in src.get("actions") or []])

        # BiDi runs the sources in lockstep, one tick at a time. A tick that grew
        # into several actions in one source gets leading pauses in the others, so
        # e.g. a Shift held by a key source stays down until the click lands.
        ticks = max((len(b) for b in blocks), default=0)
        widths = [max((len(b[t]) for b in blocks if t < len(b)), default=1) for t in range(ticks)]
        rewritten_sources: List[Dict[str, Any]] = []
        for src, b in zip(sources, blocks):
            acts: List[Dict[str, Any]] = []
            for t, blk in enumerate(b):
                acts.extend([{"type": "pause"}] * (widths[t] - len(blk)) + blk)
            rewritten_sources.append(dict(src, actions=acts))

        params["actions"] = rewritten_sources
        msg["params"] = params
        return json.dumps(msg)
