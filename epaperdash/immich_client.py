"""Thin async wrapper around the Immich REST API.

Immich runs as its own HA add-on; this add-on reaches it over the network. Set
IMMICH_URL (e.g. http://192.168.1.172:2283 — the host IP + Immich's mapped port,
not localhost) and IMMICH_API_KEY (Immich -> Account Settings -> API Keys). Auth
is the `x-api-key` header on every call. IMMICH_ALBUM is the default album ID to
pull from; callers can override it per request.
"""

import logging
import os
import random
import re
from pathlib import Path

import httpx

# Dev convenience: load IMMICH_* from a repo-root .env (shared with ha_client).
# No-op in the add-on, where the file is absent and options come from env.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

log = logging.getLogger("epaperdash")

TIMEOUT_SECONDS = 10.0
IMAGE_TIMEOUT_SECONDS = 30.0  # photos are larger than the album JSON

# Remember the asset shown last per album so we never refresh to the same photo
# twice in a row. Keyed by the resolved album id; survives for the process life.
_last_shown: dict[str, str] = {}


class ImmichClientError(Exception):
    """Raised when an Immich photo can't be retrieved."""


def _connection() -> tuple[str, dict[str, str]]:
    """Return `(base_url, headers)` for talking to Immich, or raise."""
    url = os.environ.get("IMMICH_URL")
    key = os.environ.get("IMMICH_API_KEY")
    if not url or not key:
        raise ImmichClientError("set IMMICH_URL and IMMICH_API_KEY to use ?immich=")
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/"), {"x-api-key": key, "Accept": "application/json"}


async def get_random_album_photo(album_id: str | None = None) -> bytes:
    """Return the JPEG bytes of a random IMAGE asset from an Immich album.

    `album_id` defaults to IMMICH_ALBUM. Fetches the album's asset list, picks a
    random photo, and returns its `preview` thumbnail (a downsized JPEG, ideal for
    the 800x480 panel and far lighter than the original). Raises ImmichClientError
    on missing config, network/HTTP errors, or an album with no usable images.
    """
    base_url, headers = _connection()
    album_id = album_id or os.environ.get("IMMICH_ALBUM")
    if not album_id:
        raise ImmichClientError("no album: set IMMICH_ALBUM or pass ?immich=<album-id>")
    # album_id lands in the request path; Immich IDs are UUIDs, so reject anything
    # else to block path traversal / endpoint injection from the ?immich= query.
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", album_id):
        raise ImmichClientError(f"invalid album id: {album_id!r}")

    async with httpx.AsyncClient(
        timeout=IMAGE_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        try:
            resp = await client.get(
                f"{base_url}/api/albums/{album_id}", headers=headers, timeout=TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            album = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ImmichClientError(f"album fetch failed for {album_id}: {e}") from e

        assets = [a for a in (album.get("assets") or []) if a.get("type") == "IMAGE"]
        if not assets:
            raise ImmichClientError(f"album {album_id!r} has no image assets")

        # Exclude the photo we showed last time so a refresh always changes the
        # screen. With only one image there's nothing else to pick, so keep it.
        candidates = [a for a in assets if a["id"] != _last_shown.get(album_id)] or assets
        asset_id = random.choice(candidates)["id"]
        _last_shown[album_id] = asset_id
        try:
            resp = await client.get(
                f"{base_url}/api/assets/{asset_id}/thumbnail",
                headers=headers,
                params={"size": "preview"},
            )
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as e:
            raise ImmichClientError(f"thumbnail fetch failed for asset {asset_id}: {e}") from e
