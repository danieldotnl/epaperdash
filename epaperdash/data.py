"""Step 2: gather_state() pulls the wist-je-dat fact live from HA.

The rest of the dashboard (calendar, weather, recycling, birthdays) is still
hardcoded — separate iterations will wire each panel to its own HA entity.

Event categories used by the template:
  - calendar   ▣  (regular agenda items)
  - school     ✎  (school-related)

Recycling and birthdays live in their own panels and aren't mixed into the
agenda.
"""

import logging

from ha_client import HAClientError, get_state

log = logging.getLogger("epaperdash")

FACT_ENTITY = "input_text.wistjedat"
FACT_ERROR = "Wist je dat… <em>(kon Home Assistant niet bereiken)</em>"


async def gather_state() -> dict:
    try:
        fact = await get_state(FACT_ENTITY)
    except HAClientError as e:
        log.warning("fact fetch failed: %s", e)
        fact = FACT_ERROR

    return {
        "header": {
            "weekday": "Dinsdag",
            "date": "26 mei 2026",
            "weather": {
                "icon": "⛅",
                "temp_high": 21,
                "temp_low": 11,
                "condition": "Half bewolkt",
                "wind": "wind 12 km/u",
            },
        },
        "today_events": [],
        "tomorrow": {
            "weekday_short": "Wo",
            "date_short": "27 mei",
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
        "recycling": [
            {"date": "Wo 27 mei", "type": "Papier"},
            {"date": "Vr 29 mei", "type": "GFT"},
            {"date": "Ma 1 jun",  "type": "PMD"},
            {"date": "Wo 10 jun", "type": "Papier"},
        ],
        "birthdays": [
            {"date": "Di 2 jun",  "name": "Emma",   "age": 8},
            {"date": "Vr 12 jun", "name": "Jan",    "age": 40},
            {"date": "Za 22 aug", "name": "Sophie", "age": None},
            {"date": "Wo 4 sep",  "name": "Oma",    "age": None},
        ],
        "fact": fact,
    }
