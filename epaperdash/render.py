"""CLI: render output PNGs without spinning up the server.

  uv run python render.py [--raw]            # the dashboard
  uv run python render.py --photo <url|path> # a Spectra 6 dithered photo
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from data import gather_state
from dither import dither
from renderer import Renderer

HERE = Path(__file__).resolve().parent


async def render_dashboard(raw: bool) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        renderer = Renderer(browser)
        png = await renderer.render(await gather_state(), raw=raw)
        await browser.close()

    out = HERE / ("dashboard_raw.png" if raw else "dashboard.png")
    out.write_bytes(png)
    print(f"wrote {out.name} ({len(png)} bytes)")


async def render_photo(src: str) -> None:
    if src.startswith(("http://", "https://")):
        from ha_client import fetch_image

        data = await fetch_image(src)
    else:
        data = Path(src).read_bytes()

    out = HERE / "photo.png"
    out.write_bytes(dither(data))
    print(f"wrote {out.name} from {src}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--photo" in args:
        i = args.index("--photo")
        if i + 1 >= len(args):
            sys.exit("usage: python render.py --photo <url|path>")
        asyncio.run(render_photo(args[i + 1]))
    else:
        asyncio.run(render_dashboard(raw="--raw" in args))
