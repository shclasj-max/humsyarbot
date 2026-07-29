import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/test")

from api.routers import dashboard, profile  # noqa: E402
from api.user_metrics import normalize_stats, normalize_weekly  # noqa: E402


class MetricsTests(unittest.TestCase):
    def test_normalize_stats_handles_malformed_values(self):
        result = normalize_stats(
            {
                "total_answers": "4",
                "correct_answers": "3",
                "downloads": None,
                "week_activity": -5,
                "percentage": float("nan"),
                "weak_topics": [" قلب ", None, "قلب", ""],
            }
        )
        self.assertEqual(result["total_answers"], 4)
        self.assertEqual(result["correct_answers"], 3)
        self.assertEqual(result["percentage"], 75)
        self.assertEqual(result["downloads"], 0)
        self.assertEqual(result["week_activity"], 0)
        self.assertEqual(result["weak_topics"], ["قلب"])
        self.assertEqual(result["level"]["key"], "advanced")

    def test_normalize_weekly_skips_invalid_rows(self):
        result = normalize_weekly([("07/01", "2"), None, {"date": "07/02", "count": -1}])
        self.assertEqual(
            result,
            [
                {"date": "07/01", "count": 2},
                {"date": "07/02", "count": 0},
            ],
        )


class DashboardEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_returns_stable_defaults(self):
        user = {
            "id": 123,
            "_db": {"name": "دانشجو", "group": "1", "role": "student"},
        }
        with (
            patch.object(dashboard.db, "user_stats", AsyncMock(return_value=None)),
            patch.object(dashboard.db, "upcoming_exams", AsyncMock(return_value=None)) as exams,
            patch.object(dashboard.db, "ticket_get_user", AsyncMock(return_value=None)),
        ):
            result = await dashboard.get_dashboard(user)

        exams.assert_awaited_once_with(7, group="1")
        self.assertEqual(result["stats"]["percentage"], 0)
        self.assertEqual(result["stats"]["weak_topics"], [])
        self.assertEqual(result["upcoming_exams"], [])
        self.assertEqual(result["open_tickets"], 0)

    async def test_leaderboard_normalizes_legacy_values(self):
        leaders = [
            {
                "user_id": "123",
                "name": "کاربر",
                "correct_answers": "8",
                "total_answers": "10",
            },
            None,
        ]
        with patch.object(
            dashboard.db, "get_leaderboard", AsyncMock(return_value=leaders)
        ):
            result = await dashboard.leaderboard({"id": 123})

        self.assertEqual(len(result["leaderboard"]), 1)
        self.assertEqual(result["leaderboard"][0]["percent"], 80)
        self.assertTrue(result["leaderboard"][0]["is_me"])


class ProfileEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_handles_missing_collections(self):
        user = {"id": 456, "_db": {"name": "کاربر", "role": "unknown"}}
        with (
            patch.object(profile.db, "user_stats", AsyncMock(return_value={})),
            patch.object(profile.db, "weekly_activity", AsyncMock(return_value=None)),
            patch.object(profile.db, "ticket_get_user", AsyncMock(return_value=None)),
        ):
            result = await profile.get_profile(user)

        self.assertEqual(result["user"]["role"], "student")
        self.assertEqual(result["stats"]["weekly_chart"], [])
        self.assertEqual(result["tickets"], {"open": 0, "closed": 0})

    async def test_name_update_normalizes_spaces(self):
        update = AsyncMock()
        with patch.object(profile.db, "update_user", update):
            result = await profile.update_name(
                profile.NameUpdate(name="  علی   احمدی  "),
                {"id": 789},
            )

        update.assert_awaited_once_with(789, {"name": "علی احمدی"})
        self.assertEqual(result["name"], "علی احمدی")

    async def test_download_badge_uses_calculated_stats(self):
        with patch.object(
            profile.db,
            "user_stats",
            AsyncMock(
                return_value={
                    "total_answers": 1,
                    "correct_answers": 1,
                    "downloads": 10,
                }
            ),
        ):
            result = await profile.get_badges({"id": 123, "_db": {}})

        badges = {item["id"]: item["earned"] for item in result["badges"]}
        self.assertTrue(badges["first"])
        self.assertTrue(badges["downloader"])


if __name__ == "__main__":
    unittest.main()
