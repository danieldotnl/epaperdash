"""FastAPI server that renders the dashboard PNG on demand.

Run:  uv run uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from playwright.async_api import async_playwright

from data import gather_state
from renderer import Renderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("epaperdash")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_playwright() as p:
        # In Docker: sandbox needs caps we don't have, and /dev/shm defaults to 64 MB.
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        app.state.renderer = Renderer(browser)
        log.info("chromium launched, renderer ready")
        try:
            yield
        finally:
            await browser.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    """Liveness check that bypasses Playwright/Chromium entirely."""
    return "ok"


@app.get("/dashboard.png")
async def dashboard(raw: bool = False) -> Response:
    """raw=true returns the un-dithered RGB screenshot (debug only)."""
    try:
        png = await app.state.renderer.render(await gather_state(), raw=raw)
    except Exception:
        log.exception("render failed")
        raise
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
