"""Step 1: hardcoded fakes. Step 2 swaps gather_state() to hit HA REST API.

Event categories used by the template:
  - birthday   ✿  (verjaardag / in memoriam)
  - recycling  ♻  (afval inzameling)
  - calendar   ▣  (regular agenda items)
  - school     ✎  (school-related)
"""


def gather_state() -> dict:
    return {
        "header": {
            "weekday": "Dinsdag",
            "date": "26 mei 2026",
            "temp": 18,
            "condition": "Half bewolkt",
        },
        "days": [
            {
                "label": "VANDAAG",
                "weekday_short": "Di",
                "date_short": "26 mei",
                "weather_icon": "☀",
                "temp_high": "30°",
                "events": [
                    {"cat": "birthday", "title": "Verjaardag Jan (40)", "time": None},
                ],
            },
            {
                "label": "MORGEN",
                "weekday_short": "Wo",
                "date_short": "27 mei",
                "weather_icon": "⛅",
                "temp_high": "20°",
                "events": [
                    {"cat": "recycling", "title": "Papier", "time": None},
                    {"cat": "calendar", "title": "Sportles", "time": "19:00 – 20:00"},
                ],
            },
            {
                "label": None,
                "weekday_short": "Vr",
                "date_short": "29 mei",
                "weather_icon": "☁",
                "temp_high": "25°",
                "events": [
                    {"cat": "recycling", "title": "GFT", "time": None},
                    {"cat": "calendar", "title": "Diner met vrienden", "time": "19:00"},
                ],
            },
            {
                "label": None,
                "weekday_short": "Za",
                "date_short": "30 mei",
                "weather_icon": "☁",
                "temp_high": "23°",
                "events": [
                    {"cat": "calendar", "title": "Hardlopen", "time": "10:00"},
                ],
            },
            {
                "label": None,
                "weekday_short": "Zo",
                "date_short": "31 mei",
                "weather_icon": "☁",
                "temp_high": "19°",
                "events": [
                    {"cat": "calendar", "title": "Familiebezoek", "time": "14:00"},
                ],
            },
            {
                "label": None,
                "weekday_short": "Ma",
                "date_short": "1 jun",
                "weather_icon": "⛅",
                "temp_high": "21°",
                "events": [
                    {"cat": "recycling", "title": "PMD", "time": None},
                ],
            },
            {
                "label": None,
                "weekday_short": "Di",
                "date_short": "2 jun",
                "weather_icon": "☀",
                "temp_high": "24°",
                "events": [
                    {"cat": "birthday", "title": "Verjaardag Emma (8)", "time": None},
                    {"cat": "school", "title": "Schoolreisje", "time": "09:00"},
                ],
            },
        ],
        "fact": (
            "Een groep flamingo's heet een <strong>flamboyance</strong>. "
            "Ze krijgen hun roze kleur van de carotenoïden in de pekelkreeftjes die ze eten."
        ),
    }
