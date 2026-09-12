#!/usr/bin/env python3
"""
Regenerate the README screenshots.

Drives Scribe headlessly with Textual's test pilot and exports each frame as
SVG. Hardware readings and the log directory are stubbed so the images are
reproducible on any machine (only the clock in the status bar changes).

    python3 docs/screenshots/generate.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
sys.path.insert(0, str(REPO))

import scribe  # noqa: E402
from textual.widgets import Input, TextArea  # noqa: E402

# ─── Stand-ins for hardware and system state ──────────────────────────────────

scribe.get_battery = lambda: "87%"
scribe.get_wifi = lambda: "Wi-Fi: Off"
scribe.get_bme280 = lambda: {
    "temp_c": 11.4, "temp_f": 52.5, "humidity": 68.2, "pressure": 1012.6
}
scribe.get_gps_coords = lambda timeout=2.0: {"lat": 54.9783, "lon": -1.6178}

SAMPLE_DIR = Path(tempfile.mkdtemp(prefix="scribe-shots-"))
scribe.ScribeApp._docs = property(lambda self: SAMPLE_DIR)

SAMPLE_LOGS = {
    "writing_2026-09-10_0742.txt":
        "Morning pages. The valley is still under cloud and the only sound is\n"
        "the beck running high after last night's rain.\n",
    "observation_2026-09-10_1615.txt":
        "OBSERVATION LOG — 2026-09-10 16:15\n"
        "Temp:     49.1°F / 9.5°C\n"
        "Humidity: 74.0%\n"
        "Weather:  low cloud, rain easing\n",
    "survival_2026-09-09_2030.txt":
        "SURVIVAL LOG — 2026-09-09 20:30\n"
        "Battery: 62%\n"
        "Resources:\n  Water: 2.5L\n  Food:  3 days\n  Fuel:  half canister\n",
    "writing_2026-09-08_2112.txt":
        "Notes toward the second chapter. The rain chapter, really — everything\n"
        "in it happens under weather.\n",
}
for _name, _body in SAMPLE_LOGS.items():
    (SAMPLE_DIR / _name).write_text(_body)

# ─── Sample content ───────────────────────────────────────────────────────────

WRITING_TEXT = """Day four. The rain came in off the fell just after dawn and has not
let up since, so I have spent the morning inside with the stove
ticking and nothing to do but write.

There is a particular quality to writing on a machine that cannot do
anything else. No tabs. No notifications. No small grey dot telling me
someone, somewhere, would like a moment of my attention. Just the
cursor, and the sound of the rain on the roof.
"""

SURVIVAL_TEXT = """SURVIVAL LOG — 2026-09-12 09:20
──────────────────────────────
Battery: 87%
Temp:    52.5°F / 11.4°C

Resources:
  Water: 2.5L + stream 200m N
  Food:  3 days
  Fuel:  half canister

Checklist:
  [x] Refill bottles
  [ ] Dry boots by stove
  [ ] Check forecast at 18:00

Notes:
Wind swung round to the north overnight. Colder.
"""

SIZE = (108, 30)


def _strip_webfonts(svg: str) -> str:
    """Drop the @font-face rules so the SVG needs no network fetch.

    Each text run carries an explicit textLength, so a local monospace
    fallback lays out identically.
    """
    while "@font-face {" in svg:
        start = svg.index("@font-face {")
        end = svg.index("}", svg.index("}", start) + 1) + 1  # nested src block
        svg = svg[:start] + svg[end:]
    return svg


async def shot(name, setup, size=SIZE):
    app = scribe.ScribeApp()
    app.notify = lambda *a, **k: None  # keep toasts out of the frame
    async with app.run_test(size=size) as pilot:
        await setup(pilot, app)
        await pilot.pause()
        svg = app.export_screenshot(title="Scribe")
    (OUT / f"{name}.svg").write_text(_strip_webfonts(svg))
    print(f"wrote {(OUT / f'{name}.svg').relative_to(REPO)}")


async def main():
    async def writing(pilot, app):
        editor = app.query_one(TextArea)
        editor.load_text(WRITING_TEXT)
        editor.move_cursor((6, 46))

    async def observation(pilot, app):
        await pilot.press("f2")
        await pilot.press("ctrl+n")
        await pilot.pause()
        editor = app.query_one(TextArea)
        text = editor.text
        text = text.replace("Weather:  \n", "Weather:  low cloud, rain easing\n")
        text = text.replace("Mood:     \n", "Mood:     settled\n")
        text += ("Beck is running high and brown. Three ravens over the crag at\n"
                 "first light, working the updraught on the north face.\n")
        editor.load_text(text)
        editor.move_cursor((11, 60))

    async def survival(pilot, app):
        await pilot.press("f3")
        editor = app.query_one(TextArea)
        editor.load_text(SURVIVAL_TEXT)
        editor.move_cursor((17, 0))

    async def search(pilot, app):
        await pilot.press("ctrl+f")
        await pilot.pause()
        app.screen.query_one(Input).value = "rain"
        await pilot.pause()

    await shot("writing", writing)
    await shot("observation", observation)
    await shot("survival", survival)
    await shot("search", search)


if __name__ == "__main__":
    asyncio.run(main())
