import logging
import re
import unicodedata
from pathlib import Path

import pytz
import requests
import datetime

from plugins.weather.weather import UNITS, Weather

try:
    # Package-relative import when loaded as plugins.mini_weather.mini_weather
    from .cwa_client import fetch_and_build_template_params
except ImportError:
    # Fallback for flat plugin layout used by some installers
    from cwa_client import fetch_and_build_template_params  # type: ignore

logger = logging.getLogger(__name__)

REVERSE_GEOCODE_URL = (
    "https://nominatim.openstreetmap.org/reverse"
    "?lat={lat}&lon={long}&format=jsonv2&addressdetails=1&zoom=10"
)

# Simple in-memory cache for reverse-geocoded titles to avoid hitting Nominatim
# on every refresh. Keys are rounded coordinate pairs to tolerate tiny changes.
REVERSE_GEOCODE_CACHE = {}
# TTL for successful reverse geocode results (seconds)
REVERSE_GEOCODE_SUCCESS_TTL = 7 * 24 * 60 * 60  # 7 days
# TTL for failed attempts (seconds) to avoid tight retry loops
REVERSE_GEOCODE_FAIL_TTL = 60 * 60  # 1 hour
REVERSE_GEOCODE_ROUND_DECIMALS = 4

QUICK_LOCATION_LABELS = {
    "52.3676,4.9041": "Amsterdam",
    "52.5200,13.4050": "Berlin",
    "-34.6037,-58.3816": "Buenos Aires",
    "-6.2088,106.8456": "Jakarta",
    "51.5074,-0.1278": "London",
    "40.4168,-3.7038": "Madrid",
    "40.7128,-74.0060": "New York",
    "48.8566,2.3522": "Paris",
    "-22.9068,-43.1729": "Rio de Janeiro",
    "41.9028,12.4964": "Rome",
    "-23.5505,-46.6333": "São Paulo",
    "25.0330,121.5654": "Taipei",
    "24.9937,121.3009": "Taoyuan",
    "24.1477,120.6736": "Taichung",
    "22.9999,120.2270": "Tainan",
    "22.6273,120.3014": "Kaohsiung",
    "35.6762,139.6503": "Tokyo",
}

QUICK_LOCATION_COORDS = {
    city: tuple(map(float, coords.split(",")))
    for coords, city in QUICK_LOCATION_LABELS.items()
}

LANGUAGE_LABELS = {
    "de": {
        "now": "JETZT",
        "days": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "header_days": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "updated_at": "Aktualisiert {time}",
        "feels_like": "Gefühlt {temp}{unit}",
        "rain": "Regen {pct}%",
    },
    "en": {
        "now": "NOW",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "header_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "updated_at": "Updated {time}",
        "feels_like": "Feels {temp}{unit}",
        "rain": "Rain {pct}%",
    },
    "es": {
        "now": "AHORA",
        "days": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
        "header_days": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        "updated_at": "Actualizado {time}",
        "feels_like": "Sensación {temp}{unit}",
        "rain": "Lluvia {pct}%",
    },
    "fr": {
        "now": "MAINT",
        "days": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
        "header_days": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "updated_at": "Mis à jour {time}",
        "feels_like": "Ressenti {temp}{unit}",
        "rain": "Pluie {pct}%",
    },
    "id": {
        "now": "SEK",
        "days": ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"],
        "header_days": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"],
        "updated_at": "Diperbarui {time}",
        "feels_like": "Terasa {temp}{unit}",
        "rain": "Hujan {pct}%",
    },
    "it": {
        "now": "ORA",
        "days": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
        "header_days": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"],
        "updated_at": "Aggiornato {time}",
        "feels_like": "Percepita {temp}{unit}",
        "rain": "Pioggia {pct}%",
    },
    "nl": {
        "now": "NU",
        "days": ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"],
        "header_days": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
        "updated_at": "Bijgewerkt {time}",
        "feels_like": "Voelt als {temp}{unit}",
        "rain": "Regen {pct}%",
    },
    "pt": {
        "now": "AGORA",
        "days": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
        "header_days": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"],
        "updated_at": "Atualizado {time}",
        "feels_like": "Sensação {temp}{unit}",
        "rain": "Chuva {pct}%",
    },
    "zh-tw": {
        "now": "現在",
        "days": ["週一", "週二", "週三", "週四", "週五", "週六", "週日"],
        "header_days": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
        "updated_at": "{time} 更新",
        "feels_like": "體感 {temp}{unit}",
        "rain": "降雨 {pct}%",
    },
}

# month names for a handful of supported languages; keep capitalized first letter
MONTH_NAMES = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "pt": [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ],
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "it": [
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ],
    "nl": [
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ],
    "id": [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ],
    "zh-tw": [
        "1月",
        "2月",
        "3月",
        "4月",
        "5月",
        "6月",
        "7月",
        "8月",
        "9月",
        "10月",
        "11月",
        "12月",
    ],
}


def normalize_language_key(language):
    lang = (language or "").strip().lower().replace("_", "-")
    if lang in ("zh", "zh-tw", "zh-hant", "zh-hant-tw", "zh-tw-hant"):
        return "zh-tw"
    return lang.split("-")[0]


def format_localized_date(language, dt):
    """Return a short localized date string for the given language and datetime.

    Examples:
      en -> "March 25, 2026"
      pt -> "25 de março de 2026"
      fr/de/it/nl/es/id -> "25 mars 2026"
    """
    short = normalize_language_key(language)
    months = MONTH_NAMES.get(short, MONTH_NAMES.get("en"))
    raw_month = months[dt.month - 1]

    day = dt.day
    year = dt.year

    # Capitalization rules
    # - English: capitalize month (e.g., March)
    # - French: lowercase month (e.g., mars)
    # - Other languages: use the form provided in MONTH_NAMES
    if short == "en":
        month = raw_month[0].upper() + raw_month[1:]
    elif short == "fr":
        month = raw_month.lower()
    else:
        month = raw_month

    # Formatting rules per language
    if short == "en":
        # Month Day, Year -> March 25, 2026
        return f"{month} {day}, {year}"

    if short in ("fr", "de", "it", "nl", "es", "id"):
        # Day Month Year -> 25 mars 2026 (no commas/connectors)
        return f"{day} {month} {year}"

    if short == "pt":
        # Portuguese: Day de month de Year -> 25 de março de 2026
        return f"{day} de {month} de {year}"

    if short == "zh-tw":
        # Traditional Chinese: 2026年3月25日
        return f"{year}年{month}{day}日"

    # Fallback: use English-style month-first formatting
    return f"{month} {day}, {year}"


def format_header_weekday(language, dt):
    """Full weekday name for the header date block (e.g. 星期三, Wednesday)."""
    labels = get_language_labels(language)
    days = labels.get("header_days")
    if days:
        return days[dt.weekday() % 7]
    return LANGUAGE_LABELS["en"]["header_days"][dt.weekday() % 7]


def format_updated_label(language, dt, time_format="24h"):
    """Label shown under the current temperature.

    The rendered image is static on an e-paper display, so the clock time of
    the refresh (e.g. "08:06 更新" / "Updated 08:06") stays accurate until the
    next refresh — more useful than a literal "just now".
    """
    labels = get_language_labels(language)
    short = normalize_language_key(language)
    # Traditional Chinese official style is 24-hour; otherwise honour device format.
    if short == "zh-tw" or time_format != "12h":
        time_str = dt.strftime("%H:%M")
    else:
        time_str = dt.strftime("%I:%M %p").lstrip("0")
    template = labels.get("updated_at") or LANGUAGE_LABELS["en"]["updated_at"]
    return template.replace("{time}", time_str)


def format_feels_like_label(language, value, unit_symbol="°"):
    """Localized current feels-like label, or empty if the value is missing.

    Examples: "體感 21°", "Feels 21°". Kelvin uses a leading space ("Feels 294 K").
    """
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value or text_value in {"--", "None", "N/A"}:
        return ""
    # Keep a leading minus, but require a numeric body.
    body = text_value[1:] if text_value.startswith("-") else text_value
    if not body.replace(".", "", 1).isdigit():
        return ""
    if "." in body:
        temp = text_value
    else:
        temp = str(int(text_value))
    if not unit_symbol or unit_symbol.startswith("°"):
        unit = unit_symbol or "°"
    else:
        unit = f" {unit_symbol}"
    labels = get_language_labels(language)
    template = labels.get("feels_like") or LANGUAGE_LABELS["en"]["feels_like"]
    return template.replace("{temp}", temp).replace("{unit}", unit)




def normalize_rain_probability(value):
    """Return an integer 0–100 rain probability, or None if unavailable.

    Accepts CWA-style percentages ("20", 20) and OWM-style fractions (0.2).
    A bare 0 or 0.0 is a real 0% and is kept. "-" / "--" / blanks are hidden.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text_value = value.strip().replace("%", "")
        if not text_value or text_value in {"-", "—", "–", "--", "None", "N/A"}:
            return None
        try:
            number = float(text_value)
        except ValueError:
            return None
        # String "0.2" from a fraction source is possible; "20" is a percent.
        if "." in text_value and 0 < number <= 1:
            number *= 100
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        # OpenWeatherMap daily/hourly pop is a 0–1 fraction.
        if 0 <= number <= 1 and not isinstance(value, int):
            number *= 100
    if number < 0 or number > 100:
        return None
    return int(round(number))


def format_rain_label(language, value):
    """Localized rain-probability label, or empty if the value is missing.

    Examples: "降雨 20%", "Rain 20%". A 0% chance is shown.
    """
    pct = normalize_rain_probability(value)
    if pct is None:
        return ""
    labels = get_language_labels(language)
    template = labels.get("rain") or LANGUAGE_LABELS["en"]["rain"]
    return template.replace("{pct}", str(pct))


def format_weather_description(value):
    """Today's short weather description, or empty if missing."""
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value or text_value in {"--", "-", "None", "N/A"}:
        return ""
    return text_value


# Open-Meteo uses WMO weather interpretation codes. Maps are short display
# labels for the hero description; unknown codes stay hidden.
_OPEN_METEO_WX_TEXT = {
    "en": {
        0: "Clear",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Icy fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        56: "Light freezing drizzle",
        57: "Freezing drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Freezing rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Light showers",
        81: "Showers",
        82: "Heavy showers",
        85: "Light snow showers",
        86: "Snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Thunderstorm with hail",
    },
    "zh-tw": {
        0: "晴",
        1: "晴時多雲",
        2: "多雲時晴",
        3: "陰",
        45: "霧",
        48: "霧凇",
        51: "小毛毛雨",
        53: "毛毛雨",
        55: "大毛毛雨",
        56: "輕度凍毛雨",
        57: "凍毛雨",
        61: "小雨",
        63: "雨",
        65: "大雨",
        66: "輕度凍雨",
        67: "凍雨",
        71: "小雪",
        73: "雪",
        75: "大雪",
        77: "雪粒",
        80: "小陣雨",
        81: "陣雨",
        82: "大陣雨",
        85: "小陣雪",
        86: "陣雪",
        95: "雷雨",
        96: "雷雹",
        99: "雷雹",
    },
}


def open_meteo_weather_description(weather_code, language="en"):
    if weather_code is None or weather_code == "":
        return ""
    try:
        code = int(weather_code)
    except (TypeError, ValueError):
        return ""
    short = language if language in _OPEN_METEO_WX_TEXT else "en"
    # normalize_language_key may not be needed if caller already normalized.
    try:
        short = normalize_language_key(language)
    except Exception:
        pass
    table = _OPEN_METEO_WX_TEXT.get(short) or _OPEN_METEO_WX_TEXT["en"]
    return table.get(code) or _OPEN_METEO_WX_TEXT["en"].get(code) or ""


def extract_owm_today_extras(weather_data):
    """Best-effort description and 0–100 rain probability from OWM One Call."""
    description = ""
    rain = None
    if not isinstance(weather_data, dict):
        return description, rain
    current = weather_data.get("current") or {}
    weather = current.get("weather") or []
    if weather and isinstance(weather[0], dict):
        description = format_weather_description(
            weather[0].get("description") or weather[0].get("main")
        )
    daily = weather_data.get("daily") or []
    if daily and isinstance(daily[0], dict) and "pop" in daily[0]:
        rain = normalize_rain_probability(daily[0].get("pop"))
    if rain is None:
        # Fall back to the highest remaining hourly pop today / next 24h.
        pops = []
        for hour in (weather_data.get("hourly") or [])[:24]:
            if isinstance(hour, dict) and hour.get("pop") is not None:
                pops.append(normalize_rain_probability(hour.get("pop")))
        pops = [p for p in pops if p is not None]
        if pops:
            rain = max(pops)
    return description, rain


def extract_open_meteo_today_extras(weather_data, language="en"):
    """Best-effort description and rain probability from an Open-Meteo payload."""
    description = ""
    rain = None
    if not isinstance(weather_data, dict):
        return description, rain
    current = weather_data.get("current") or {}
    description = open_meteo_weather_description(current.get("weather_code"), language)
    daily = weather_data.get("daily") or {}
    daily_pops = daily.get("precipitation_probability_max") or []
    if daily_pops and daily_pops[0] is not None:
        rain = normalize_rain_probability(daily_pops[0])
    if rain is None:
        hourly = weather_data.get("hourly") or {}
        times = hourly.get("time") or []
        probs = hourly.get("precipitation_probability") or []
        today = None
        if current.get("time"):
            today = str(current.get("time"))[:10]
        pops = []
        for i, time_str in enumerate(times):
            if i >= len(probs):
                break
            if today and not str(time_str).startswith(today):
                continue
            pct = normalize_rain_probability(probs[i])
            if pct is not None:
                pops.append(pct)
            if today is None and len(pops) >= 24:
                break
        if pops:
            rain = max(pops)
    return description, rain


def apply_best_effort_conditions(template_params, weather_data, provider, language="en"):
    """Fill weather_description / rain_probability when the parent parser omitted them."""
    if not isinstance(template_params, dict):
        return template_params
    if provider == "OpenWeatherMap":
        description, rain = extract_owm_today_extras(weather_data)
    elif provider == "OpenMeteo":
        description, rain = extract_open_meteo_today_extras(weather_data, language)
    else:
        return template_params
    if not template_params.get("weather_description") and description:
        template_params["weather_description"] = description
    if template_params.get("rain_probability") is None and rain is not None:
        template_params["rain_probability"] = rain
    return template_params


def resolve_display_icon(icon_path, color_icons=False):
    """Swap a colour PNG for the outline + halftone SVG when colour icons are off."""
    if color_icons or not icon_path:
        return icon_path

    path = Path(str(icon_path))
    outline = path.parent / "outline" / f"{path.stem}.svg"
    if outline.is_file():
        return str(outline)
    return icon_path




def get_language_labels(language):
    lang = (language or "").strip().lower().replace("_", "-")
    # exact key
    if lang in LANGUAGE_LABELS:
        return LANGUAGE_LABELS[lang]
    # try prefix like en-US -> en
    short = normalize_language_key(language)
    if short in LANGUAGE_LABELS:
        return LANGUAGE_LABELS[short]
    # fallback to English
    return LANGUAGE_LABELS["en"]


def get_accept_language_header(language):
    normalized = normalize_language_key(language)
    if normalized == "zh-tw":
        return "zh-TW,zh-Hant;q=0.9,zh;q=0.8,en;q=0.5"
    if normalized in LANGUAGE_LABELS:
        return f"{normalized};q=1.0,en;q=0.5"
    return "en;q=1.0"


def is_valid_title(value):
    if value is None:
        return False

    title = str(value).strip()
    if len(title) < 2:
        return False

    # Require at least one letter/number to avoid titles like "," or "'".
    return bool(re.search(r"\w", title, flags=re.UNICODE))


def is_supported_title(value):
    if not is_valid_title(value):
        return False

    title = str(value).strip()
    has_letter = False

    for char in title:
        if not char.isalpha():
            continue

        has_letter = True
        char_name = unicodedata.name(char, "")
        if "LATIN" not in char_name and "CJK" not in char_name and "BOPOMOFO" not in char_name:
            return False

    return has_letter


class MiniWeather(Weather):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        # Required for OpenWeatherMap and CWA; Open-Meteo needs none (UI hides the badge).
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap / CWA",
            "expected_key": "OPEN_WEATHER_MAP_SECRET or CWA_API_KEY"
        }
        return template_params
    def generate_image(self, settings, device_config):
        units = settings.get("units")
        if units not in UNITS:
            raise RuntimeError("Units are required.")

        language = str(settings.get("language", "en")).strip() or "en"
        weather_provider = settings.get("weatherProvider", "OpenMeteo")
        timezone_name = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        local_tz = pytz.timezone(timezone_name)

        lat = None
        long = None
        if weather_provider == "CWA":
            cwa_location = (settings.get("cwaLocation") or settings.get("cwaDistrict") or "").strip()
            cwa_city = (settings.get("cwaCity") or "").strip()
            if not cwa_location or not cwa_city:
                raise RuntimeError("CWA city and district are required.")
            # CWA is Taiwan-only; coordinates are unused for the forecast request.
            lat = 23.9739
            long = 120.9820
        else:
            lat_value = settings.get("latitude")
            long_value = settings.get("longitude")
            if lat_value in (None, "") or long_value in (None, ""):
                raise RuntimeError("Latitude and Longitude are required.")

            # Validate and parse numeric coordinates with clear error messages.
            try:
                lat = float(str(lat_value).strip())
                long = float(str(long_value).strip())
            except (ValueError, TypeError):
                raise RuntimeError("Latitude and Longitude must be valid numeric values.")

            # Range checks: latitude [-90, 90], longitude [-180, 180]
            if not (-90.0 <= lat <= 90.0):
                raise RuntimeError("Latitude must be between -90 and 90.")
            if not (-180.0 <= long <= 180.0):
                raise RuntimeError("Longitude must be between -180 and 180.")

        try:
            template_params, provider_tz, api_key = self._get_template_params(
                weather_provider,
                settings,
                units,
                lat,
                long,
                local_tz,
                time_format,
                device_config,
                language,
            )
        except Exception as exc:
            logger.error("%s request failed: %s", weather_provider, exc)
            raise RuntimeError(f"{weather_provider} request failure, please check logs.") from exc

        title = self._resolve_title_with_fallback(settings, weather_provider, lat, long, api_key, language)

        forecast = template_params.get("forecast", [])
        if not forecast:
            raise RuntimeError("Forecast data unavailable.")

        current_day = forecast[0]
        forecast_days = max(1, min(4, int(settings.get("forecastDays", 4))))
        forecast_rows = forecast[1:1 + forecast_days] if len(forecast) > 1 else forecast[:forecast_days]
        labels = get_language_labels(language)

        # localized date string
        # Use the provider timezone that was returned from _get_template_params.
        # This matches the timezone used to parse the forecast and respects the
        # user's `weatherTimeZone` selection (locationTimeZone vs device timezone).
        now = datetime.datetime.now(provider_tz)
        localized_date = format_localized_date(language, now)

        # Fix weekday labels: the parent parser may derive day labels from
        # date-only strings forced to UTC midnight, which shifts the weekday
        # backwards for timezones west of UTC.  Override weekday_index using
        # calendar math so the localization always maps to the correct day.
        # forecast_rows[0] = tomorrow, forecast_rows[1] = day-after, etc.
        logger.debug("Mini Weather NOW date: %s (%s)", now.strftime("%Y-%m-%d"), now.strftime("%A"))
        for i, row in enumerate(forecast_rows):
            target_date = now + datetime.timedelta(days=i + 1)
            row["weekday_index"] = target_date.weekday()  # Monday=0 .. Sunday=6
            logger.debug(
                "  Forecast row %d: %s (%s) weekday_index=%d",
                i + 1, target_date.strftime("%Y-%m-%d"), target_date.strftime("%A"), row["weekday_index"],
            )

        color_icons = settings.get("colorIcons", "false") == "true"
        forecast_rows = self._localize_forecast_rows(forecast_rows, labels)
        if not color_icons:
            current_icon = template_params.get("current_day_icon")
            if current_icon:
                template_params["current_day_icon"] = resolve_display_icon(current_icon, color_icons)
            for row in forecast_rows:
                if row.get("icon"):
                    row["icon"] = resolve_display_icon(row["icon"], color_icons)

        template_params.update(
            {
                "title": title,
                "language": normalize_language_key(language),
                "current_label": labels["now"],
                "date": localized_date,
                "weekday": format_header_weekday(language, now),
                "updated_label": format_updated_label(language, now, time_format),
                "feels_like_label": format_feels_like_label(
                    language,
                    template_params.get("feels_like"),
                    "°" if units in ("metric", "imperial") else "K",
                ),
                "weather_description": format_weather_description(
                    template_params.get("weather_description")
                ),
                "rain_label": format_rain_label(
                    language, template_params.get("rain_probability")
                ),
                "current_high": current_day["high"],
                "current_low": current_day["low"],
                "forecast_rows": forecast_rows,
                "forecast_days": len(forecast_rows),
                "provider_timezone": provider_tz.zone,
                "plugin_settings": settings,
                "show_icons": settings.get("showIcons", "true") != "false",
                "color_icons": color_icons,
            }
        )

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image = self.render_image(dimensions, "mini_weather.html", "mini_weather.css", template_params)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def _localize_forecast_rows(self, forecast_rows, labels):
        localized_rows = []
        # English abbreviations and full names used as fallback mapping
        EN_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        EN_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for row in forecast_rows:
            row_copy = dict(row)
            weekday_index = row_copy.get("weekday_index")

            # If weekday_index not present, try to derive it from the day label
            if weekday_index is None:
                day_lbl = str(row_copy.get("day", "")).strip()
                if day_lbl:
                    # try to match common 3-letter English abbreviations
                    for idx, abbr in enumerate(EN_ABBR):
                        if day_lbl.startswith(abbr) or day_lbl.lower().startswith(abbr.lower()):
                            weekday_index = idx
                            break
                    else:
                        # try full English name
                        for idx, full in enumerate(EN_FULL):
                            if day_lbl.lower().startswith(full.lower()):
                                weekday_index = idx
                                break

            if isinstance(weekday_index, int):
                row_copy["day"] = labels["days"][weekday_index % 7]

            localized_rows.append(row_copy)

        return localized_rows

    def _get_template_params(
        self,
        weather_provider,
        settings,
        units,
        lat,
        long,
        local_tz,
        time_format,
        device_config,
        language="en",
    ):
        timezone_selection = settings.get("weatherTimeZone", "locationTimeZone")
        api_key = None

        if weather_provider == "OpenWeatherMap":
            api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
            if not api_key:
                raise RuntimeError("Open Weather Map API Key not configured.")

            weather_data = self.get_weather_data(api_key, units, lat, long)
            aqi_data = self.get_air_quality(api_key, lat, long)
            tz = self.parse_timezone(weather_data) if timezone_selection == "locationTimeZone" else local_tz
            template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format, lat)
            apply_best_effort_conditions(template_params, weather_data, "OpenWeatherMap", language)
            return template_params, tz, api_key

        if weather_provider == "OpenMeteo":
            weather_data = self.get_open_meteo_data(lat, long, units, 5)
            aqi_data = self.get_open_meteo_air_quality(lat, long)
            tz = self.parse_open_meteo_timezone(weather_data) if timezone_selection == "locationTimeZone" else local_tz
            template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format, lat)
            apply_best_effort_conditions(template_params, weather_data, "OpenMeteo", language)
            return template_params, tz, api_key

        if weather_provider == "CWA":
            api_key = device_config.load_env_key("CWA_API_KEY")
            if not api_key:
                raise RuntimeError("CWA API Key not configured (set CWA_API_KEY).")

            cwa_location = (settings.get("cwaLocation") or settings.get("cwaDistrict") or "").strip()
            cwa_dataset = (settings.get("cwaDataset") or "").strip()
            if not cwa_location:
                raise RuntimeError("CWA location is required.")
            if not cwa_dataset:
                raise RuntimeError("CWA dataset is required.")

            # CWA forecast times are Taiwan local; always render in Asia/Taipei.
            tz = pytz.timezone("Asia/Taipei")

            def _icon_path(icon_stem: str) -> str:
                return self.get_plugin_dir(f"icons/{icon_stem}.png")

            template_params = fetch_and_build_template_params(
                api_key=api_key,
                base_dataset=cwa_dataset,
                location_name=cwa_location,
                units=units,
                time_format=time_format,
                icon_path_fn=_icon_path,
            )
            # Parent Weather uses temperature_unit from UNITS; keep consistent.
            template_params["temperature_unit"] = UNITS[units]["temperature"]
            return template_params, tz, api_key

        raise RuntimeError(f"Unknown weather provider: {weather_provider}")

    def _resolve_title(self, settings, weather_provider, lat, long, api_key, language):
        title_selection = settings.get("titleSelection", "location")
        custom_title = (settings.get("customTitle") or "").strip()

        if title_selection == "custom":
            if not custom_title:
                raise RuntimeError("Custom title is required.")
            return custom_title

        if weather_provider == "CWA":
            cwa_city = (settings.get("cwaCity") or "").strip()
            cwa_location = (settings.get("cwaLocation") or settings.get("cwaDistrict") or "").strip()
            if cwa_location:
                # Prefer the selected township name; it may already include the city
                # (e.g. 臺北市中正區) for disambiguation in CWA's location list.
                if cwa_city and cwa_city not in cwa_location:
                    return f"{cwa_city}{cwa_location}"
                return cwa_location
            if cwa_city:
                return cwa_city
            raise RuntimeError("CWA location is required.")

        if weather_provider == "OpenWeatherMap":
            return self.get_location(api_key, lat, long)

        return self.get_reverse_geocoded_location(lat, long, language)

    def _resolve_title_with_fallback(self, settings, weather_provider, lat, long, api_key, language):
        try:
            title = self._resolve_title(settings, weather_provider, lat, long, api_key, language)
            if is_supported_title(title):
                return title
        except Exception as exc:
            logger.warning("Mini Weather title resolution failed, using fallback: %s", exc)

        quick_location = (settings.get("quickLocation") or "").strip()
        quick_location_label = QUICK_LOCATION_LABELS.get(quick_location)
        if quick_location_label:
            return quick_location_label

        matched_city = self._match_quick_location_by_coordinates(lat, long)
        if matched_city:
            return matched_city

        return self.format_coordinates(lat, long)

    def _match_quick_location_by_coordinates(self, lat, long, tolerance=0.02):
        for city, (city_lat, city_long) in QUICK_LOCATION_COORDS.items():
            if abs(lat - city_lat) <= tolerance and abs(long - city_long) <= tolerance:
                return city
        return None

    def parse_open_meteo_timezone(self, weather_data):
        timezone_name = weather_data.get("timezone")
        if not timezone_name:
            raise RuntimeError("Timezone not found in weather data.")

        logger.info("Using timezone from Open-Meteo data: %s", timezone_name)
        return pytz.timezone(timezone_name)

    def get_reverse_geocoded_location(self, lat, long, language="en"):
        # Use rounded coordinates as cache key to avoid tiny float differences
        key = (
            round(float(lat), REVERSE_GEOCODE_ROUND_DECIMALS),
            round(float(long), REVERSE_GEOCODE_ROUND_DECIMALS),
            normalize_language_key(language),
        )

        now_ts = datetime.datetime.now().timestamp()
        cached = REVERSE_GEOCODE_CACHE.get(key)
        if cached:
            age = now_ts - cached.get("ts", 0)
            if cached.get("title") and age < REVERSE_GEOCODE_SUCCESS_TTL:
                return cached["title"]
            if cached.get("failed") and age < REVERSE_GEOCODE_FAIL_TTL:
                # recent failure — avoid retrying too quickly
                return self.format_coordinates(lat, long)

        headers = {
            "User-Agent": "InkyPi Mini Weather/1.0 (+https://github.com/inkypi)",
            "Accept-Language": get_accept_language_header(language),
        }
        try:
            response = requests.get(
                REVERSE_GEOCODE_URL.format(lat=lat, long=long),
                headers=headers,
                timeout=30,
            )
        except Exception as exc:
            logger.warning("Reverse geocode request failed: %s", exc)
            # store a failed marker to avoid hammering the service
            REVERSE_GEOCODE_CACHE[key] = {"failed": True, "ts": now_ts}
            return self.format_coordinates(lat, long)

        if not 200 <= response.status_code < 300:
            logger.warning("Failed to reverse geocode location: %s", response.content)
            REVERSE_GEOCODE_CACHE[key] = {"failed": True, "ts": now_ts}
            return self.format_coordinates(lat, long)

        try:
            location_data = response.json()
        except Exception as exc:
            logger.warning("Invalid JSON from reverse geocode: %s", exc)
            REVERSE_GEOCODE_CACHE[key] = {"failed": True, "ts": now_ts}
            return self.format_coordinates(lat, long)

        address = location_data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        region = address.get("state") or address.get("country")

        if city and region:
            title = f"{city}, {region}"
        elif city:
            title = city
        elif region:
            title = region
        else:
            display_name = location_data.get("display_name", "")
            if display_name:
                title = ", ".join(display_name.split(", ")[:2])
            else:
                title = self.format_coordinates(lat, long)

        # Cache successful result
        REVERSE_GEOCODE_CACHE[key] = {"title": title, "ts": now_ts}
        return title

    def format_coordinates(self, lat, long):
        return f"{lat:.2f}, {long:.2f}"
