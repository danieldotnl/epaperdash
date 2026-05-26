"""Step 1: hardcoded fakes. Step 2 swaps gather_state() to hit HA REST API.

Event categories used by the template:
  - calendar   ▣  (regular agenda items)
  - school     ✎  (school-related)

Recycling and birthdays live in their own panels and aren't mixed into the
agenda.
"""


def gather_state() -> dict:
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
        "fact": (
            "Een groep flamingo's heet een <strong>flamboyance</strong>. "
            "Ze krijgen hun roze kleur van de carotenoïden in de pekelkreeftjes die ze eten."
        ),
    }
