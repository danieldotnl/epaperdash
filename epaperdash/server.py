"""FastAPI server that renders the dashboard PNG on demand.

Run:  uv run uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from playwright.async_api import async_playwright

from data import gather_state
from dither import dither
from ha_client import HAClientError, fetch_image, get_entity_image
from immich_client import ImmichClientError, get_random_album_photo
from renderer import Renderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("epaperdash")


def _load_addon_options() -> None:
    """Fold HA add-on options into os.environ (no-op outside the add-on).

    Supervisor writes the configured options to /data/options.json; the bare
    `uvicorn` CMD doesn't export them, so we map each key to its UPPER_CASE env
    var (immich_url -> IMMICH_URL). Existing env wins, so a dev `.env` and the
    injected SUPERVISOR_TOKEN are never clobbered. Blank options are skipped.
    """
    path = Path("/data/options.json")
    if not path.is_file():
        return
    try:
        options = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        log.warning("could not read %s: %s", path, e)
        return
    for key, value in options.items():
        env_key = key.upper()
        if env_key not in os.environ and value not in (None, ""):
            os.environ[env_key] = str(value)


_load_addon_options()


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


def _img_media_type(data: bytes) -> str:
    """Best-effort content type from magic bytes (used for the raw passthrough)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


# Dev-only: photos dropped here are servable via ?sample=. Not shipped in the
# add-on image (the dir is git-ignored), so ?sample= simply 404s in production.
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def _read_sample(name: str) -> bytes:
    """Read a file from the local samples/ dir; .name strips any path traversal."""
    path = SAMPLES_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no sample {name!r} in {SAMPLES_DIR}")
    return path.read_bytes()


@app.get("/photo.png")
async def photo(
    url: str | None = None,
    entity: str | None = None,
    sample: str | None = None,
    immich: str | None = None,
    fit: str = "cover",
    raw: bool = False,
) -> Response:
    """Fetch a photo and dither it for the Spectra 6 (reTerminal E1002) panel.

    Source — exactly one of: ?url= (any image URL), ?entity= (an HA camera.*/image.*),
    ?sample= (a filename in the local samples/ dir, dev only), or ?immich= (a random
    photo from an Immich album; pass an album ID, or "1"/"" to use IMMICH_ALBUM).
    ?fit=cover|contain controls framing; ?raw=true returns the fetched source untouched.

    If PHOTO_ENTITY is set, an ?immich request serves that HA camera.*/image.* entity
    instead, so what the panel shows can change without reflashing its URL.
    """
    if immich is not None and not (url or entity or sample) and os.environ.get("PHOTO_ENTITY"):
        entity, immich = os.environ["PHOTO_ENTITY"], None

    # immich uses `is not None` so a bare ?immich (empty value) selects the configured
    # album; the others require a non-empty value, else a blank ?url= is a 400 not a 502.
    if [bool(url), bool(entity), bool(sample), immich is not None].count(True) != 1:
        raise HTTPException(
            status_code=400,
            detail="provide exactly one of ?url=, ?entity=, ?sample= or ?immich=",
        )

    try:
        if url:
            src = await fetch_image(url)
        elif entity:
            src = await get_entity_image(entity)
        elif sample:
            src = _read_sample(sample)
        else:
            # ?immich alone (no value) or ?immich=1 -> configured album; else treat as album ID.
            album_id = immich if immich not in ("", "1") else None
            src = await get_random_album_photo(album_id)
    except (HAClientError, ImmichClientError) as e:
        log.warning("photo fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    if raw:
        return Response(
            content=src,
            media_type=_img_media_type(src),
            headers={"Cache-Control": "no-store"},
        )

    try:
        png = dither(src, fit=fit)
    except Exception:
        log.exception("dither failed")
        raise
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
