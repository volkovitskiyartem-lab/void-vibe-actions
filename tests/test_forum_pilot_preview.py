"""Regression checks: read-only pilot selection is deterministic and constrained."""
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts/forum_pilot_preview.py"
spec = importlib.util.spec_from_file_location("pilot", PATH)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def sample():
    messages = []
    items = []
    for idx in range(15):
        cover = {"kind": "photo", "id": 1000+idx, "media_id": 3000+idx,
                 "caption": "cover", "entities": [], "size": 45}
        src = {"kind": "audio", "id": 2000+idx, "topic": 100+idx,
               "media_id": 4000+idx, "caption": "caption",
               "attributes": [], "size": 100, "filename": "track.flac",
               "entities": [], "reply": cover["id"]}
        messages.extend([cover, src])
        items.append({"source": src, "cover": cover, "target_topic": idx+1})
    snapshot = {"schema": 2, "complete_scan": True, "messages": messages}
    policy = {"migration_prohibited": True,
              "root_topic_ids": {"root"+str(i):i for i in range(1,19)}}
    proposal = {"digest": "digest-1", "policy_digest": "policy-1",
                "items": items, "blocked": []}
    baseline = {"migration_prohibited": True, "snapshot_sha256": "snap",
                "proposal_digest": "digest-1", "scan": {"audio": 15}}
    return snapshot, proposal, policy, baseline


class PreviewTests(unittest.TestCase):
    def test_exact_ten_stable_and_not_sent(self):
        args=sample()
        a=pilot.preview(*args)
        b=pilot.preview(*args)
        self.assertEqual(a, b)
        self.assertEqual(a["selected_count"], 10)
        self.assertEqual(len({x["target_topic_id"] for x in a["selected"]}), 10)
        self.assertEqual(a["sent"], 0)
        self.assertEqual(a["deleted"], 0)
        self.assertTrue(a["approval_required"])
        self.assertTrue(a["migration_prohibited"])

    def test_smaller_limit(self):
        self.assertEqual(pilot.preview(*sample(), limit=2)["selected_count"], 2)

    def test_fails_closed_policy_permit(self):
        args=sample()
        args[2]["migration_prohibited"] = False
        with self.assertRaises(ValueError):
            pilot.preview(*args)

    def test_fails_closed_incomplete(self):
        args=sample()
        args[0]["complete_scan"] = False
        with self.assertRaises(ValueError):
            pilot.preview(*args)

    def test_mismatched_digest(self):
        args=sample()
        args[3]["proposal_digest"] = "other"
        with self.assertRaises(ValueError):
            pilot.preview(*args)

    def test_shared_cover_excluded(self):
        args=sample()
        args[0]["messages"][3]["reply"] = args[0]["messages"][1]["reply"]
        # Make the explicit proposal reference the shared photo too.
        args[1]["items"][1]["cover"] = args[1]["items"][0]["cover"]
        out=pilot.preview(*args)
        self.assertFalse({2000,2001} & {x["source_message_id"] for x in out["selected"]})
        self.assertEqual(out["selected_count"], 10)
        self.assertGreater(out["blocked_shared_cover_count"], 0)

    def test_protected_or_already_in_place_not_sampled(self):
        args=sample()
        args[1]["items"][0]["target_topic"] = args[1]["items"][0]["source"]["topic"]
        args[1]["blocked"].append({"source_message_id": 2001})
        out=pilot.preview(*args)
        self.assertNotIn(2000, {x["source_message_id"] for x in out["selected"]})
        self.assertNotIn(2001, {x["source_message_id"] for x in out["selected"]})

    def test_snapshot_audio_mismatch(self):
        args=sample()
        args[3]["scan"]["audio"] = 14
        with self.assertRaises(ValueError):
            pilot.preview(*args)

    def test_invalid_limits(self):
        for bad in [0,11,True]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pilot.preview(*sample(), limit=bad)


if __name__ == "__main__":
    unittest.main()
