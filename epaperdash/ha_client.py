"""Thin async wrapper around the HA Supervisor-proxied REST API.

Used inside an add-on with `homeassistant_api: true` so Supervisor injects
SUPERVISOR_TOKEN. Outside that context the token is absent and calls fail
fast with a clear log line.
"""

import logging
import os
from datetime import datetime

import httpx

log = logging.getLogger("epaperdash")

BASE_URL = "http://supervisor/core"
TIMEOUT_SECONDS = 5.0
_UNAVAILABLE = {"", "unknown", "unavailable", "none"}


class HAClientError(Exception):
    """Raised when the HA state can't be retrieved or is not usable."""


async def get_entity(entity_id: str) -> tuple[str, dict]:
    """Return `(state, attributes)` for an entity, or raise HAClientError.

    Raises on: missing token, network error, non-2xx response, or a state
    value that's empty/unknown/unavailable.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise HAClientError("SUPERVISOR_TOKEN not set")

    url = f"{BASE_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise HAClientError(f"HA fetch failed for {entity_id}: {e}") from e

    state = (data.get("state") or "").strip()
    if state.lower() in _UNAVAILABLE:
        raise HAClientError(f"{entity_id} is {state!r}")

    return state, data.get("attributes") or {}


async def get_state(entity_id: str) -> str:
    state, _ = await get_entity(entity_id)
    return state


async def calendar_events(entity_id: str, start: datetime, end: datetime) -> list[dict]:
    """Return events for `entity_id` in [start, end). Raises HAClientError on failure."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise HAClientError("SUPERVISOR_TOKEN not set")

    url = f"{BASE_URL}/api/calendars/{entity_id}"
    params = {"start": start.isoformat(), "end": end.isoformat()}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise HAClientError(f"HA calendar fetch failed for {entity_id}: {e}") from e

    if not isinstance(data, list):
        raise HAClientError(f"unexpected calendar payload for {entity_id}: {type(data).__name__}")
    return data
