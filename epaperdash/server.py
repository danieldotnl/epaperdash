"""FastAPI server that renders the dashboard PNG on demand.

Run:  uv run uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from playwright.async_api import async_playwright

from data import gather_state
from renderer import Renderer


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_playwright() as p:
        # In Docker: sandbox needs caps we don't have, and /dev/shm defaults to 64 MB.
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        app.state.renderer = Renderer(browser)
        try:
            yield
        finally:
            await browser.close()


app = FastAPI(lifespan=lifespan)


@app.get("/dashboard.png")
async def dashboard(raw: bool = False) -> Response:
    """raw=true returns the un-dithered RGB screenshot (debug only)."""
    png = await app.state.renderer.render(gather_state(), raw=raw)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
