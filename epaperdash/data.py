"""gather_state() collects the live dashboard payload from HA.

Live so far: wist-je-dat fact, afval (cyclus_* + cleanprofs_gft). Calendar,
weather, and birthdays are still hardcoded.

Event categories used by the template:
  - calendar   ▣  (regular agenda items)
  - school     ✎  (school-related)
  - waste      ♻  (today's pickup, surfaced in VANDAAG)

The Afval panel shows the rolling 4 nearest pickups regardless of whether
one falls today.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

from ha_client import HAClientError, get_entity, get_state

log = logging.getLogger("epaperdash")

FACT_ENTITY = "input_text.wistjedat"
FACT_ERROR = "Wist je dat… <em>(kon Home Assistant niet bereiken)</em>"

WEEKDAYS_NL = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
WEEKDAYS_SHORT_NL = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni",
             "juli", "augustus", "september", "oktober", "november", "december"]
MONTHS_SHORT_NL = ["jan", "feb", "mrt", "apr", "mei", "jun",
                   "jul", "aug", "sep", "okt", "nov", "dec"]

WASTE_FRACTIONS = {
    "gft": "GFT",
    "papier": "Papier",
    "pmd": "PMD",
    "restafval": "Restafval",
}
CLEANPROFS_ENTITY = "sensor.cleanprofs_gft"
WASTE_ROW_LIMIT = 4


def _parse_sort_date(value) -> date | None:
    """Parse afvalwijzer's YYYYMMDD sort_date (int or str)."""
    s = str(value or "")
    if len(s) != 8 or not s.isdigit():
        return None
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def _format_waste_date(d: date) -> str:
    return f"{WEEKDAYS_SHORT_NL[d.weekday()]} {d.day} {MONTHS_SHORT_NL[d.month - 1]}"


async def _fetch_attrs(entity_id: str) -> dict:
    """Return attributes dict for an entity, or {} on failure."""
    try:
        _, attrs = await get_entity(entity_id)
        log.info("attrs for %s: %r", entity_id, attrs)  # TEMP debug
        return attrs
    except HAClientError as e:
        log.warning("attrs fetch failed for %s: %s", entity_id, e)
        return {}


async def _gather_waste(today_date: date) -> tuple[list, list]:
    """Returns (rows for Afval panel, today's pickups as VANDAAG events)."""
    fraction_keys = list(WASTE_FRACTIONS.keys())
    *fraction_attrs, cleanprofs_attrs = await asyncio.gather(
        *(_fetch_attrs(f"sensor.cyclus_{k}") for k in fraction_keys),
        _fetch_attrs(CLEANPROFS_ENTITY),
    )
    cleanprofs_date = _parse_sort_date(cleanprofs_attrs.get("sort_date"))

    items: list[tuple[date, str]] = []
    for key, attrs in zip(fraction_keys, fraction_attrs):
        d = _parse_sort_date(attrs.get("sort_date"))
        if d is None:
            continue
        label = WASTE_FRACTIONS[key]
        if key == "gft" and cleanprofs_date == d:
            label = f"{label} + clean"
        items.append((d, label))

    items.sort(key=lambda x: x[0])
    items = items[:WASTE_ROW_LIMIT]

    rows = [{"date": _format_waste_date(d), "type": label} for d, label in items]
    today_events = [
        {"cat": "waste", "title": label, "time": None}
        for d, label in items if d == today_date
    ]
    return rows, today_events


async def gather_state() -> dict:
    try:
        fact = await get_state(FACT_ENTITY)
    except HAClientError as e:
        log.warning("fact fetch failed: %s", e)
        fact = FACT_ERROR

    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    waste_rows, waste_today_events = await _gather_waste(today.date())

    return {
        "header": {
            "weekday": WEEKDAYS_NL[today.weekday()],
            "date": f"{today.day} {MONTHS_NL[today.month - 1]} {today.year}",
            "weather": {
                "icon": "⛅",
                "temp_high": 21,
                "temp_low": 11,
                "condition": "Half bewolkt",
                "wind": "wind 12 km/u",
            },
        },
        "today_events": waste_today_events,
        "tomorrow": {
            "weekday_short": WEEKDAYS_SHORT_NL[tomorrow.weekday()],
            "date_short": f"{tomorrow.day} {MONTHS_SHORT_NL[tomorrow.month - 1]}",
            "weather_icon": "⛅",
            "temp_high": "20°",
            "events": [
                {"cat": "calendar", "title": "Sportles", "time": "19:00 – 20:00"},
            ],
        },
        "week_rows": [
            {"weekday_short": "Vr", "date_short": "29 mei", "cat": "calendar", "title": "Diner met vrienden", "time": "19:00"},
            {"weekday_short": "Za", "date_short": "30 mei", "cat": "calendar", "title": "Hardlopen",          "time": "10:00"},
            {"weekday_short": "Zo", "date_short": "31 mei", "cat": "calendar", "title": "Familiebezoek",      "time": "14:00"},
            {"weekday_short": "Di", "date_short": "2 jun",  "cat": "school",   "title": "Schoolreisje",       "time": "09:00"},
        ],
        "recycling": waste_rows,
        "birthdays": [
            {"date": "Di 2 jun",  "name": "Emma",   "age": 8},
            {"date": "Vr 12 jun", "name": "Jan",    "age": 40},
            {"date": "Za 22 aug", "name": "Sophie", "age": None},
            {"date": "Wo 4 sep",  "name": "Oma",    "age": None},
        ],
        "fact": fact,
    }
