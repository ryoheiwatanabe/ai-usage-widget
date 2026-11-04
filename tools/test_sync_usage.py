import copy
import unittest

from sync_usage import QuotaError, normalize_codex, retain_after_failure, preserve_unavailable, TerminalScreen, parse_claude_usage, claude_reset_time


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

    def test_disconnected_or_missing_window_keeps_original_sample(self):
        old = {"id": "claude", "status": "connected", "measuredAt": "2026-11-02T17:00:00Z",
               "windows": [{"id": "session", "remainingPercent": 65},
                           {"id": "weekly", "remainingPercent": 80}], "credits": None}
        for current in [{"id": "claude", "status": "disconnected", "windows": []},
                        {**old, "measuredAt": "2026-11-04T11:00:00Z", "windows": old["windows"][:1]}]:
            with self.subTest(status=current["status"]):
                result = preserve_unavailable(current, {"providers": [old]})
                self.assertEqual(result["status"], "stale")
                self.assertEqual(result["windows"], old["windows"])
                self.assertEqual(result["measuredAt"], old["measuredAt"])

    def test_cursor_updates_replace_previous_usage_and_split_sequences(self):
        screen = TerminalScreen()
        screen.feed('\x1b[2J\x1b[1;1HCurrent session\x1b[2;1H94% used\x1b[3;1HCurrent week (all models)\x1b[4;1H12% used')
        screen.feed('\x1b[2;1')
        screen.feed('H96% used\x1b[4;1H13% used')
        result = parse_claude_usage(screen.text(), '2026-11-04T00:00:00Z')
        self.assertEqual({w['id']: w['remainingPercent'] for w in result['windows']}, {'session': 4, 'weekly': 87})

    def test_claude_reset_date_uses_explicit_timezone_and_rollover(self):
        self.assertEqual(claude_reset_time('12am (Asia/Tokyo)', '2026-11-04T11:00:00Z'), '2026-11-04T15:00:00Z')
        self.assertEqual(claude_reset_time('Jan 2 at 4pm (Asia/Tokyo)', '2026-12-31T11:00:00Z'), '2027-01-02T07:00:00Z')
        self.assertIsNone(claude_reset_time('unknown', '2026-11-04T11:00:00Z'))

    def test_expired_reset_does_not_jump_to_next_year_or_day(self):
        measured = '2026-11-04T08:00:00Z'  # 17:00 JST
        self.assertEqual(claude_reset_time('Nov 4 at 4pm (Asia/Tokyo)', measured), '2026-11-04T07:00:00Z')
        self.assertEqual(claude_reset_time('4pm (Asia/Tokyo)', measured), '2026-11-04T07:00:00Z')

    def test_terminal_erase_display_removes_old_quotas(self):
        for erase in ['\x1b[J', '\x1b[0J', '\x1b[1J']:
            screen = TerminalScreen()
            screen.feed('Current session\x1b[2;1H80% used')
            screen.feed(('\x1b[2;160H' if erase.endswith('1J') else '\x1b[H') + erase)
            with self.subTest(erase=erase), self.assertRaises(QuotaError):
                parse_claude_usage(screen.text(), '2026-11-04T00:00:00Z')

    def test_invalid_percent_is_rejected(self):
        for value in [-1, 101, float("nan"), True]:
            with self.subTest(value=value), self.assertRaises(QuotaError):
                normalize_codex({"rateLimits": {"primary": {"usedPercent": value,
                                 "windowDurationMins": 300, "resetsAt": 1900000000}}}, "2026-11-02T17:00:00Z")


if __name__ == "__main__":
    unittest.main()
