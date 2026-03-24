from typing import Any, List
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import json, urllib.request, time, socket
from app.db import set_reminder_set, get_reminder_set
import dateparser

#  UTC providers
_UTC_SOURCES = [
    ("https://worldtimeapi.org/api/timezone/Etc/UTC", "datetime"),
    ("https://timeapi.io/api/Time/current/zone?timeZone=UTC", "dateTime"),
    ("http://worldclockapi.com/api/json/utc/now", "currentDateTime"),
]

#  Helper: fetch UTC from the HTTP providers
def _fetch_utc_http(retries: int = 3, delay: float = 1.5) -> datetime | None:
    last_err = None
    for attempt in range(1, retries + 1):
        for url, field in _UTC_SOURCES:
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    payload = json.loads(resp.read().decode())
                    iso = payload.get(field)
                    if not iso:
                        raise RuntimeError(f"Missing field {field!r} in response from {url}")
                    if iso[-6:] not in ("+00:00", "-00:00"):
                        iso += "+00:00"
                    return datetime.fromisoformat(iso)
            except Exception as exc:
                last_err = exc
                continue 
        if attempt < retries:
            time.sleep(delay * attempt)
    print(f"[debug] HTTP UTC fetch failed after {retries} tries: {last_err}")
    return None

#  Helper: fetch UTC from an NTP server 
def _fetch_utc_ntp(host: str = "pool.ntp.org", timeout: int = 5) -> datetime | None:

    msg = b'\x1b' + 47 * b'\0'
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(msg, (host, 123))
            data, _ = s.recvfrom(48)
        if len(data) < 48:
            return None
        import struct
        _, = struct.unpack("!I", data[40:44])
        ntp_time = _.to_bytes(4, 'big')
        ts = struct.unpack("!I", ntp_time)[0] - 2208988800
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None

#  Core: get a trustworthy UTC anchor
def _get_trusted_utc() -> datetime:

    utc_now = _fetch_utc_http()
    if utc_now:
        return utc_now

    utc_now = _fetch_utc_ntp()
    if utc_now:
        return utc_now

    return datetime.now(timezone.utc) 

#  Geocoder & timezone finder
geolocator = Nominatim(user_agent="sega_ai")
tf = TimezoneFinder()

#  Public function – same signature you already use
def time_date(expr: str | None) -> datetime:

    utc_now = _get_trusted_utc()

    if not expr or not expr.strip():
        return utc_now

    expr = expr.strip()

    try:
        target = ZoneInfo(expr)
        return utc_now.astimezone(target)
    except ZoneInfoNotFoundError:
        pass
    except Exception:
        pass

    try:
        loc = geolocator.geocode(expr)
        if loc:
            tz_name = tf.timezone_at(lng=loc.longitude, lat=loc.latitude)
            if tz_name:
                target = ZoneInfo(tz_name)
                return utc_now.astimezone(target)
    except Exception:
        pass

    return utc_now

async def set_reminder(reminder_details: dict):
    await set_reminder_set(reminder_details)

async def get_reminder(raw_expr: str):
    raw_expr = raw_expr.lower().strip()

    start_date = None
    end_date = None

    settings = {
        'TIMEZONE': 'UTC',
        'RETURN_AS_TIMEZONE_AWARE': True,
        'PREFER_DATES_FROM': 'future',
    }

    if " to " in raw_expr:
        start_str, end_str = map(str.strip, raw_expr.split(" to ", 1))

        start_dt = dateparser.parse(start_str, settings=settings)
        end_dt = dateparser.parse(end_str, settings=settings)

        if not start_dt or not end_dt:
            return "Could not parse date range."

        start_date = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_date = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    else:
        dt = dateparser.parse(raw_expr, settings=settings)

        if not dt:
            return "Could not parse date."

        if raw_expr in ("today", "tomorrow"):
            start_of_day = dt.replace(hour=0, minute=0, second=0)
            end_of_day = dt.replace(hour=23, minute=59, second=59)

            start_date = start_of_day.strftime("%Y-%m-%d %H:%M:%S")
            end_date = end_of_day.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            end_date = start_date

    print(start_date)
    print(end_date)

    reminder_set = await get_reminder_set(start_date, end_date)
    print(reminder_set)

    return reminder_set



async def _clock_and_calendar(raw_expr: str, reminder_details: dict, mode: str = "auto") -> str:
    results: List[Any] = []
    try:
        if mode.lower() == "time_date":
            results.append(time_date(raw_expr))
        if mode.lower() == "set_reminder":
            results.append(await set_reminder(reminder_details))
        if mode.lower() == "get_schedule":
            results.append(await get_reminder(raw_expr))
        if not results:
            return "No computable expression found."
        return str(tuple(results))
    except Exception as exc:
        return f"Cannot find! reason: {exc} for expression: {raw_expr}"


def run(expression: str, mode: str = "auto") -> str:
    return _clock_and_calendar(expression, mode)