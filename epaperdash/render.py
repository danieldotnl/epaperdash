"""CLI: render dashboard.png from the current data without spinning up the server.

  uv run python render.py [--raw]
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from data import gather_state
from renderer import Renderer

HERE = Path(__file__).resolve().parent


async def main(raw: bool) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        renderer = Renderer(browser)
        png = await renderer.render(gather_state(), raw=raw)
        await browser.close()

    out = HERE / ("dashboard_raw.png" if raw else "dashboard.png")
    out.write_bytes(png)
    print(f"wrote {out.name} ({len(png)} bytes)")


if __name__ == "__main__":
    asyncio.run(main(raw="--raw" in sys.argv))
