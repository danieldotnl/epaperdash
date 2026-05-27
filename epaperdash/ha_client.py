"""Thin async wrapper around the HA REST API.

In the add-on (`homeassistant_api: true`) Supervisor injects SUPERVISOR_TOKEN and
the core API is at http://supervisor/core. For local dev, set HA_SERVER + HA_TOKEN
(e.g. via a repo-root .env) to point at a real HA instance instead. See
`_connection()`.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

import httpx

# Dev convenience: load HA_SERVER/HA_TOKEN from a repo-root .env. No-op in the
# add-on, where the file is absent and SUPERVISOR_TOKEN takes precedence.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

log = logging.getLogger("epaperdash")

BASE_URL = "http://supervisor/core"
TIMEOUT_SECONDS = 5.0
_UNAVAILABLE = {"", "unknown", "unavailable", "none"}


class HAClientError(Exception):
    """Raised when the HA state can't be retrieved or is not usable."""


def _connection() -> tuple[str, str]:
    """Return `(base_url, token)` for talking to HA.

    Prefer the Supervisor-injected token (add-on/production); fall back to
    HA_SERVER + HA_TOKEN for local dev. Raise HAClientError if neither is set.
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        return BASE_URL, token

    server = os.environ.get("HA_SERVER")
    token = os.environ.get("HA_TOKEN")
    if server and token:
        if not server.startswith(("http://", "https://")):
            server = f"http://{server}"
        return server.rstrip("/"), token

    raise HAClientError(
        "no HA credentials: set SUPERVISOR_TOKEN (add-on) or HA_SERVER + HA_TOKEN (dev)"
    )


async def get_entity(entity_id: str) -> tuple[str, dict]:
    """Return `(state, attributes)` for an entity, or raise HAClientError.

    Raises on: missing token, network error, non-2xx response, or a state
    value that's empty/unknown/unavailable.
    """
    base_url, token = _connection()

    url = f"{base_url}/api/states/{entity_id}"
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


async def get_forecasts(entity_id: str, forecast_type: str = "daily") -> list[dict]:
    """Return the forecast list for a weather entity, or raise HAClientError.

    Since HA 2023.9 the `forecast` attribute is gone; the multi-day forecast is
    only available via the `weather.get_forecasts` action. That action returns
    data, so the REST call needs `?return_response`. The response shape is::

        {"changed_states": [...],
         "service_response": {entity_id: {"forecast": [ {...}, ... ]}}}
    """
    base_url, token = _connection()

    url = f"{base_url}/api/services/weather/get_forecasts"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"entity_id": entity_id, "type": forecast_type}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url, headers=headers, params={"return_response": "1"}, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise HAClientError(f"HA forecast fetch failed for {entity_id}: {e}") from e

    service_response = data.get("service_response") if isinstance(data, dict) else None
    forecast = (service_response or {}).get(entity_id, {}).get("forecast")
    if not isinstance(forecast, list) or not forecast:
        raise HAClientError(f"no {forecast_type} forecast for {entity_id}")
    return forecast


async def calendar_events(entity_id: str, start: datetime, end: datetime) -> list[dict]:
    """Return events for `entity_id` in [start, end). Raises HAClientError on failure."""
    base_url, token = _connection()

    url = f"{base_url}/api/calendars/{entity_id}"
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
