"""Step 1: hardcoded fakes. Step 2 swaps gather_state() to hit HA REST API."""


def gather_state() -> dict:
    return {
        "day": "Monday",
        "date": "May 25, 2026",
        "events": [
            {"time": "08:30", "title": "School run — Anna",     "meta": "Drop-off, back by 09:00"},
            {"time": "10:00", "title": "Dentist — Daniel",      "meta": "Dr. Visser, Utrechtsestraat"},
            {"time": "14:30", "title": "Grocery delivery",           "meta": "Picnic, 14:30 – 15:00 window"},
            {"time": "19:00", "title": "Family movie night",         "meta": "Living room, popcorn duty: Daniel"},
        ],
        "weather": {
            "temp": 18,
            "condition": "Partly cloudy",
            "range": "H 21° / L 11° · wind 12 km/h",
            "forecast": [
                {"when": "Tue", "icon": "☀", "temp": "22° / 12°"},
                {"when": "Wed", "icon": "⛅", "temp": "19° / 10°"},
                {"when": "Thu", "icon": "☔", "temp": "15° / 09°"},
            ],
        },
        "fact": (
            "A group of flamingos is called a <strong>flamboyance</strong>. "
            "They get their pink colour from the carotenoids in the brine shrimp they eat."
        ),
    }
