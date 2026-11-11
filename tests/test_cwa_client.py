"""Unit tests for CWA client parsing (no network)."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "mini_weather"))

from cwa_client import (  # noqa: E402
    build_template_params_from_cwa_days,
    convert_temp_c,
    map_cwa_wx_to_icon,
    parse_cwa_days,
    weekly_dataset_id,
)


SAMPLE_PAYLOAD = {
    "success": True,
    "records": {
        "Locations": [
            {
                "DatasetDescription": "臺灣各縣市鄉鎮未來1週天氣預報",
                "Location": [
                    {
                        "LocationName": "臺北市大安區",
                        "Latitude": "25.026",
                        "Longitude": "121.543",
                        "WeatherElement": [
                            {
                                "ElementName": "天氣現象",
                                "Time": [
                                    {
                                        "StartTime": "2026-08-03T06:00:00+08:00",
                                        "EndTime": "2026-08-03T18:00:00+08:00",
                                        "ElementValue": [
                                            {"Weather": "多雲", "WeatherCode": "04"}
                                        ],
                                    },
                                    {
                                        "StartTime": "2026-08-03T18:00:00+08:00",
                                        "EndTime": "2026-08-04T06:00:00+08:00",
                                        "ElementValue": [
                                            {"Weather": "多雲", "WeatherCode": "04"}
                                        ],
                                    },
                                    {
                                        "StartTime": "2026-08-04T06:00:00+08:00",
                                        "EndTime": "2026-08-04T18:00:00+08:00",
                                        "ElementValue": [
                                            {"Weather": "晴時多雲", "WeatherCode": "02"}
                                        ],
                                    },
                                    {
                                        "StartTime": "2026-08-04T18:00:00+08:00",
                                        "EndTime": "2026-08-05T06:00:00+08:00",
                                        "ElementValue": [
                                            {"Weather": "晴", "WeatherCode": "01"}
                                        ],
                                    },
                                ],
                            },
                            {
                                "ElementName": "最高溫度",
                                "Time": [
                                    {
                                        "StartTime": "2026-08-03T06:00:00+08:00",
                                        "ElementValue": [{"MaxTemperature": "33"}],
                                    },
                                    {
                                        "StartTime": "2026-08-03T18:00:00+08:00",
                                        "ElementValue": [{"MaxTemperature": "28"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T06:00:00+08:00",
                                        "ElementValue": [{"MaxTemperature": "34"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T18:00:00+08:00",
                                        "ElementValue": [{"MaxTemperature": "29"}],
                                    },
                                ],
                            },
                            {
                                "ElementName": "最低溫度",
                                "Time": [
                                    {
                                        "StartTime": "2026-08-03T06:00:00+08:00",
                                        "ElementValue": [{"MinTemperature": "27"}],
                                    },
                                    {
                                        "StartTime": "2026-08-03T18:00:00+08:00",
                                        "ElementValue": [{"MinTemperature": "25"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T06:00:00+08:00",
                                        "ElementValue": [{"MinTemperature": "26"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T18:00:00+08:00",
                                        "ElementValue": [{"MinTemperature": "24"}],
                                    },
                                ],
                            },
                            {
                                "ElementName": "平均溫度",
                                "Time": [
                                    {
                                        "StartTime": "2026-08-03T06:00:00+08:00",
                                        "ElementValue": [{"Temperature": "30"}],
                                    },
                                    {
                                        "StartTime": "2026-08-03T18:00:00+08:00",
                                        "ElementValue": [{"Temperature": "26"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T06:00:00+08:00",
                                        "ElementValue": [{"Temperature": "31"}],
                                    },
                                    {
                                        "StartTime": "2026-08-04T18:00:00+08:00",
                                        "ElementValue": [{"Temperature": "27"}],
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    },
}


class CwaClientTests(unittest.TestCase):
    def test_weekly_dataset_id(self):
        self.assertEqual(weekly_dataset_id("F-D0047-061"), "F-D0047-063")
        self.assertEqual(weekly_dataset_id("F-D0047-005"), "F-D0047-007")

    def test_temp_conversion(self):
        self.assertEqual(convert_temp_c(0, "metric"), 0)
        self.assertEqual(convert_temp_c(0, "imperial"), 32)
        self.assertEqual(convert_temp_c(0, "standard"), 273)

    def test_wx_icon_mapping(self):
        self.assertEqual(map_cwa_wx_to_icon(1), "01d")
        self.assertEqual(map_cwa_wx_to_icon(18), "11d")
        self.assertEqual(map_cwa_wx_to_icon(999), "03d")

    def test_parse_daily_aggregation(self):
        days = parse_cwa_days(SAMPLE_PAYLOAD, "臺北市大安區")
        self.assertEqual(len(days), 2)
        self.assertEqual(days[0]["date"], "2026-08-03")
        self.assertEqual(days[0]["high_c"], 33)
        self.assertEqual(days[0]["low_c"], 25)
        self.assertEqual(days[0]["wx_code"], 4)
        self.assertEqual(days[1]["high_c"], 34)
        self.assertEqual(days[1]["low_c"], 24)
        self.assertEqual(days[1]["wx_code"], 2)
        self.assertEqual(days[0]["wx_text"], "多雲")
        self.assertIsNone(days[0].get("pop"))

    def test_build_template_params(self):
        days = parse_cwa_days(SAMPLE_PAYLOAD, "臺北市大安區")
        params = build_template_params_from_cwa_days(
            days,
            units="metric",
            time_format="24h",
            icon_path_fn=lambda stem: f"icons/{stem}.png",
        )
        self.assertEqual(params["current_temperature"], "30")
        self.assertEqual(params["current_day_icon"], "icons/02d.png")
        self.assertEqual(len(params["forecast"]), 2)
        self.assertEqual(params["forecast"][0]["high"], 33)
        self.assertEqual(params["forecast"][0]["low"], 25)
        self.assertEqual(params["forecast"][1]["high"], 34)
        # Sample payload has no AT / MaxAT / MinAT, so feels-like is hidden.
        self.assertIsNone(params["feels_like"])
        self.assertEqual(params["weather_description"], "多雲")
        self.assertIsNone(params["rain_probability"])

    def _payload_with_elements(self, extra_elements):
        import copy
        payload = copy.deepcopy(SAMPLE_PAYLOAD)
        loc = payload["records"]["Locations"][0]["Location"][0]
        loc["WeatherElement"].extend(extra_elements)
        return payload

    def test_weekly_max_min_at_chinese_names(self):
        """Weekly F-D0047 product: 最高/最低體感溫度 (MaxAT/MinAT)."""
        payload = self._payload_with_elements(
            [
                {
                    "ElementName": "最高體感溫度",
                    "Time": [
                        {
                            "StartTime": "2026-08-03T06:00:00+08:00",
                            "ElementValue": [{"MaxApparentTemperature": "32"}],
                        },
                        {
                            "StartTime": "2026-08-03T18:00:00+08:00",
                            "ElementValue": [{"MaxApparentTemperature": "28"}],
                        },
                        {
                            "StartTime": "2026-08-04T06:00:00+08:00",
                            "ElementValue": [{"MaxApparentTemperature": "35"}],
                        },
                        {
                            "StartTime": "2026-08-04T18:00:00+08:00",
                            "ElementValue": [{"MaxApparentTemperature": "29"}],
                        },
                    ],
                },
                {
                    "ElementName": "最低體感溫度",
                    "Time": [
                        {
                            "StartTime": "2026-08-03T06:00:00+08:00",
                            "ElementValue": [{"MinApparentTemperature": "26"}],
                        },
                        {
                            "StartTime": "2026-08-03T18:00:00+08:00",
                            "ElementValue": [{"MinApparentTemperature": "24"}],
                        },
                        {
                            "StartTime": "2026-08-04T06:00:00+08:00",
                            "ElementValue": [{"MinApparentTemperature": "27"}],
                        },
                        {
                            "StartTime": "2026-08-04T18:00:00+08:00",
                            "ElementValue": [{"MinApparentTemperature": "25"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        # Daytime (06:00) MaxAT is the single "當天體感" value on the weekly product.
        self.assertEqual(days[0]["feels_c"], 32)
        self.assertEqual(days[1]["feels_c"], 35)
        params = build_template_params_from_cwa_days(
            days, units="metric", time_format="24h",
            icon_path_fn=lambda stem: stem,
        )
        self.assertEqual(params["feels_like"], "32")

    def test_at_element_preferred_over_max_at(self):
        """3-day product AT / 體感溫度 wins over MaxAT on the same day."""
        payload = self._payload_with_elements(
            [
                {
                    "ElementName": "體感溫度",
                    "Time": [
                        {
                            "StartTime": "2026-08-03T06:00:00+08:00",
                            "ElementValue": [{"ApparentTemperature": "21"}],
                        },
                        {
                            "StartTime": "2026-08-03T18:00:00+08:00",
                            "ElementValue": [{"ApparentTemperature": "19"}],
                        },
                    ],
                },
                {
                    "elementName": "MaxAT",
                    "Time": [
                        {
                            "startTime": "2026-08-03T06:00:00+08:00",
                            "elementValue": [{"value": "32"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        self.assertEqual(days[0]["feels_c"], 21)
        params = build_template_params_from_cwa_days(
            days, units="imperial", time_format="24h",
            icon_path_fn=lambda stem: stem,
        )
        # 21°C → 70°F
        self.assertEqual(params["feels_like"], "70")

    def test_english_maxat_element_name(self):
        payload = self._payload_with_elements(
            [
                {
                    "elementName": "MaxAT",
                    "Time": [
                        {
                            "startTime": "2026-08-03T06:00:00+08:00",
                            "elementValue": [{"MaxApparentTemperature": "29"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        self.assertEqual(days[0]["feels_c"], 29)

    def test_weekly_pop12h_chinese_names(self):
        """Weekly F-D0047 product: 12小時降雨機率 (PoP12h)."""
        payload = self._payload_with_elements(
            [
                {
                    "ElementName": "12小時降雨機率",
                    "Time": [
                        {
                            "StartTime": "2026-08-03T06:00:00+08:00",
                            "ElementValue": [{"ProbabilityOfPrecipitation": "20"}],
                        },
                        {
                            "StartTime": "2026-08-03T18:00:00+08:00",
                            "ElementValue": [{"ProbabilityOfPrecipitation": "40"}],
                        },
                        {
                            "StartTime": "2026-08-04T06:00:00+08:00",
                            "ElementValue": [{"ProbabilityOfPrecipitation": "10"}],
                        },
                        {
                            "StartTime": "2026-08-04T18:00:00+08:00",
                            "ElementValue": [{"value": "-"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        # Daytime (06:00) PoP is today's single rain-probability figure.
        self.assertEqual(days[0]["pop"], 20)
        self.assertEqual(days[1]["pop"], 10)
        params = build_template_params_from_cwa_days(
            days, units="metric", time_format="24h",
            icon_path_fn=lambda stem: stem,
        )
        self.assertEqual(params["rain_probability"], 20)
        self.assertEqual(params["weather_description"], "多雲")

    def test_pop_english_element_name_and_zero(self):
        payload = self._payload_with_elements(
            [
                {
                    "elementName": "PoP12h",
                    "Time": [
                        {
                            "startTime": "2026-08-03T06:00:00+08:00",
                            "elementValue": [{"value": "0"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        self.assertEqual(days[0]["pop"], 0)
        params = build_template_params_from_cwa_days(
            days, units="metric", time_format="24h",
            icon_path_fn=lambda stem: stem,
        )
        self.assertEqual(params["rain_probability"], 0)

    def test_pop_missing_dash_stays_hidden(self):
        payload = self._payload_with_elements(
            [
                {
                    "ElementName": "降雨機率",
                    "Time": [
                        {
                            "StartTime": "2026-08-03T06:00:00+08:00",
                            "ElementValue": [{"ProbabilityOfPrecipitation": "-"}],
                        },
                    ],
                },
            ]
        )
        days = parse_cwa_days(payload, "臺北市大安區")
        self.assertIsNone(days[0]["pop"])
        params = build_template_params_from_cwa_days(
            days, units="metric", time_format="24h",
            icon_path_fn=lambda stem: stem,
        )
        self.assertIsNone(params["rain_probability"])

    def test_location_not_found(self):

        with self.assertRaises(RuntimeError):
            parse_cwa_days(SAMPLE_PAYLOAD, "不存在區")


if __name__ == "__main__":
    unittest.main()
