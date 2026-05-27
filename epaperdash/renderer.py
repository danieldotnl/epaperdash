"""Template + data -> PNG bytes. Single source of truth used by both the
FastAPI server and the offline CLI."""

from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Browser
from PIL import Image

WIDTH, HEIGHT = 800, 480
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class Renderer:
    def __init__(self, browser: Browser) -> None:
        self._browser = browser
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(["html", "j2"]),
        )

    async def render(self, data: dict, *, raw: bool = False) -> bytes:
        html = self._env.get_template("dashboard.html.j2").render(**data)
        ctx = await self._browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
        )
        try:
            page = await ctx.new_page()
            await page.set_content(html, wait_until="networkidle")
            rgb_png = await page.screenshot(full_page=False)
        finally:
            await ctx.close()

        if raw:
            return rgb_png

        # The ESPHome panel is 1-bit B/W — hard-threshold to pure black/white
        # so anti-aliased edges don't land on grays the panel can't show.
        quantized = Image.open(BytesIO(rgb_png)).convert("1", dither=Image.NONE)
        out = BytesIO()
        quantized.save(out, "PNG", optimize=True)
        return out.getvalue()
