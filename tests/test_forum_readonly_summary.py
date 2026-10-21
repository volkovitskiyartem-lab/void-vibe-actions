"""Offline, secret-free tests for aggregate-only 18-topic planning."""
import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/forum_readonly_summary.py"
spec = importlib.util.spec_from_file_location("forum_readonly_summary", SCRIPT)
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def sample():
    snapshot = {
        "schema": 2, "complete_scan": True,
        "messages": [
            {"kind": "photo", "id": 1},
            {"kind": "audio", "id": 2},
            {"kind": "audio", "id": 3},
            {"kind": "audio", "id": 4},
            {"kind": "audio", "id": 5},
        ],
    }
    roots = {"root" + str(i): i for i in range(1, 19)}
    policy = {"migration_prohibited": True, "root_topic_ids": roots}
    proposal = {
        "policy_digest": "example-policy-digest",
        "digest": "example-plan-digest",
        "items": [{"target_topic": 1}, {"target_topic": 2}],
        "blocked": [{"reason": "cover_association_unverified", "source_message_id": 4}],
    }
    status = {
        "complete": True, "error": None, "scanned": 6,
        "audio": 4, "media_messages": 5,
    }
    return snapshot, proposal, policy, status


class ForumSummaryTests(unittest.TestCase):
    def test_complete_report_is_aggregate_only(self):
        snap, plan, policy, status = sample()
        result = reporter.aggregate(snap, plan, policy, status, "abc123")
        self.assertEqual(result["scan"]["audio"], 4)
        self.assertEqual(result["classification"]["audio_already_in_place"], 1)
        self.assertEqual(result["classification"]["eligible_pairs_for_review"], 2)
        self.assertEqual(result["classification"]["blocked_pending_review"], 1)
        self.assertEqual(result["classification"]["blocked_reasons"],
                         {"cover_association_unverified": 1})
        self.assertEqual(result["classification"]["destination_by_topic_id"],
                         {"1": 1, "2": 1})
        self.assertEqual(result["confirmation"]["sent"], 0)
        self.assertEqual(result["confirmation"]["deleted"], 0)
        encoded = json.dumps(result)
        self.assertNotIn("source_message_id", encoded)
        self.assertNotIn("messages", result)

    def test_fails_closed_incomplete_snapshot(self):
        args = sample()
        args[0]["complete_scan"] = False
        with self.assertRaises(ValueError):
            reporter.aggregate(*args, snapshot_sha256="abc")

    def test_fails_closed_on_disabled_migration_prohibition(self):
        snap, plan, policy, status = sample()
        policy["migration_prohibited"] = False
        with self.assertRaises(ValueError):
            reporter.aggregate(snap, plan, policy, status, "abc")

    def test_status_mismatch_fails_closed(self):
        snap, plan, policy, status = sample()
        status["audio"] = 500
        with self.assertRaises(ValueError):
            reporter.aggregate(snap, plan, policy, status, "abc")

    def test_bad_target_topic_fails_closed(self):
        snap, plan, policy, status = sample()
        plan["items"][0]["target_topic"] = 99999
        with self.assertRaises(ValueError):
            reporter.aggregate(snap, plan, policy, status, "abc")

    def test_incorrect_audio_accounting_fails_closed(self):
        snap, plan, policy, status = sample()
        plan["blocked"].extend([{"reason": "x"}] * 3)
        with self.assertRaises(ValueError):
            reporter.aggregate(snap, plan, policy, status, "abc")

    def test_requires_18_distinct_roots(self):
        snap, plan, policy, status = sample()
        policy["root_topic_ids"]["root18"] = 1
        with self.assertRaises(ValueError):
            reporter.aggregate(snap, plan, policy, status, "abc")


if __name__ == "__main__":
    unittest.main()
