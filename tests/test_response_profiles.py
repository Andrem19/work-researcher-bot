import unittest

from work_researcher.server import _resolve_response_policy


class ResponseProfileTests(unittest.TestCase):
    def test_auto_profile_from_context(self):
        cases = [
            (55_040, "compact", 4, 8),
            (80_000, "compact", 4, 8),
            (128_000, "balanced", 12, 20),
            (299_999, "balanced", 12, 20),
            (300_000, "wide", 30, 50),
            (1_000_000, "wide", 30, 50),
        ]
        for context_window, profile, page_limit, max_limit in cases:
            with self.subTest(context_window=context_window):
                policy = _resolve_response_policy(context_window=context_window)
                self.assertEqual(policy["profile"], profile)
                self.assertEqual(policy["page_limit"], page_limit)
                self.assertEqual(policy["max_limit"], max_limit)
                self.assertEqual(policy["reason"], "context_window")

    def test_unknown_context_uses_balanced_default(self):
        policy = _resolve_response_policy()

        self.assertEqual(policy["profile"], "balanced")
        self.assertEqual(policy["page_limit"], 12)
        self.assertEqual(policy["reason"], "safe_default")

    def test_explicit_profile_enforces_its_cap(self):
        cases = [
            (100, "compact", 8),
            (100, "balanced", 20),
            (100, "wide", 50),
            (2, "wide", 2),
        ]
        for requested, profile, expected in cases:
            with self.subTest(profile=profile, requested=requested):
                policy = _resolve_response_policy(profile, limit=requested)
                self.assertEqual(policy["page_limit"], expected)

    def test_rejects_invalid_context_window(self):
        for bad_value in (0, -1):
            with self.subTest(value=bad_value):
                with self.assertRaisesRegex(ValueError, "context_window"):
                    _resolve_response_policy(context_window=bad_value)

    def test_rejects_invalid_limit(self):
        for bad_value in (0, -1):
            with self.subTest(value=bad_value):
                with self.assertRaisesRegex(ValueError, "limit"):
                    _resolve_response_policy(limit=bad_value)


if __name__ == "__main__":
    unittest.main()
