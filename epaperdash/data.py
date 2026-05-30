"""gather_state() collects the live dashboard payload from HA.

Live: wist-je-dat fact, afval (cyclus_* + cleanprofs_gft), agenda
(calendar.* entities), birthdays, and weather (weather.* entity state +
the daily get_forecasts action). Nothing on the dashboard is hardcoded.

Event categories used by the template:
  - calendar   ◆  (regular agenda items — calendar.home_assistant)
  - school     ✎  (calendar.parro_agenda)
  - holiday    ★  (calendar.holidays_in_netherlands)
  - birthday   ✿  (calendar.ha_birthdays, also surfaced in VANDAAG/MORGEN)
  - waste      ♻  (today's pickup, surfaced in VANDAAG)

The Afval panel shows the rolling 4 nearest pickups regardless of whether
one falls today. Multi-day calendar events are repeated per day they span.
"""

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta

from ha_client import HAClientError, calendar_events, get_entity, get_forecasts, get_state

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

CALENDARS = [
    ("calendar.holidays_in_netherlands", "holiday"),
    ("calendar.home_assistant", "calendar"),
    ("calendar.parro_agenda", "school"),
]
AGENDA_ROW_CAP = 7  # max entry rows across VANDAAG + MORGEN + DEZE WEEK combined
CALENDAR_WINDOW_DAYS = 8  # enough to cover today + tomorrow + next-7-day panel

WEATHER_ENTITY = "weather.tomorrow_io_home_daily"
# HA's standardized condition strings → monochrome glyph + Dutch label.
# Glyphs render as text (not colour emoji) via font-variant-emoji in the template.
WEATHER_GLYPHS = {
    "clear-night": "☾", "cloudy": "☁", "fog": "🌫", "hail": "🌧",
    "lightning": "🌩", "lightning-rainy": "⛈", "partlycloudy": "⛅",
    "pouring": "🌧", "rainy": "🌦", "snowy": "❄", "snowy-rainy": "🌨",
    "sunny": "☀", "windy": "🌬", "windy-variant": "🌬", "exceptional": "⚠",
}
WEATHER_CONDITIONS_NL = {
    "clear-night": "Helder", "cloudy": "Bewolkt", "fog": "Mist", "hail": "Hagel",
    "lightning": "Onweer", "lightning-rainy": "Onweer en regen",
    "partlycloudy": "Half bewolkt", "pouring": "Stortregen", "rainy": "Regen",
    "snowy": "Sneeuw", "snowy-rainy": "Natte sneeuw", "sunny": "Zonnig",
    "windy": "Winderig", "windy-variant": "Winderig", "exceptional": "Extreem weer",
}

BATTERY_ENTITY = "sensor.epaper_bw_battery_level"

BIRTHDAYS_ENTITY = "calendar.ha_birthdays"
BIRTHDAY_PANEL_LIMIT = 4
BIRTHDAY_WINDOW_DAYS = 366  # one full year so every annual entry yields one occurrence
_BIRTHDAY_YEAR_RE = re.compile(r"^(?P<name>.*?)\s*\(\s*(?P<year>\d{4})\s*\)\s*$")


def _parse_sort_date(value) -> date | None:
    """Parse afvalwijzer's YYYYMMDD Sort_date (int or str)."""
    s = str(value or "")
    if len(s) != 8 or not s.isdigit():
        return None
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def _format_short_date(d: date) -> str:
    return f"{WEEKDAYS_SHORT_NL[d.weekday()]} {d.day} {MONTHS_SHORT_NL[d.month - 1]}"


async def _fetch_attrs(entity_id: str) -> dict:
    """Return attributes dict for an entity, or {} on failure."""
    try:
        _, attrs = await get_entity(entity_id)
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
    cleanprofs_date = _parse_sort_date(cleanprofs_attrs.get("Sort_date"))

    items: list[tuple[date, str]] = []
    for key, attrs in zip(fraction_keys, fraction_attrs):
        d = _parse_sort_date(attrs.get("Sort_date"))
        if d is None:
            continue
        label = WASTE_FRACTIONS[key]
        if key == "gft" and cleanprofs_date == d:
            label = f"{label} + clean"
        items.append((d, label))

    items.sort(key=lambda x: x[0])
    items = items[:WASTE_ROW_LIMIT]

    rows = [{"date": _format_short_date(d), "type": label} for d, label in items]
    today_events = [
        {"cat": "waste", "title": label, "time": ""}
        for d, label in items if d == today_date
    ]
    return rows, today_events


def _dates_covered(start_dt: datetime, end_dt: datetime, all_day: bool) -> list[date]:
    """Inclusive list of dates an event covers. HA's all-day end is exclusive."""
    if all_day:
        d, last = start_dt.date(), end_dt.date()  # last is exclusive
        out = []
        while d < last:
            out.append(d)
            d += timedelta(days=1)
        return out
    d, last = start_dt.date(), end_dt.date()
    if end_dt.time() == time(0, 0):  # ends exactly at midnight → previous day is last
        last -= timedelta(days=1)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=1)
    return out


def _normalize_event(raw: dict, cat: str) -> dict | None:
    """Convert HA calendar JSON into our internal shape, or None if unparseable."""
    summary = (raw.get("summary") or "").strip() or "(zonder titel)"
    s = raw.get("start") or {}
    e = raw.get("end") or {}
    try:
        if "date" in s:
            all_day = True
            start_dt = datetime.combine(date.fromisoformat(s["date"]), time.min).astimezone()
            end_dt = datetime.combine(date.fromisoformat(e["date"]), time.min).astimezone()
        else:
            all_day = False
            start_dt = datetime.fromisoformat(s["dateTime"]).astimezone()
            end_dt = datetime.fromisoformat(e["dateTime"]).astimezone()
    except (KeyError, ValueError) as ex:
        log.warning("unparseable event %r: %s", raw, ex)
        return None
    return {
        "cat": cat,
        "title": summary,
        "all_day": all_day,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "dates": _dates_covered(start_dt, end_dt, all_day),
    }


def _fmt_range(ev: dict) -> str:
    """HH:MM – HH:MM for same-day timed events; just HH:MM if multi-day; empty for all-day."""
    if ev["all_day"]:
        return ""
    s, e = ev["start_dt"], ev["end_dt"]
    if s.date() == e.date():
        return f"{s:%H:%M} – {e:%H:%M}"
    return f"{s:%H:%M}"


def _fmt_start(ev: dict) -> str:
    """Just HH:MM start (or empty for all-day) — used in DEZE WEEK rows."""
    return "" if ev["all_day"] else f"{ev['start_dt']:%H:%M}"


async def _fetch_calendar(entity_id: str, cat: str, start: datetime, end: datetime) -> list[dict]:
    """Fetch + normalize events for a single calendar. Returns [] on failure."""
    try:
        raw_events = await calendar_events(entity_id, start, end)
    except HAClientError as e:
        log.warning("calendar fetch failed for %s: %s", entity_id, e)
        return []
    return [ev for ev in (_normalize_event(r, cat) for r in raw_events) if ev]


async def _gather_calendar(now: datetime) -> tuple[list, list, list]:
    """Returns (today_events, tomorrow_events, week_rows) drawn from CALENDARS."""
    today_d = now.date()
    tomorrow_d = today_d + timedelta(days=1)
    week_end_d = today_d + timedelta(days=7)

    window_start = datetime.combine(today_d, time.min).astimezone()
    window_end = datetime.combine(
        today_d + timedelta(days=CALENDAR_WINDOW_DAYS), time.min
    ).astimezone()

    results = await asyncio.gather(*(
        _fetch_calendar(entity_id, cat, window_start, window_end)
        for entity_id, cat in CALENDARS
    ))
    events = [ev for sub in results for ev in sub]

    today_events: list[dict] = []
    tomorrow_events: list[dict] = []
    week_rows: list[dict] = []

    for ev in events:
        for d in ev["dates"]:
            sort_dt = ev["start_dt"] if not ev["all_day"] else datetime.combine(d, time.min).astimezone()
            if d == today_d:
                if not ev["all_day"] and ev["end_dt"] <= now:
                    continue  # already over earlier today
                today_events.append({
                    "cat": ev["cat"], "title": ev["title"],
                    "time": _fmt_range(ev), "_sort": sort_dt,
                })
            elif d == tomorrow_d:
                tomorrow_events.append({
                    "cat": ev["cat"], "title": ev["title"],
                    "time": _fmt_range(ev), "_sort": sort_dt,
                })
            elif tomorrow_d < d <= week_end_d:
                week_rows.append({
                    "weekday_short": WEEKDAYS_SHORT_NL[d.weekday()],
                    "date_short": f"{d.day} {MONTHS_SHORT_NL[d.month - 1]}",
                    "cat": ev["cat"], "title": ev["title"],
                    "time": _fmt_start(ev),
                    "_sort": (d, sort_dt),
                })

    today_events.sort(key=lambda x: x["_sort"])
    tomorrow_events.sort(key=lambda x: x["_sort"])
    week_rows.sort(key=lambda x: x["_sort"])
    for lst in (today_events, tomorrow_events, week_rows):
        for x in lst:
            x.pop("_sort")

    return today_events, tomorrow_events, week_rows


def _parse_birthday_title(summary: str) -> tuple[str, int | None]:
    """Extract (name, birth_year). Year is None when the title has no (YYYY) suffix."""
    m = _BIRTHDAY_YEAR_RE.match(summary)
    if m:
        return m.group("name").strip(), int(m.group("year"))
    return summary.strip(), None


def _birthday_event_title(name: str, age: int | None) -> str:
    return f"{name} ({age})" if age is not None else name


async def _gather_birthdays(now: datetime) -> tuple[list, list, list]:
    """Returns (panel_rows, today_events, tomorrow_events) from calendar.ha_birthdays."""
    today_d = now.date()
    tomorrow_d = today_d + timedelta(days=1)
    window_start = datetime.combine(today_d, time.min).astimezone()
    window_end = datetime.combine(
        today_d + timedelta(days=BIRTHDAY_WINDOW_DAYS), time.min
    ).astimezone()

    try:
        raw_events = await calendar_events(BIRTHDAYS_ENTITY, window_start, window_end)
    except HAClientError as e:
        log.warning("birthdays fetch failed: %s", e)
        return [], [], []

    entries: list[tuple[date, str, int | None]] = []
    for raw in raw_events:
        ev = _normalize_event(raw, "birthday")
        if not ev or not ev["dates"]:
            continue
        d = ev["dates"][0]
        name, year = _parse_birthday_title(ev["title"])
        age = d.year - year if year is not None else None
        entries.append((d, name, age))

    entries.sort(key=lambda x: x[0])

    panel_rows = [
        {"date": _format_short_date(d), "name": n, "age": a}
        for d, n, a in entries[:BIRTHDAY_PANEL_LIMIT]
    ]
    today_events = [
        {"cat": "birthday", "title": _birthday_event_title(n, a), "time": ""}
        for d, n, a in entries if d == today_d
    ]
    tomorrow_events = [
        {"cat": "birthday", "title": _birthday_event_title(n, a), "time": ""}
        for d, n, a in entries if d == tomorrow_d
    ]
    return panel_rows, today_events, tomorrow_events


def _fmt_temp(value) -> str:
    """Round to a whole-degree string like '21°', or '–' when unparseable."""
    try:
        return f"{round(float(value))}°"
    except (TypeError, ValueError):
        return "–"


def _fmt_wind(value) -> str:
    """Tomorrow.io reports km/h for metric; render 'wind 6 km/u' or '' if absent."""
    try:
        return f"wind {round(float(value))} km/u"
    except (TypeError, ValueError):
        return ""


def _fmt_rain(forecast: dict) -> str | None:
    """Chance-of-rain as '30%', or None when the forecast omits it."""
    try:
        return f"{round(float(forecast.get('precipitation_probability')))}%"
    except (TypeError, ValueError):
        return None


def _condition_nl(condition: str) -> str:
    return WEATHER_CONDITIONS_NL.get(condition, condition.capitalize() or "–")


# Shown only on a cold start that coincides with an outage (no cache yet).
_PLACEHOLDER_WEATHER: tuple[dict, dict] = (
    {"icon": "", "temp_high": "–", "temp_low": "–", "condition": "–", "wind": "", "rain": None},
    {"icon": "", "temp_high": "–", "rain": None},
)
# Most recent fully-good read, kept in memory so transient Tomorrow.io outages
# don't blank the panel. Lost on add-on restart (refilled by the next good read).
_last_weather: tuple[dict, dict] | None = None


async def _gather_weather() -> tuple[dict, dict]:
    """Returns (header_weather, tomorrow_weather).

    Current condition + wind come from the entity state/attributes; today's and
    tomorrow's high/low and rain chance come from the daily forecast. Tomorrow.io's
    free tier intermittently 500s upstream, which flips the entity to 'unavailable'
    and makes get_forecasts error; on any such failure we reuse the last good read
    rather than render a partial/blank panel.
    """
    global _last_weather
    try:
        state, attrs = await get_entity(WEATHER_ENTITY)
        forecast = await get_forecasts(WEATHER_ENTITY, "daily")
    except HAClientError as e:
        fallback = "last-good cache" if _last_weather else "placeholders"
        log.warning("weather fetch failed (%s); using %s", e, fallback)
        return _last_weather or _PLACEHOLDER_WEATHER

    today_fc = forecast[0] if len(forecast) >= 1 else {}
    tomorrow_fc = forecast[1] if len(forecast) >= 2 else {}

    today_cond = state or today_fc.get("condition") or ""
    tomorrow_cond = tomorrow_fc.get("condition") or ""

    header_weather = {
        "icon": WEATHER_GLYPHS.get(today_cond, "•"),
        "temp_high": _fmt_temp(today_fc.get("temperature")),
        "temp_low": _fmt_temp(today_fc.get("templow")),
        "condition": _condition_nl(today_cond),
        "wind": _fmt_wind(attrs.get("wind_speed")),
        "rain": _fmt_rain(today_fc),
    }
    tomorrow_weather = {
        "icon": WEATHER_GLYPHS.get(tomorrow_cond, "•"),
        "temp_high": _fmt_temp(tomorrow_fc.get("temperature")),
        "rain": _fmt_rain(tomorrow_fc),
    }
    _last_weather = (header_weather, tomorrow_weather)
    return _last_weather


async def _gather_battery() -> int | None:
    """Panel battery level as a whole percentage, or None if unavailable."""
    try:
        state = await get_state(BATTERY_ENTITY)
    except HAClientError as e:
        log.warning("battery fetch failed: %s", e)
        return None
    try:
        return round(float(state))
    except (TypeError, ValueError):
        return None


async def gather_state() -> dict:
    try:
        fact = await get_state(FACT_ENTITY)
    except HAClientError as e:
        log.warning("fact fetch failed: %s", e)
        fact = FACT_ERROR

    now = datetime.now().astimezone()
    tomorrow = now + timedelta(days=1)
    waste_rows, waste_today_events = await _gather_waste(now.date())
    cal_today, cal_tomorrow, week_rows = await _gather_calendar(now)
    birthday_rows, bday_today, bday_tomorrow = await _gather_birthdays(now)
    header_weather, tomorrow_weather = await _gather_weather()
    battery = await _gather_battery()

    today_events = bday_today + waste_today_events + cal_today
    tomorrow_events = bday_tomorrow + cal_tomorrow
    # Empty VANDAAG/MORGEN still cost 1 line each via the "geen afspraken" placeholder.
    week_slack = max(
        0,
        AGENDA_ROW_CAP - max(1, len(today_events)) - max(1, len(tomorrow_events)),
    )
    week_rows = week_rows[:week_slack] if week_slack > 0 else None

    return {
        "header": {
            "weekday": WEEKDAYS_NL[now.weekday()],
            "date": f"{now.day} {MONTHS_NL[now.month - 1]} {now.year}",
            "weather": header_weather,
        },
        "today_events": today_events,
        "tomorrow": {
            "weekday_short": WEEKDAYS_SHORT_NL[tomorrow.weekday()],
            "date_short": f"{tomorrow.day} {MONTHS_SHORT_NL[tomorrow.month - 1]}",
            "weather_icon": tomorrow_weather["icon"],
            "temp_high": tomorrow_weather["temp_high"],
            "rain": tomorrow_weather["rain"],
            "events": tomorrow_events,
        },
        "week_rows": week_rows,
        "recycling": waste_rows,
        "birthdays": birthday_rows,
        "fact": fact,
        "refreshed": now.strftime("%H%M"),
        "battery": battery,
    }
