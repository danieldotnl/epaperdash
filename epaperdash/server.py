"""FastAPI server that renders the dashboard PNG on demand.

Run:  uv run uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from playwright.async_api import async_playwright

from data import gather_state
from renderer import Renderer


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_playwright() as p:
        # In Docker: sandbox needs caps we don't have, and /dev/shm defaults to 64 MB.
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        app.state.renderer = Renderer(browser)
        print("epaperdash: chromium launched, renderer ready", file=sys.stderr, flush=True)
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
        png = await app.state.renderer.render(gather_state(), raw=raw)
    except Exception:
        print("epaperdash: render failed", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        raise
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
