import base64
import datetime
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Provide lightweight stub for google.genai when running tests in environments without google-genai installed
if "google" not in sys.modules:
    google_pkg = types.ModuleType("google")
    google_pkg.__path__ = []
    sys.modules["google"] = google_pkg
if "google.genai" not in sys.modules:
    genai_mod = types.ModuleType("google.genai")
    genai_mod.Client = MagicMock()
    sys.modules["google.genai"] = genai_mod
    sys.modules["google"].genai = genai_mod

import config
import utils
import garmin_service
import weather_service
import ai_service
import notifier
import chart_service
import main


class TestConfig(unittest.TestCase):
    def test_empty_env_vars_fallback_to_defaults(self):
        env_overrides = {
            "RUNNER_NAME": "",
            "RUNNER_BIRTH_YEAR": "   ",
            "RUNNER_PB": "",
            "ZONE2_MAX_HR": "",
            "TZ_OFFSET_HOURS": "",
            "ACTIVITIES_COUNT": "",
            "DEFAULT_LAT": "",
            "DEFAULT_LON": "",
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            reloaded = importlib.reload(config)
            self.assertEqual(reloaded.RUNNER_NAME, "Runner")
            self.assertEqual(reloaded.RUNNER_BIRTH_YEAR, 1985)
            self.assertEqual(reloaded.RUNNER_PB, "3:45")
            self.assertEqual(reloaded.ZONE2_MAX_HR, 140)
            self.assertEqual(reloaded.TZ_OFFSET_HOURS, 8)
            self.assertEqual(reloaded.ACTIVITIES_COUNT, 7)
            self.assertAlmostEqual(reloaded.DEFAULT_LAT, 25.03)
            self.assertAlmostEqual(reloaded.DEFAULT_LON, 121.56)

        importlib.reload(config)

    def test_zero_string_env_var_is_preserved(self):
        with patch.dict(os.environ, {"TZ_OFFSET_HOURS": "0"}, clear=False):
            reloaded = importlib.reload(config)
            self.assertEqual(reloaded.TZ_OFFSET_HOURS, 0)
        importlib.reload(config)


class TestUtils(unittest.TestCase):
    def test_check_activity_recency_uses_local_now(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        with patch.object(utils, "get_local_now", return_value=fake_now):
            is_recent, diff = utils.check_activity_recency("2026-11-15 20:00:00", max_hours=26)
            self.assertTrue(is_recent)
            self.assertAlmostEqual(diff, 8.0)

            is_recent_old, diff_old = utils.check_activity_recency("2026-11-15 01:00:00", max_hours=26)
            self.assertFalse(is_recent_old)
            self.assertAlmostEqual(diff_old, 27.0)

    def test_select_yesterday_activity_prefers_main_run_and_ignores_today(self):
        # 即使排程延遲至 08:00 才跑且跑者今日 06:00 已晨跑，仍應精準鎖定「昨日」的主跑步課表
        fake_now = datetime.datetime(2026, 11, 16, 8, 0, 0)
        activities = [
            {
                "activityId": 3,
                "startTimeLocal": "2026-11-16 06:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 5000,
                "duration": 1500,
            },
            {
                "activityId": 2,
                "startTimeLocal": "2026-11-15 21:15:00",
                "activityType": {"typeKey": "walking"},
                "distance": 1200,
                "duration": 900,
            },
            {
                "activityId": 1,
                "startTimeLocal": "2026-11-15 05:30:00",
                "activityType": {"typeKey": "running"},
                "distance": 15000,
                "duration": 4500,
            },
        ]
        primary, others, history, diff = utils.select_yesterday_activity(activities, reference_now=fake_now)
        self.assertEqual(primary["activityId"], 1)
        self.assertEqual(len(others), 1)
        self.assertEqual(others[0]["activityId"], 2)
        self.assertEqual([a["activityId"] for a in history], [2, 1])
        self.assertAlmostEqual(diff, 26.5)

    def test_select_yesterday_activity_rest_day(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            {
                "activityId": 1,
                "startTimeLocal": "2026-11-14 18:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 10000,
                "duration": 3000,
            }
        ]
        primary, others, history, diff = utils.select_yesterday_activity(activities, reference_now=fake_now)
        self.assertIsNone(primary)
        self.assertEqual(others, [])
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(diff, 34.0)

    def test_select_yesterday_activity_dedups_and_sorts_newest_first(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            {"activityId": 1, "startTimeLocal": "2026-11-12 18:00:00", "activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1500},
            {"activityId": 2, "startTimeLocal": "2026-11-14 18:00:00", "activityType": {"typeKey": "running"}, "distance": 8000, "duration": 2400},
            {"activityId": 2, "startTimeLocal": "2026-11-14 18:00:00", "activityType": {"typeKey": "running"}, "distance": 8000, "duration": 2400},
        ]
        primary, _, history, diff = utils.select_yesterday_activity(activities, reference_now=fake_now)
        self.assertIsNone(primary)
        self.assertEqual([a["activityId"] for a in history], [2, 1])
        self.assertAlmostEqual(diff, 34.0)

    def test_calculate_acwr_zones_and_excludes_today(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            # 今日 (D) 活動不應計入「截至昨日」的 ACWR
            {"startTimeLocal": "2026-11-16 01:00:00", "activityTrainingLoad": 500},
        ]
        # 28 days of baseline load up to yesterday: 120 in recent 7 days + 300 prior
        for day_offset in [2, 5, 10, 17, 24]:
            dt = fake_now - datetime.timedelta(days=day_offset)
            load = 60 if day_offset < 7 else 100
            activities.append({
                "startTimeLocal": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "activityTrainingLoad": load,
            })
        res = utils.calculate_acwr(activities, reference_now=fake_now)
        self.assertEqual(res["acute_load"], 120)
        self.assertEqual(res["chronic_load"], 105)  # (120 + 300) / 4 = 105
        self.assertEqual(res["status_zone"], "optimal")

    def test_calculate_rolling_mileage_and_laps_distance_formatting(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            {"activityId": 99, "startTimeLocal": "2026-11-16 01:00:00", "activityType": {"typeKey": "running"}, "distance": 50000},
            {"activityId": 1, "startTimeLocal": "2026-11-14 18:00:00", "activityType": {"typeKey": "running"}, "distance": 10000},
            {"activityId": 1, "startTimeLocal": "2026-11-14 18:00:00", "activityType": {"typeKey": "running"}, "distance": 10000},
            {"activityId": 2, "startTimeLocal": "2026-11-11 18:00:00", "activityType": {"typeKey": "walking"}, "distance": 8000},
            {"activityId": 3, "startTimeLocal": "2026-10-25 06:00:00", "activityType": {"typeKey": "treadmill_running"}, "distance": 14000},
        ]
        m = utils.calculate_rolling_mileage(activities, reference_now=fake_now)
        self.assertAlmostEqual(m["run_km_7d"], 10.0)
        self.assertEqual(m["run_count_7d"], 1)
        self.assertAlmostEqual(m["run_km_28d_weekly_avg"], 6.0)  # (10 + 14) / 4

        laps_text = utils.format_laps_table([
            {"lapIndex": 0, "distance": 1000, "averageSpeed": 3.33, "averageHR": 145, "elevationGain": 2, "averageRunCadence": 176, "duration": 300},
            {"lapIndex": 1, "distance": 195, "averageSpeed": 3.50, "averageHR": 160, "elevationGain": 0, "averageRunCadence": 182, "duration": 56},
        ])
        self.assertIn("L01: 1.00km |", laps_text)
        self.assertIn("L02: 195m |", laps_text)

    def test_calculate_vdot_paces(self):
        res = utils.calculate_vdot_paces("3:45")
        self.assertGreater(res["vdot"], 38.0)
        self.assertLess(res["vdot"], 45.0)
        self.assertNotEqual(res["m_pace"], "N/A")
        self.assertNotEqual(res["t_pace"], "N/A")

    def test_calculate_aerobic_decoupling_steady_and_interval(self):
        steady_laps = [
            {"distance": 1000, "duration": 330, "averageHR": 140} for _ in range(4)
        ] + [
            {"distance": 1000, "duration": 330, "averageHR": 147} for _ in range(4)
        ] + [
            {"distance": 200, "duration": 70, "averageHR": 145}
        ]
        res = utils.calculate_aerobic_decoupling(steady_laps)
        self.assertIsNotNone(res)
        self.assertTrue(res["is_steady_state"])
        self.assertAlmostEqual(res["split_lap_x"], 4.5)
        self.assertGreater(res["decoupling_pct"], 0)

        formatted_steady = utils.format_aerobic_decoupling(res)
        self.assertIn("前半程 vs 後半程配速: 5:30 → 5:31", formatted_steady)
        self.assertIn("Positive Split", formatted_steady)

        even_laps = [
            {"distance": 1000, "duration": 330, "averageHR": 140} for _ in range(4)
        ] + [
            {"distance": 1000, "duration": 330, "averageHR": 145} for _ in range(4)
        ]
        formatted_even = utils.format_aerobic_decoupling(utils.calculate_aerobic_decoupling(even_laps))
        self.assertIn("5:30 → 5:30", formatted_even)
        self.assertIn("Even Split", formatted_even)

        # 後半程加速 (Negative Split) + 功率欄位存在時仍須正確顯示配速變化
        neg_split_laps = [
            {"distance": 1000, "duration": 320, "averageHR": 145, "avgPower": 260} for _ in range(3)
        ] + [
            {"distance": 1000, "duration": 300, "averageHR": 152, "avgPower": 280} for _ in range(3)
        ]
        neg_res = utils.calculate_aerobic_decoupling(neg_split_laps)
        formatted_neg = utils.format_aerobic_decoupling(neg_res)
        self.assertIn("5:20 → 5:00", formatted_neg)
        self.assertIn("Negative Split", formatted_neg)

        interval_laps = [
            {"distance": 1000, "duration": 220, "averageHR": 172},  # 4.55 m/s
            {"distance": 400, "duration": 180, "averageHR": 135},   # 2.22 m/s
            {"distance": 1000, "duration": 220, "averageHR": 175},
            {"distance": 400, "duration": 180, "averageHR": 138},
            {"distance": 1000, "duration": 220, "averageHR": 178},
        ]
        interval_res = utils.calculate_aerobic_decoupling(interval_laps)
        self.assertIsNotNone(interval_res)
        self.assertFalse(interval_res["is_steady_state"])
        self.assertIn("非穩態/間歇課表僅供參考", interval_res["status_desc"])

    def test_clean_ai_text(self):
        self.assertEqual(utils.clean_ai_text(r"A $\rightarrow$ B \to C"), "A → B → C")
        self.assertEqual(
            utils.clean_ai_text("### 賽後復盤\n  * **訓練型態判定**：**正式賽事**\n負荷 2 * 3 與 snake_case"),
            "賽後復盤\n  • 訓練型態判定：正式賽事\n負荷 2 * 3 與 snake_case",
        )

    def test_format_upcoming_races_excludes_past_and_formats_yesterday_context(self):
        races = [
            {"title": "2026 Mother Marathon 北港媽祖盃全國馬拉松", "date": "2026-11-21", "days_left": -1, "distance_km": 42.2},
            {"title": "Taipei Marathon", "date": "2026-12-20", "days_left": 28, "distance_km": 42.2},
        ]
        upcoming_text = utils.format_upcoming_races(races)
        self.assertIn("Taipei Marathon", upcoming_text)
        self.assertNotIn("2026 Mother Marathon", upcoming_text)

        is_race, note = utils.format_yesterday_race_context({"eventTypeDTO": {"typeKey": "race"}}, [races[0]])
        self.assertTrue(is_race)
        self.assertIn("2026 Mother Marathon 北港媽祖盃全國馬拉松 (42.2km)", note)
        self.assertIn("[活動事件類型: race]", note)

        is_watch_race, watch_note = utils.format_yesterday_race_context({"eventTypeDTO": {"typeKey": "race"}}, [])
        self.assertTrue(is_watch_race)
        self.assertIn("eventType: race", watch_note)

        is_plain, plain_note = utils.format_yesterday_race_context({"eventTypeDTO": {"typeKey": "uncategorized"}}, [])
        self.assertFalse(is_plain)
        self.assertEqual(plain_note, "")

        recent_text = utils.format_recent_races([
            {"title": "2026 Mother Marathon", "date": "2026-11-21", "days_left": -2, "distance_km": 42.2}
        ])
        self.assertIn("近期剛完賽目標賽事", recent_text)
        self.assertIn("2 天前完賽", recent_text)


class TestGarminService(unittest.TestCase):
    def test_fetch_extended_activities_prefers_date_range_and_falls_back(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        mock_client = MagicMock()
        mock_client.get_activities_by_date.return_value = [{"activityId": 99}]

        with patch.object(garmin_service, "get_local_now", return_value=fake_now):
            res = garmin_service.fetch_extended_activities(mock_client, count=35, days=28)
            self.assertEqual(res, [{"activityId": 99}])
            mock_client.get_activities_by_date.assert_called_once_with("2026-10-19", "2026-11-16")

        mock_client.get_activities_by_date.side_effect = RuntimeError("API error")
        mock_client.get_activities.return_value = [{"activityId": 88}]
        with patch.object(garmin_service, "get_local_now", return_value=fake_now):
            res = garmin_service.fetch_extended_activities(mock_client, count=35, days=28)
            self.assertEqual(res, [{"activityId": 88}])
            mock_client.get_activities.assert_called_once_with(0, 35)

    def test_fetch_upcoming_races_dedup_and_local_today(self):
        fake_now = datetime.datetime(2026, 11, 16, 3, 55, 0)
        mock_client = MagicMock()
        # Same race returned across two monthly calendar fetches
        race_item = {
            "id": 12345,
            "itemType": "event",
            "date": "2026-11-16",
            "title": "Taipei Marathon",
            "distance": 42195,
        }
        mock_client.get_scheduled_workouts.return_value = {"calendarItems": [race_item]}

        with patch.object(garmin_service, "get_local_now", return_value=fake_now):
            races = garmin_service.fetch_upcoming_races(mock_client, months_ahead=2)
            self.assertEqual(len(races), 1)
            self.assertEqual(races[0]["days_left"], 0)
            self.assertEqual(races[0]["distance_km"], 42.2)

    def test_fetch_upcoming_races_includes_yesterday_across_month_boundary(self):
        fake_now = datetime.datetime(2026, 12, 1, 4, 0, 0)
        mock_client = MagicMock()

        def fake_get_scheduled_workouts(year, month):
            if (year, month) == (2026, 11):
                return {
                    "calendarItems": [{
                        "id": 999,
                        "itemType": "event",
                        "date": "2026-11-30",
                        "title": "Month End Marathon",
                        "distance": 42195,
                    }]
                }
            return {"calendarItems": []}

        mock_client.get_scheduled_workouts.side_effect = fake_get_scheduled_workouts

        with patch.object(garmin_service, "get_local_now", return_value=fake_now):
            races_default = garmin_service.fetch_upcoming_races(mock_client, months_ahead=1)
            self.assertEqual(races_default, [])

            races_with_yest = garmin_service.fetch_upcoming_races(mock_client, months_ahead=1, days_back=1)
            self.assertEqual(len(races_with_yest), 1)
            self.assertEqual(races_with_yest[0]["title"], "Month End Marathon")
            self.assertEqual(races_with_yest[0]["days_left"], -1)
            mock_client.get_scheduled_workouts.assert_any_call(2026, 11)

    def test_get_garmin_client_prefers_tokenstore_and_decodes_base64(self):
        raw_json = json.dumps({"di_token": "tok", "di_refresh_token": "ref", "di_client_id": "cid"})
        b64_token = base64.b64encode(raw_json.encode("utf-8")).decode("ascii")
        mock_instance = MagicMock()

        with patch.object(garmin_service, "GARMIN_EMAIL", None), \
             patch.object(garmin_service, "GARMIN_PWD", None), \
             patch.object(garmin_service, "GARMIN_TOKENS", b64_token), \
             patch.object(garmin_service, "Garmin", return_value=mock_instance) as mock_garmin:
            client = garmin_service.get_garmin_client()
            self.assertIs(client, mock_instance)
            mock_garmin.assert_called_once_with(None, None)
            mock_instance.login.assert_called_once_with(raw_json)

    def test_get_garmin_client_falls_back_to_credentials_when_token_fails(self):
        raw_json = '{"di_token": "bad"}'
        first_client = MagicMock()
        first_client.login.side_effect = RuntimeError("Expired token")
        second_client = MagicMock()

        def verify_env_cleared():
            self.assertNotIn("GARMINTOKENS", os.environ)
            return (None, None)

        second_client.login.side_effect = verify_env_cleared

        with patch.dict(os.environ, {"GARMINTOKENS": raw_json}, clear=False), \
             patch.object(garmin_service, "GARMIN_EMAIL", "runner@example.com"), \
             patch.object(garmin_service, "GARMIN_PWD", "secret"), \
             patch.object(garmin_service, "GARMIN_TOKENS", raw_json), \
             patch.object(garmin_service, "Garmin", side_effect=[first_client, second_client]) as mock_garmin:
            client = garmin_service.get_garmin_client()
            self.assertIs(client, second_client)
            self.assertEqual(mock_garmin.call_count, 2)
            first_client.login.assert_called_once_with(raw_json)
            second_client.login.assert_called_once_with()
            self.assertEqual(os.environ.get("GARMINTOKENS"), raw_json)

    def test_get_garmin_client_requires_token_or_credentials(self):
        with patch.object(garmin_service, "GARMIN_EMAIL", None), \
             patch.object(garmin_service, "GARMIN_PWD", None), \
             patch.object(garmin_service, "GARMIN_TOKENS", None):
            with self.assertRaises(ValueError):
                garmin_service.get_garmin_client()


class TestWeatherService(unittest.TestCase):
    def test_get_open_meteo_weather_no_false_fallback_on_missing_timestamp(self):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "hourly": {
                "time": ["2026-11-16T23:00"],
                "temperature_2m": [20.0],
                "relative_humidity_2m": [80],
                "apparent_temperature": [21.0],
                "wind_speed_10m": [10.0],
                "weather_code": [0],
            }
        }
        with patch.object(weather_service.requests, "get", return_value=mock_res):
            res = weather_service.get_open_meteo_weather(25.03, 121.56, "2026-11-15 06:00:00")
            self.assertIsNone(res)

            res_hit = weather_service.get_open_meteo_weather(25.03, 121.56, "2026-11-16 23:15:00")
            self.assertIsNotNone(res_hit)
            self.assertEqual(res_hit["wind_speed"], 10.0)
            self.assertEqual(res_hit["weather_desc"], "晴")

    def test_get_today_weather_forecast(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "hourly": {
                "time": ["2026-11-16T06:00", "2026-11-16T16:00", "2026-11-16T20:00"],
                "temperature_2m": [19.5, 24.0, 21.0],
                "relative_humidity_2m": [75, 65, 78],
                "apparent_temperature": [19.0, 25.0, 21.5],
                "precipitation_probability": [10, 20, 60],
                "wind_speed_10m": [8.5, 12.0, 14.0],
                "weather_code": [1, 0, 61],
            }
        }
        with patch.object(weather_service, "get_local_now", return_value=fake_now), \
             patch.object(weather_service.requests, "get", return_value=mock_res):
            slots = weather_service.get_today_weather_forecast(25.03, 121.56)
            self.assertEqual(len(slots), 3)
            formatted = weather_service.format_today_forecast(slots)
            self.assertIn("清晨 (06:00)", formatted)
            self.assertIn("降雨 60%", formatted)
            self.assertIn("風速 14.0km/h", formatted)


class TestAIService(unittest.TestCase):
    def _make_model(self, name, actions=("generateContent",)):
        m = MagicMock()
        m.name = name
        m.supported_actions = list(actions)
        return m

    def test_detect_candidate_models_cross_gen_and_filters_unavailable_fallback(self):
        mock_client = MagicMock()
        mock_client.models.list.return_value = [
            self._make_model("models/gemini-4-hydrogen"),
            self._make_model("models/gemini-4-hydrogen-lite"),
            self._make_model("models/gemini-3.0-flash"),
            self._make_model("models/gemini-3.0-flash-image"),
            self._make_model("models/gemini-2.5-flash"),
            self._make_model("models/gemini-2.0-flash"),
            self._make_model("models/gemini-2.0-flash-lite"),
            self._make_model("models/gemini-flash-latest"),
            # Notice gemini-1.5-flash is intentionally absent (retired)
        ]

        candidates = ai_service.detect_candidate_models(mock_client)
        self.assertEqual(candidates[0], "models/gemini-4-hydrogen")
        self.assertEqual(candidates[1], "models/gemini-3.0-flash")
        self.assertNotIn("models/gemini-4-hydrogen-lite", candidates)
        self.assertNotIn("models/gemini-3.0-flash-image", candidates)
        self.assertNotIn("models/gemini-1.5-flash", candidates)
        self.assertIn("models/gemini-2.5-flash", candidates)

    def test_invoke_models_immediate_failover_on_404_and_retry_on_503(self):
        mock_client = MagicMock()
        calls = []

        def fake_generate(model, contents):
            calls.append(model)
            if model == "models/m1":
                raise RuntimeError("404 NOT_FOUND")
            if model == "models/m2":
                if calls.count("models/m2") == 1:
                    raise RuntimeError("503 UNAVAILABLE")
                resp = MagicMock()
                resp.text = "Advice OK"
                return resp
            raise RuntimeError("Unexpected")

        mock_client.models.generate_content.side_effect = fake_generate

        with patch.object(ai_service.time, "sleep") as mock_sleep:
            text, used = ai_service.generate_coach_advice(
                mock_client, ["models/m1", "models/m2", "models/m3"], "report"
            )
            self.assertEqual(text, "Advice OK")
            self.assertEqual(used, "models/m2")
            # m1 should be called only ONCE (immediate failover on 404), m2 TWICE (retry once on 503)
            self.assertEqual(calls, ["models/m1", "models/m2", "models/m2"])
            mock_sleep.assert_called_once_with(2)

    def test_none_client_returns_rule_engine_fallback_without_sleeping(self):
        text, used = ai_service.generate_rest_day_advice(None, ["models/m1"], "report")
        self.assertEqual(used, "fallback-rule-engine")
        self.assertIn("GEMINI_API_KEY", text)

    def test_generate_coach_advice_prompt_includes_race_guidance(self):
        mock_client = MagicMock()
        captured = []

        def fake_generate(model, contents):
            captured.append(contents)
            resp = MagicMock()
            resp.text = "Race Analysis"
            return resp

        mock_client.models.generate_content.side_effect = fake_generate
        ai_service.generate_coach_advice(mock_client, ["models/m1"], "🏁 賽事關聯: Test Marathon")
        self.assertEqual(len(captured), 1)
        self.assertIn("正式賽事 (Race Day)", captured[0])
        self.assertIn("🏁 賽事關聯", captured[0])
        self.assertIn("賽後恢復期", captured[0])

    def test_generate_rest_day_advice_prompt_includes_post_race_recovery(self):
        mock_client = MagicMock()
        captured = []

        def fake_generate(model, contents):
            captured.append(contents)
            resp = MagicMock()
            resp.text = "Post-Race Rest"
            return resp

        mock_client.models.generate_content.side_effect = fake_generate
        ai_service.generate_rest_day_advice(mock_client, ["models/m1"], "🏁 【近期剛完賽目標賽事】")
        self.assertEqual(len(captured), 1)
        self.assertIn("賽後漸進恢復期", captured[0])
        self.assertIn("嚴禁使用", captured[0])


class TestNotifier(unittest.TestCase):
    def test_split_telegram_text_preserves_lines(self):
        part1 = "📊 【報告數據】\n" + "\n".join(f"Line {i:03d}: " + ("A" * 40) for i in range(120))
        part2 = "🤖 【Gemini AI 教練建議】\n建議內容如下。"
        chunks = notifier.split_telegram_text(part1 + "\n\n" + part2, max_chars=4000)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(chunks[-1].startswith("🤖 【Gemini AI 教練建議】"))
        for c in chunks:
            self.assertLessEqual(len(c), 4000)
        # Ensure no line in part1 was split mid-line
        rejoined_p1 = "\n".join(chunks[:-1])
        for i in range(120):
            self.assertIn(f"Line {i:03d}: " + ("A" * 40), rejoined_p1)


class TestChartService(unittest.TestCase):
    def test_generate_all_telemetry_charts(self):
        acwr_data = {"acwr": 1.15, "acute_load": 230, "chronic_load": 200, "status_zone": "optimal", "status_desc": "Sweet Spot"}
        hr_zones = [{"zoneNumber": i, "secsInZone": i * 120} for i in range(1, 6)]
        laps = [{"averageSpeed": 3.0 + i * 0.02, "averageHR": 140 + i, "distance": 1000, "duration": 330} for i in range(5)]
        decoupling = {"decoupling_pct": 2.1, "status_zone": "excellent", "status_desc": "Elite", "split_lap_x": 2.5}

        with tempfile.TemporaryDirectory() as tmpdir:
            charts = chart_service.generate_all_telemetry_charts(
                {"activityId": 1}, laps, acwr_data, hr_zones, decoupling_data=decoupling, output_dir=tmpdir
            )
            self.assertEqual(len(charts), 3)
            for path, caption in charts:
                self.assertTrue(os.path.exists(path))
                self.assertGreater(os.path.getsize(path), 1000)
                self.assertTrue(len(caption) > 0)

    def test_marathon_laps_chart_adaptive_ticks_and_outlier_ylim(self):
        ticks = chart_service._select_lap_ticks(list(range(1, 44)))
        self.assertLessEqual(len(ticks), 12)
        self.assertEqual(ticks[0], 1)
        self.assertEqual(ticks[-1], 43)

        # 42 圈約 5:00/km，最後第 43 圈是極慢速 16:40/km (1.0 m/s) 零頭圈
        marathon_laps = [
            {"averageSpeed": 3.33, "averageHR": 160, "distance": 1000, "duration": 300} for _ in range(42)
        ] + [{"averageSpeed": 1.0, "averageHR": 145, "distance": 195, "duration": 195}]
        ylim = chart_service._compute_pace_ylim([(1000 / l["averageSpeed"]) / 60 for l in marathon_laps])
        self.assertIsNotNone(ylim)
        self.assertLess(ylim[0], 7.0)  # 反轉軸下方不應被 16.7 min/km 拉扁

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "marathon_laps.png")
            ok = chart_service.generate_laps_trend_chart(marathon_laps, save_path=out_path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 1000)


class TestMainFlow(unittest.TestCase):
    def test_run_main_task_active_day_with_primary_and_other_activity(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            {
                "activityId": 2,
                "startTimeLocal": "2026-11-15 21:15:00",
                "activityType": {"typeKey": "walking"},
                "distance": 1200,
                "duration": 900,
                "calories": 60,
            },
            {
                "activityId": 1,
                "startTimeLocal": "2026-11-15 20:00:00",
                "activityType": {"typeKey": "running"},
                "locationName": "Taipei",
                "distance": 10000,
                "duration": 3000,
                "movingDuration": 2980,
                "averageSpeed": 3.33,
                "maxSpeed": 3.8,
                "averageHR": 145,
                "maxHR": 162,
                "calories": 650,
                "aerobicTrainingEffect": 3.2,
                "anaerobicTrainingEffect": 0.4,
                "startLatitude": 25.03,
                "startLongitude": 121.56,
            },
        ]
        laps = [{"distance": 1000, "duration": 300, "averageSpeed": 3.33, "averageHR": 144 + i} for i in range(4)]

        sent_texts = []
        sent_photos = []

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(main, "LOCAL_SAVE_DIR", tmpdir), \
             patch.object(main, "get_local_now", return_value=fake_now), \
             patch.object(utils, "get_local_now", return_value=fake_now), \
             patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen"]), \
             patch.object(main, "get_garmin_client", return_value=MagicMock()), \
             patch.object(main, "fetch_recent_activities", return_value=activities), \
             patch.object(main, "fetch_extended_activities", return_value=activities), \
             patch.object(main, "fetch_daily_recovery_metrics", return_value=None), \
             patch.object(main, "fetch_upcoming_races", return_value=[]), \
             patch.object(main, "get_today_weather_forecast", return_value=[{"label": "清晨 (06:00)", "temperature": 20, "weather_desc": "晴"}]), \
             patch.object(main, "fetch_activity_hr_zones", return_value=[{"zoneNumber": 2, "secsInZone": 2400}]), \
             patch.object(main, "get_open_meteo_weather", return_value={"temperature": 21, "humidity": 75, "apparent_temperature": 21, "wind_speed": 10, "weather_desc": "晴"}), \
             patch.object(main, "fetch_activity_splits", return_value=laps), \
             patch.object(main, "generate_coach_advice", return_value=(r"教練建議 $\rightarrow$ 執行 Zone 2", "models/gemini-4-hydrogen")), \
             patch.object(main, "send_telegram", side_effect=sent_texts.append), \
             patch.object(main, "send_telegram_photo", side_effect=lambda p, caption=None: sent_photos.append((p, caption))), \
             patch.object(main.time, "sleep"):
            main.run_main_task()

        self.assertEqual(len(sent_texts), 1)
        msg = sent_texts[0]
        self.assertIn("報告日期：2026-11-16 (週一) | 分析標的：昨日 2026-11-15 (週日)", msg)
        self.assertIn("昨日活動深度數據 (2026-11-15 (週日))", msg)
        self.assertIn("Taipei", msg)
        self.assertIn("昨日其他紀錄", msg)
        self.assertIn("跑量統計: 近7日 10.00 km (1 趟) | 近28日週均 2.50 km", msg)
        self.assertIn("L01: 1.00km |", msg)
        self.assertIn("前半程 vs 後半程配速:", msg)
        self.assertIn("今日訓練時段氣象預報 (2026-11-16 (週一))", msg)
        self.assertIn("風速 10km/h", msg)
        self.assertIn("教練建議 → 執行 Zone 2", msg)
        self.assertIn("(🤖 使用模型：gemini-4-hydrogen)", msg)
        chunks = notifier.split_telegram_text(msg)
        self.assertEqual(len(chunks), 2)
        self.assertIn("(🤖 使用模型：gemini-4-hydrogen)", chunks[1])
        self.assertEqual(len(sent_photos), 3)
        self.assertIn("昨日 2026-11-15", sent_photos[0][1])

    def test_run_main_task_rest_day(self):
        fake_now = datetime.datetime(2026, 11, 16, 4, 0, 0)
        activities = [
            {
                "activityId": 1,
                "startTimeLocal": "2026-11-14 18:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 10000,
                "duration": 3000,
            }
        ]
        sent_texts = []
        sent_photos = []

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(main, "LOCAL_SAVE_DIR", tmpdir), \
             patch.object(main, "get_local_now", return_value=fake_now), \
             patch.object(utils, "get_local_now", return_value=fake_now), \
             patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen", "models/gemini-2.5-flash"]), \
             patch.object(main, "get_garmin_client", return_value=MagicMock()), \
             patch.object(main, "fetch_recent_activities", return_value=activities), \
             patch.object(main, "fetch_extended_activities", return_value=activities), \
             patch.object(main, "fetch_daily_recovery_metrics", return_value=None), \
             patch.object(main, "fetch_upcoming_races", return_value=[]), \
             patch.object(main, "get_today_weather_forecast", return_value=None), \
             patch.object(main, "generate_rest_day_advice", return_value=("今日休整超補償", "models/gemini-2.5-flash")), \
             patch.object(main, "send_telegram", side_effect=sent_texts.append), \
             patch.object(main, "send_telegram_photo", side_effect=lambda p, caption=None: sent_photos.append((p, caption))), \
             patch.object(main.time, "sleep"):
            main.run_main_task()

        self.assertEqual(len(sent_texts), 1)
        self.assertIn("昨日休整與今日恢復日報", sent_texts[0])
        self.assertIn("報告日期：2026-11-16 (週一) | 分析標的：昨日 2026-11-15 (週日)", sent_texts[0])
        self.assertIn("今日休整超補償", sent_texts[0])
        self.assertIn("(🤖 使用模型：gemini-2.5-flash，由 gemini-4-hydrogen 容錯切換)", sent_texts[0])
        self.assertEqual(len(sent_photos), 1)

    def test_run_main_task_day_after_race_carries_yesterday_race_context(self):
        fake_now = datetime.datetime(2026, 11, 22, 4, 0, 0)
        activities = [
            {
                "activityId": 777,
                "activityName": "2026 Mother Marathon",
                "startTimeLocal": "2026-11-21 06:00:00",
                "activityType": {"typeKey": "running"},
                "locationName": "Beigang",
                "distance": 42195,
                "duration": 13500,
                "movingDuration": 13450,
                "averageSpeed": 3.12,
                "maxSpeed": 3.6,
                "averageHR": 162,
                "maxHR": 178,
                "calories": 2800,
                "aerobicTrainingEffect": 5.0,
                "anaerobicTrainingEffect": 0.8,
            }
        ]
        races = [
            {
                "id": 555,
                "title": "2026 Mother Marathon 北港媽祖盃全國馬拉松",
                "date": "2026-11-21",
                "days_left": -1,
                "distance_km": 42.2,
            },
            {
                "id": 556,
                "title": "2026 Taipei Marathon",
                "date": "2026-12-20",
                "days_left": 28,
                "distance_km": 42.2,
            },
        ]
        captured_prompts = []
        sent_texts = []

        def fake_coach(client, models, report_text):
            captured_prompts.append(report_text)
            return ("訓練型態判定：正式賽事（2026 Mother Marathon）", "models/gemini-4-hydrogen")

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(main, "LOCAL_SAVE_DIR", tmpdir), \
             patch.object(main, "get_local_now", return_value=fake_now), \
             patch.object(utils, "get_local_now", return_value=fake_now), \
             patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen"]), \
             patch.object(main, "get_garmin_client", return_value=MagicMock()), \
             patch.object(main, "fetch_recent_activities", return_value=activities), \
             patch.object(main, "fetch_extended_activities", return_value=activities), \
             patch.object(main, "fetch_daily_recovery_metrics", return_value=None), \
             patch.object(main, "fetch_upcoming_races", return_value=races) as mock_races, \
             patch.object(main, "get_today_weather_forecast", return_value=None), \
             patch.object(main, "fetch_activity_hr_zones", return_value=None), \
             patch.object(main, "get_open_meteo_weather", return_value=None), \
             patch.object(main, "fetch_activity_splits", return_value=[]), \
             patch.object(main, "generate_coach_advice", side_effect=fake_coach), \
             patch.object(main, "send_telegram", side_effect=sent_texts.append), \
             patch.object(main, "send_telegram_photo"), \
             patch.object(main.time, "sleep"):
            main.run_main_task()

        mock_races.assert_called_once_with(unittest.mock.ANY, months_ahead=3, days_back=7)
        self.assertEqual(len(captured_prompts), 1)
        report_sent_to_ai = captured_prompts[0]
        self.assertIn("[昨日主分析 | 正式賽事]", report_sent_to_ai)
        self.assertIn("🏁 賽事關聯: 昨日為 Garmin 排定目標賽事日 (Race Day) — 2026 Mother Marathon 北港媽祖盃全國馬拉松 (42.2km)", report_sent_to_ai)
        self.assertIn("🏷️ 名稱: 2026 Mother Marathon", report_sent_to_ai)
        self.assertIn("2026 Taipei Marathon", report_sent_to_ai)
        # 昨日已完賽賽事不應出現在「未來目標賽事」清單中
        upcoming_section = report_sent_to_ai.split("🏆 【未來目標賽事")[1].split("-" * 30)[0]
        self.assertNotIn("2026 Mother Marathon", upcoming_section)

    def test_run_main_task_post_race_rest_day_carries_recent_race_context(self):
        fake_now = datetime.datetime(2026, 11, 23, 4, 0, 0)
        activities = [
            {
                "activityId": 777,
                "startTimeLocal": "2026-11-21 06:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 42195,
                "duration": 13500,
            }
        ]
        races = [
            {
                "id": 555,
                "title": "2026 Mother Marathon 北港媽祖盃全國馬拉松",
                "date": "2026-11-21",
                "days_left": -2,
                "distance_km": 42.2,
            }
        ]
        captured_prompts = []

        def fake_rest_coach(client, models, report_text):
            captured_prompts.append(report_text)
            return ("建議今日持續休整恢復", "models/gemini-4-hydrogen")

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(main, "LOCAL_SAVE_DIR", tmpdir), \
             patch.object(main, "get_local_now", return_value=fake_now), \
             patch.object(utils, "get_local_now", return_value=fake_now), \
             patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen"]), \
             patch.object(main, "get_garmin_client", return_value=MagicMock()), \
             patch.object(main, "fetch_recent_activities", return_value=activities), \
             patch.object(main, "fetch_extended_activities", return_value=activities), \
             patch.object(main, "fetch_daily_recovery_metrics", return_value=None), \
             patch.object(main, "fetch_upcoming_races", return_value=races), \
             patch.object(main, "get_today_weather_forecast", return_value=None), \
             patch.object(main, "generate_rest_day_advice", side_effect=fake_rest_coach), \
             patch.object(main, "send_telegram"), \
             patch.object(main, "send_telegram_photo"), \
             patch.object(main.time, "sleep"):
            main.run_main_task()

        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("🏁 【近期剛完賽目標賽事 (近7日內，賽後恢復期參考)】", captured_prompts[0])
        self.assertIn("2 天前完賽", captured_prompts[0])
        self.assertIn("2026 Mother Marathon 北港媽祖盃全國馬拉松", captured_prompts[0])

    def test_run_main_task_uses_extended_activities_when_recent_window_is_crowded(self):
        fake_now = datetime.datetime(2026, 11, 16, 8, 0, 0)
        recent_only_today = [
            {"activityId": 99, "startTimeLocal": "2026-11-16 06:00:00", "activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1500}
        ]
        extended = recent_only_today + [
            {"activityId": 50, "startTimeLocal": "2026-11-15 17:00:00", "activityType": {"typeKey": "running"}, "distance": 12000, "duration": 3600}
        ]
        sent_texts = []

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(main, "LOCAL_SAVE_DIR", tmpdir), \
             patch.object(main, "get_local_now", return_value=fake_now), \
             patch.object(utils, "get_local_now", return_value=fake_now), \
             patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen"]), \
             patch.object(main, "get_garmin_client", return_value=MagicMock()), \
             patch.object(main, "fetch_recent_activities", return_value=recent_only_today), \
             patch.object(main, "fetch_extended_activities", return_value=extended), \
             patch.object(main, "fetch_daily_recovery_metrics", return_value=None), \
             patch.object(main, "fetch_upcoming_races", return_value=[]), \
             patch.object(main, "get_today_weather_forecast", return_value=None), \
             patch.object(main, "fetch_activity_hr_zones", return_value=None), \
             patch.object(main, "get_open_meteo_weather", return_value=None), \
             patch.object(main, "fetch_activity_splits", return_value=[]), \
             patch.object(main, "generate_coach_advice", return_value=("昨日 12km 表現良好", "models/gemini-4-hydrogen")), \
             patch.object(main, "send_telegram", side_effect=sent_texts.append), \
             patch.object(main, "send_telegram_photo"), \
             patch.object(main.time, "sleep"):
            main.run_main_task()

        self.assertEqual(len(sent_texts), 1)
        self.assertIn("12.00km", sent_texts[0])
        self.assertIn("昨日 12km 表現良好", sent_texts[0])

    def test_run_main_task_exits_nonzero_on_fatal_error(self):
        sent_texts = []
        with patch.object(main, "get_genai_client", return_value=MagicMock()), \
             patch.object(main, "detect_candidate_models", return_value=["models/gemini-4-hydrogen"]), \
             patch.object(main, "get_garmin_client", side_effect=RuntimeError("Auth failed")), \
             patch.object(main, "send_telegram", side_effect=sent_texts.append):
            with self.assertRaises(SystemExit) as ctx:
                main.run_main_task()

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(len(sent_texts), 1)
        self.assertIn("❌ Garmin 報表執行錯誤: Auth failed", sent_texts[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
