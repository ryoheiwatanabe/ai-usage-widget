import copy
import unittest

from sync_usage import QuotaError, normalize_codex, retain_after_failure


class QuotaExportTests(unittest.TestCase):
    def test_duration_controls_slot_and_zero_credit_is_valid(self):
        weekly = {"usedPercent": 35, "windowDurationMins": 10080, "resetsAt": 1900000000}
        session = {"usedPercent": 18, "windowDurationMins": 300, "resetsAt": 1899500000}
        for primary, secondary, expected in [(weekly, None, {"weekly": 65}),
                                              (weekly, session, {"weekly": 65, "session": 82}),
                                              (session, weekly, {"session": 82, "weekly": 65})]:
            with self.subTest(primary_minutes=primary["windowDurationMins"], secondary=secondary is not None):
                result = normalize_codex({"rateLimits": {"primary": primary, "secondary": secondary,
                                                         "credits": {"balance": "0"}}}, "2026-11-02T17:00:00Z")
                self.assertEqual({w["id"]: w["remainingPercent"] for w in result["windows"]}, expected)
                self.assertEqual(result["credits"], "0")

    def test_failed_read_preserves_measurement_and_does_not_mutate_original(self):
        provider = {"id": "codex", "status": "connected", "measuredAt": "2026-11-02T17:00:00Z",
                    "windows": [{"id": "weekly", "remainingPercent": 65}], "credits": "0"}
        previous = {"providers": [provider]}
        before = copy.deepcopy(previous)
        result = retain_after_failure("codex", "取得できませんでした", previous)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["measuredAt"], provider["measuredAt"])
        self.assertEqual(result["windows"], provider["windows"])
        self.assertEqual(previous, before)

    def test_invalid_percent_is_rejected(self):
        for value in [-1, 101, float("nan"), True]:
            with self.subTest(value=value), self.assertRaises(QuotaError):
                normalize_codex({"rateLimits": {"primary": {"usedPercent": value,
                                 "windowDurationMins": 300, "resetsAt": 1900000000}}}, "2026-11-02T17:00:00Z")


if __name__ == "__main__":
    unittest.main()
