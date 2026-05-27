"""gather_state() collects the live dashboard payload from HA.

Live so far: wist-je-dat fact, afval (cyclus_* + cleanprofs_gft), and the
agenda (calendar.* entities). Weather and birthdays are still hardcoded.

Event categories used by the template:
  - calendar   ◆  (regular agenda items — calendar.home_assistant)
  - school     ✎  (calendar.parro_agenda)
  - holiday    ★  (calendar.holidays_in_netherlands)
  - waste      ♻  (today's pickup, surfaced in VANDAAG)

The Afval panel shows the rolling 4 nearest pickups regardless of whether
one falls today. Multi-day calendar events are repeated per day they span.
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta

from ha_client import HAClientError, calendar_events, get_entity, get_state

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
WEEK_ROW_LIMIT = 5
CALENDAR_WINDOW_DAYS = 8  # enough to cover today + tomorrow + next-7-day panel


def _parse_sort_date(value) -> date | None:
    """Parse afvalwijzer's YYYYMMDD Sort_date (int or str)."""
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

    rows = [{"date": _format_waste_date(d), "type": label} for d, label in items]
    today_events = [
        {"cat": "waste", "title": label, "time": None}
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

    return today_events, tomorrow_events, week_rows[:WEEK_ROW_LIMIT]


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

    return {
        "header": {
            "weekday": WEEKDAYS_NL[now.weekday()],
            "date": f"{now.day} {MONTHS_NL[now.month - 1]} {now.year}",
            "weather": {
                "icon": "⛅",
                "temp_high": 21,
                "temp_low": 11,
                "condition": "Half bewolkt",
                "wind": "wind 12 km/u",
            },
        },
        "today_events": waste_today_events + cal_today,
        "tomorrow": {
            "weekday_short": WEEKDAYS_SHORT_NL[tomorrow.weekday()],
            "date_short": f"{tomorrow.day} {MONTHS_SHORT_NL[tomorrow.month - 1]}",
            "weather_icon": "⛅",
            "temp_high": "20°",
            "events": cal_tomorrow,
        },
        "week_rows": week_rows,
        "recycling": waste_rows,
        "birthdays": [
            {"date": "Di 2 jun",  "name": "Emma",   "age": 8},
            {"date": "Vr 12 jun", "name": "Jan",    "age": 40},
            {"date": "Za 22 aug", "name": "Sophie", "age": None},
            {"date": "Wo 4 sep",  "name": "Oma",    "age": None},
        ],
        "fact": fact,
    }
