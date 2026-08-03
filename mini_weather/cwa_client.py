"""Thin client for Taiwan CWA (Opendata) township weather forecasts.

API reference: https://opendata.cwa.gov.tw/
Location naming follows CWA Opendata City lists (same source OpenCWB uses).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CWA_BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# CWA Wx codes → mini_weather icon stems (files under icons/).
# Codes follow CWA 天氣現象數字代碼 (1–42).
_CWA_WX_ICON = {
    1: "01d",  # 晴
    2: "022d",  # 晴時多雲
    3: "02d",  # 多雲時晴
    4: "02d",  # 多雲
    5: "03d",  # 多雲時陰
    6: "03d",  # 陰時多雲
    7: "04d",  # 陰
    8: "51d",  # 多雲陣雨
    9: "51d",
    10: "53d",
    11: "09d",
    12: "09d",
    13: "09d",
    14: "09d",
    15: "11d",  # 晴午後雷陣雨
    16: "11d",
    17: "11d",
    18: "11d",
    19: "10d",
    20: "10d",
    21: "10d",
    22: "09d",
    23: "13d",  # 雨雪
    24: "50d",  # 霧
    25: "50d",
    26: "50d",
    27: "50d",
    28: "50d",
    29: "10d",
    30: "09d",
    31: "09d",
    32: "50d",
    33: "50d",
    34: "50d",
    35: "50d",
    36: "50d",
    37: "13d",
    38: "50d",
    39: "50d",
    41: "50d",
    42: "13d",  # 冰雹
}


def weekly_dataset_id(base_dataset: str) -> str:
    """Township 3-day dataset id → weekly forecast id (CWA convention: +2)."""
    match = re.fullmatch(r"(F-D0047-)(\d{3})", (base_dataset or "").strip())
    if not match:
        raise RuntimeError(f"Unsupported CWA dataset id: {base_dataset!r}")
    return f"{match.group(1)}{int(match.group(2)) + 2:03d}"


def convert_temp_c(temp_c: float | int | None, units: str) -> int | None:
    if temp_c is None:
        return None
    value = float(temp_c)
    if units == "imperial":
        return int(round(value * 9.0 / 5.0 + 32.0))
    if units == "standard":
        return int(round(value + 273.15))
    return int(round(value))


def map_cwa_wx_to_icon(wx_code: int | None) -> str:
    if wx_code is None:
        return "01d"
    return _CWA_WX_ICON.get(int(wx_code), "03d")


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "–"}:
        return None
    # Wind-like fields may be "≤1" etc.; keep only digits/sign/dot.
    cleaned = re.sub(r"[^\d.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return int(round(float(cleaned)))
    except ValueError:
        return None


def _parse_start_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            if fmt.endswith("%z") and re.search(r"[+-]\d{2}:\d{2}$", text):
                # Python %z does not accept colon in offset on older versions;
                # normalize +08:00 → +0800.
                text_norm = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", text)
                dt = datetime.strptime(text_norm, "%Y-%m-%dT%H:%M:%S%z")
                return dt.astimezone(TAIPEI_TZ)
            if "T" not in text:
                dt = datetime.strptime(text, fmt)
                return dt.replace(tzinfo=TAIPEI_TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt.astimezone(TAIPEI_TZ)
    except ValueError:
        return None


def _element_times(element: dict) -> list[dict]:
    return element.get("Time") or element.get("time") or []


def _element_name(element: dict) -> str:
    return str(element.get("ElementName") or element.get("elementName") or "").strip()


def _element_values(time_entry: dict) -> list[dict]:
    values = time_entry.get("ElementValue") or time_entry.get("elementValue") or []
    if isinstance(values, dict):
        return [values]
    return list(values) if values else []


def _start_time_of(time_entry: dict) -> str | None:
    return time_entry.get("StartTime") or time_entry.get("startTime")


def _first_value_dict(time_entry: dict) -> dict:
    values = _element_values(time_entry)
    if not values:
        return {}
    first = values[0]
    return first if isinstance(first, dict) else {}


def _dict_first_scalar(d: dict) -> Any:
    if not d:
        return None
    # Prefer known keys used by CWA JSON.
    for key in (
        "Temperature",
        "MaxTemperature",
        "MinTemperature",
        "Weather",
        "WeatherCode",
        "value",
        "Value",
        "ElementValue",
    ):
        if key in d and d[key] not in (None, ""):
            return d[key]
    # Fall back to first non-empty value.
    for value in d.values():
        if value not in (None, ""):
            return value
    return None


def _extract_wx(time_entry: dict) -> tuple[int | None, str]:
    values = _element_values(time_entry)
    if not values:
        return None, ""

    # Modern CWA: [{"Weather": "多雲", "WeatherCode": "04"}]
    first = values[0] if isinstance(values[0], dict) else {}
    weather_text = str(first.get("Weather") or first.get("value") or _dict_first_scalar(first) or "").strip()
    code_raw = first.get("WeatherCode")
    if code_raw is None and len(values) > 1 and isinstance(values[1], dict):
        code_raw = values[1].get("value") or _dict_first_scalar(values[1])
    if code_raw is None:
        # Sometimes both sit in one object as ordered values.
        vals = list(first.values())
        if len(vals) >= 2 and str(vals[1]).isdigit():
            code_raw = vals[1]
            if not weather_text:
                weather_text = str(vals[0])
    code = _safe_int(code_raw)
    return code, weather_text


def _extract_temp(time_entry: dict) -> int | None:
    first = _first_value_dict(time_entry)
    return _safe_int(_dict_first_scalar(first))


def _pick_location_record(payload: dict, location_name: str) -> dict:
    records = payload.get("records") or payload.get("Records") or {}
    # New schema: records.Locations[].Location[]
    locations_blocks = records.get("Locations") or records.get("locations") or []
    candidates: list[dict] = []
    for block in locations_blocks:
        for loc in block.get("Location") or block.get("location") or []:
            candidates.append(loc)

    # Older schema: records.location[]
    if not candidates:
        for loc in records.get("location") or records.get("Location") or []:
            candidates.append(loc)

    if not candidates:
        raise RuntimeError("CWA response contained no location records.")

    wanted = (location_name or "").strip()
    # Also try common 台/臺 variant and unprefixed township names.
    variants = {wanted, wanted.replace("台", "臺"), wanted.replace("臺", "台")}
    for v in list(variants):
        for city_suffix in ("縣", "市"):
            # "臺北市大安區" → also match "大安區"
            if city_suffix in v:
                # drop leading city token once (…市/…縣)
                parts = re.split(r".*?[縣市]", v, maxsplit=1)
                if len(parts) == 2 and parts[1]:
                    variants.add(parts[1])
    for loc in candidates:
        name = str(loc.get("LocationName") or loc.get("locationName") or "").strip()
        name_variants = {name, name.replace("台", "臺"), name.replace("臺", "台")}
        if name_variants & variants:
            return loc
        # Accept either side being a suffix of the other (city-prefixed vs plain).
        if any(
            (n and w and (n.endswith(w) or w.endswith(n)))
            for n in name_variants
            for w in variants
        ):
            return loc

    # If the API already filtered by locationName and returned exactly one row,
    # accept it only when the caller did not ask for a specific name, or the
    # returned name is blank (some feeds omit LocationName after filtering).
    if len(candidates) == 1:
        only = candidates[0]
        only_name = str(only.get("LocationName") or only.get("locationName") or "").strip()
        if not wanted or not only_name:
            return only

    names = [
        str(loc.get("LocationName") or loc.get("locationName") or "")
        for loc in candidates[:8]
    ]
    raise RuntimeError(
        f"CWA location {location_name!r} not found in response "
        f"(sample names: {names})."
    )


def _periods_from_location(location: dict) -> list[dict[str, Any]]:
    """Flatten WeatherElement time series into per-startTime period dicts."""
    elements = location.get("WeatherElement") or location.get("weatherElement") or []
    by_start: dict[str, dict[str, Any]] = {}

    for element in elements:
        name = _element_name(element)
        if not name:
            continue
        for time_entry in _element_times(element):
            start_raw = _start_time_of(time_entry)
            if not start_raw:
                continue
            period = by_start.setdefault(start_raw, {"start": start_raw})
            if name in {"Wx", "天氣現象"}:
                code, text = _extract_wx(time_entry)
                period["wx_code"] = code
                period["wx_text"] = text
            elif name in {"T", "溫度", "平均溫度"}:
                period["temp"] = _extract_temp(time_entry)
            elif name in {"MaxT", "最高溫度"}:
                period["max_t"] = _extract_temp(time_entry)
            elif name in {"MinT", "最低溫度"}:
                period["min_t"] = _extract_temp(time_entry)
            elif name in {"MaxAT", "最高體感溫度"}:
                period["max_at"] = _extract_temp(time_entry)
            elif name in {"MinAT", "最低體感溫度"}:
                period["min_at"] = _extract_temp(time_entry)
            elif name in {"AT", "體感溫度"}:
                period["at"] = _extract_temp(time_entry)

    periods = list(by_start.values())
    periods.sort(key=lambda p: p["start"])
    return periods


def _aggregate_daily(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge 12h (or other) periods into calendar days in Asia/Taipei."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for period in periods:
        start_dt = _parse_start_time(period.get("start"))
        if not start_dt:
            continue
        period = {**period, "start_dt": start_dt}
        buckets[start_dt.date().isoformat()].append(period)

    days: list[dict[str, Any]] = []
    for day_key in sorted(buckets.keys()):
        day_periods = buckets[day_key]
        highs: list[int] = []
        lows: list[int] = []
        temps: list[int] = []
        for p in day_periods:
            if p.get("max_t") is not None:
                highs.append(p["max_t"])
            if p.get("min_t") is not None:
                lows.append(p["min_t"])
            if p.get("temp") is not None:
                temps.append(p["temp"])
                highs.append(p["temp"])
                lows.append(p["temp"])

        # Prefer daytime Wx (start hour < 18).
        daytime = [p for p in day_periods if p["start_dt"].hour < 18]
        wx_source = daytime[0] if daytime else day_periods[0]

        if not highs and temps:
            highs = temps
        if not lows and temps:
            lows = temps
        if not highs or not lows:
            # Skip incomplete days rather than showing garbage.
            continue

        days.append(
            {
                "date": day_key,
                "start_dt": day_periods[0]["start_dt"],
                "high_c": max(highs),
                "low_c": min(lows),
                "temp_c": temps[0] if temps else int(round((max(highs) + min(lows)) / 2)),
                "wx_code": wx_source.get("wx_code"),
                "wx_text": wx_source.get("wx_text") or "",
                "feels_c": wx_source.get("at")
                or wx_source.get("max_at")
                or wx_source.get("min_at"),
            }
        )
    return days


def fetch_cwa_weekly_forecast(
    api_key: str,
    base_dataset: str,
    location_name: str,
    timeout: int = 30,
) -> dict:
    """Fetch CWA weekly township forecast JSON for one location."""
    import requests

    if not api_key or not str(api_key).strip():
        raise RuntimeError("CWA API Key not configured.")
    if not location_name or not str(location_name).strip():
        raise RuntimeError("CWA location name is required.")

    dataset = weekly_dataset_id(base_dataset)
    # Prefer 臺 form; CWA data uses 臺 extensively.
    location = str(location_name).strip().replace("台", "臺")
    url = f"{CWA_BASE_URL}/{dataset}"
    params = {
        "Authorization": api_key.strip(),
        "format": "JSON",
        "LocationName": location,
        "locationName": location,
    }

    logger.info("CWA request dataset=%s location=%s", dataset, location)
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"CWA request network error: {exc}") from exc

    if response.status_code == 401:
        raise RuntimeError("CWA API key rejected (HTTP 401).")
    if response.status_code == 204:
        raise RuntimeError("CWA returned no content for this location.")
    if not 200 <= response.status_code < 300:
        snippet = (response.text or "")[:200]
        raise RuntimeError(f"CWA request failed: status={response.status_code} body={snippet!r}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("CWA response is not valid JSON.") from exc

    # CWA sometimes returns HTTP 200 with success=false.
    if isinstance(payload, dict) and payload.get("success") is False:
        message = payload.get("message") or payload.get("result") or payload
        raise RuntimeError(f"CWA API error: {message}")

    return payload


def parse_cwa_days(payload: dict, location_name: str) -> list[dict[str, Any]]:
    location = _pick_location_record(payload, location_name)
    periods = _periods_from_location(location)
    if not periods:
        raise RuntimeError("CWA response had no forecast periods.")
    days = _aggregate_daily(periods)
    if not days:
        raise RuntimeError("CWA forecast periods could not be aggregated into daily data.")
    return days


def build_template_params_from_cwa_days(
    days: list[dict[str, Any]],
    units: str,
    time_format: str,
    icon_path_fn,
    day_label_fn=None,
) -> dict:
    """Convert aggregated CWA days into Weather-plugin-compatible template params.

    icon_path_fn(icon_stem) -> absolute/plugin path string
    day_label_fn(datetime) -> optional localized weekday label
    """
    if not days:
        raise RuntimeError("No CWA daily forecast available.")

    today = days[0]
    current_icon = map_cwa_wx_to_icon(today.get("wx_code"))
    current_temp = convert_temp_c(today.get("temp_c"), units)
    feels = convert_temp_c(today.get("feels_c") if today.get("feels_c") is not None else today.get("temp_c"), units)

    forecast = []
    for day in days:
        high = convert_temp_c(day.get("high_c"), units)
        low = convert_temp_c(day.get("low_c"), units)
        if high is None or low is None:
            continue
        start_dt = day.get("start_dt")
        if day_label_fn and start_dt is not None:
            day_label = day_label_fn(start_dt)
        elif start_dt is not None:
            day_label = start_dt.strftime("%a")
        else:
            day_label = day.get("date", "")
        icon_stem = map_cwa_wx_to_icon(day.get("wx_code"))
        forecast.append(
            {
                "day": day_label,
                "high": high,
                "low": low,
                "icon": icon_path_fn(icon_stem),
                "weekday_index": start_dt.weekday() if start_dt is not None else None,
            }
        )

    if not forecast:
        raise RuntimeError("CWA daily forecast empty after unit conversion.")

    return {
        "current_date": today.get("date", ""),
        "current_day_icon": icon_path_fn(current_icon),
        "current_temperature": str(current_temp) if current_temp is not None else "--",
        "feels_like": str(feels) if feels is not None else "--",
        "weather_description": today.get("wx_text") or "",
        "temperature_unit": "°C" if units == "metric" else ("°F" if units == "imperial" else "K"),
        "units": units,
        "time_format": time_format,
        "forecast": forecast,
        "data_points": [],
        "hourly_forecast": [],
        "alerts": [],
    }


def _location_name_candidates(location_name: str) -> list[str]:
    """Generate CWA LocationName variants (台/臺, with/without city prefix)."""
    raw = (location_name or "").strip()
    if not raw:
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = (name or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        variants.append(name)

    for base in (raw, raw.replace("台", "臺"), raw.replace("臺", "台")):
        add(base)
        # Strip one leading city/county token: 臺北市大安區 → 大安區
        stripped = re.sub(r"^.*?[縣市]", "", base, count=1)
        add(stripped)
    return variants


def fetch_and_build_template_params(
    api_key: str,
    base_dataset: str,
    location_name: str,
    units: str,
    time_format: str,
    icon_path_fn,
    day_label_fn=None,
) -> dict:
    last_error: Exception | None = None
    for candidate in _location_name_candidates(location_name):
        try:
            payload = fetch_cwa_weekly_forecast(api_key, base_dataset, candidate)
            days = parse_cwa_days(payload, candidate)
            return build_template_params_from_cwa_days(
                days,
                units=units,
                time_format=time_format,
                icon_path_fn=icon_path_fn,
                day_label_fn=day_label_fn,
            )
        except Exception as exc:  # try next name variant
            last_error = exc
            logger.warning("CWA fetch/parse failed for %r: %s", candidate, exc)
            continue
    if last_error:
        raise RuntimeError(str(last_error)) from last_error
    raise RuntimeError("CWA location name is required.")
