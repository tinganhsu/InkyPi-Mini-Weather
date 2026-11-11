"""Unit tests for new-layout helpers (no network, no InkyPi parent)."""

from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# mini_weather.py imports InkyPi's parent Weather plugin and pytz/requests.
# Stub those so the helper functions can be tested in isolation.
def _stub_inky_deps():
    if "pytz" not in sys.modules:
        sys.modules["pytz"] = types.ModuleType("pytz")
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")

    weather = types.ModuleType("plugins.weather.weather")
    weather.UNITS = {
        "metric": {"temperature": "C"},
        "imperial": {"temperature": "F"},
        "standard": {"temperature": "K"},
    }

    class Weather:  # noqa: D401
        pass

    weather.Weather = Weather
    sys.modules.setdefault("plugins", types.ModuleType("plugins"))
    sys.modules.setdefault("plugins.weather", types.ModuleType("plugins.weather"))
    sys.modules["plugins.weather.weather"] = weather


_stub_inky_deps()
sys.path.insert(0, os.path.join(ROOT, "mini_weather"))

from mini_weather import (  # noqa: E402
    format_header_weekday,
    format_localized_date,
    format_feels_like_label,
    format_rain_label,
    format_updated_label,
    format_weather_description,
    normalize_rain_probability,
    open_meteo_weather_description,
    extract_owm_today_extras,
    extract_open_meteo_today_extras,
    resolve_display_icon,
)


class LayoutHelperTests(unittest.TestCase):
    def setUp(self):
        self.dt = datetime(2026, 11, 11, 8, 6, tzinfo=ZoneInfo("Asia/Taipei"))

    def test_zh_tw_header_date_and_weekday(self):
        self.assertEqual(format_localized_date("zh-tw", self.dt), "2026年11月11日")
        self.assertEqual(format_header_weekday("zh-tw", self.dt), "星期三")

    def test_en_header_weekday(self):
        self.assertEqual(format_header_weekday("en", self.dt), "Wednesday")
        self.assertEqual(format_header_weekday("en-US", self.dt), "Wednesday")

    def test_updated_label_24h_zh_tw(self):
        self.assertEqual(format_updated_label("zh-tw", self.dt, "24h"), "08:06 更新")
        # zh-tw stays 24-hour even if the device is set to 12h
        self.assertEqual(format_updated_label("zh-tw", self.dt, "12h"), "08:06 更新")

    def test_updated_label_12h_en(self):
        self.assertEqual(format_updated_label("en", self.dt, "12h"), "Updated 8:06 AM")
        self.assertEqual(format_updated_label("en", self.dt, "24h"), "Updated 08:06")

    def test_resolve_display_icon_swaps_to_outline_svg(self):
        png = Path(ROOT) / "mini_weather" / "icons" / "01d.png"
        svg = resolve_display_icon(str(png), color_icons=False)
        self.assertTrue(svg.endswith("icons/outline/01d.svg"), svg)
        self.assertTrue(Path(svg).is_file())

    def test_resolve_display_icon_keeps_colour_png(self):
        png = Path(ROOT) / "mini_weather" / "icons" / "01d.png"
        self.assertEqual(resolve_display_icon(str(png), color_icons=True), str(png))

    def test_resolve_display_icon_missing_stem_falls_back(self):
        missing = "/tmp/not-a-real-icon.png"
        self.assertEqual(resolve_display_icon(missing, color_icons=False), missing)

    def test_feels_like_label_zh_tw_and_en(self):
        self.assertEqual(format_feels_like_label("zh-tw", 21), "體感 21°")
        self.assertEqual(format_feels_like_label("zh-tw", "21"), "體感 21°")
        self.assertEqual(format_feels_like_label("en", 21), "Feels 21°")
        self.assertEqual(format_feels_like_label("en", 294, "K"), "Feels 294 K")

    def test_feels_like_label_hidden_when_missing(self):
        self.assertEqual(format_feels_like_label("zh-tw", None), "")
        self.assertEqual(format_feels_like_label("en", "--"), "")
        self.assertEqual(format_feels_like_label("en", ""), "")

    def test_rain_label_zh_tw_and_en(self):
        self.assertEqual(format_rain_label("zh-tw", 20), "降雨 20%")
        self.assertEqual(format_rain_label("zh-tw", "20"), "降雨 20%")
        self.assertEqual(format_rain_label("en", 20), "Rain 20%")
        self.assertEqual(format_rain_label("zh-tw", 0), "降雨 0%")

    def test_rain_label_hidden_when_missing(self):
        self.assertEqual(format_rain_label("zh-tw", None), "")
        self.assertEqual(format_rain_label("en", "--"), "")
        self.assertEqual(format_rain_label("en", "-"), "")
        self.assertEqual(format_rain_label("en", ""), "")

    def test_normalize_rain_probability(self):
        self.assertEqual(normalize_rain_probability(20), 20)
        self.assertEqual(normalize_rain_probability(0.2), 20)
        self.assertEqual(normalize_rain_probability("20%"), 20)
        self.assertEqual(normalize_rain_probability(0), 0)
        self.assertEqual(normalize_rain_probability(0.0), 0)
        self.assertIsNone(normalize_rain_probability("-"))
        self.assertIsNone(normalize_rain_probability(None))

    def test_weather_description_hidden_when_missing(self):
        self.assertEqual(format_weather_description("多雲"), "多雲")
        self.assertEqual(format_weather_description("  "), "")
        self.assertEqual(format_weather_description(None), "")
        self.assertEqual(format_weather_description("--"), "")

    def test_open_meteo_weather_description(self):
        self.assertEqual(open_meteo_weather_description(3, "zh-tw"), "陰")
        self.assertEqual(open_meteo_weather_description(3, "en"), "Overcast")
        self.assertEqual(open_meteo_weather_description(2, "zh-tw"), "多雲時晴")
        self.assertEqual(open_meteo_weather_description(None, "en"), "")

    def test_extract_owm_today_extras(self):
        data = {
            "current": {"weather": [{"description": "overcast clouds", "icon": "04d"}]},
            "daily": [{"pop": 0.2, "temp": {"max": 24, "min": 18}}],
        }
        description, rain = extract_owm_today_extras(data)
        self.assertEqual(description, "overcast clouds")
        self.assertEqual(rain, 20)

    def test_extract_open_meteo_today_extras(self):
        data = {
            "current": {"time": "2026-11-11T08:00", "weather_code": 3},
            "hourly": {
                "time": ["2026-11-11T08:00", "2026-11-11T14:00", "2026-11-12T08:00"],
                "precipitation_probability": [10, 20, 90],
            },
        }
        description, rain = extract_open_meteo_today_extras(data, "zh-tw")
        self.assertEqual(description, "陰")
        self.assertEqual(rain, 20)
        data["daily"] = {"precipitation_probability_max": [35]}
        description, rain = extract_open_meteo_today_extras(data, "en")
        self.assertEqual(description, "Overcast")
        self.assertEqual(rain, 35)


if __name__ == "__main__":
    unittest.main()
