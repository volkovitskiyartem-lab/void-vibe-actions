"""Summarize a completed private forum snapshot using the PINNED private planner.

Private message records remain on the private runner checkout. The only output is
an aggregate JSON report committed to the PRIVATE audit-state branch.
No network, Telegram API operations, migrations, or message-level logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def aggregate(snapshot: dict, proposal: dict, policy: dict, status: dict,
              snapshot_sha256: str) -> dict:
    """Create aggregate-only evidence; NEVER include individual messages or IDs."""
    if snapshot.get("schema") != 2 or snapshot.get("complete_scan") is not True:
        raise ValueError("Complete schema-2 forum snapshot required")
    if policy.get("migration_prohibited") is not True:
        raise ValueError("This tool only runs while migration is prohibited")
    if status.get("complete") is not True or status.get("error") is not None:
        raise ValueError("Private scanner reports incomplete or failed")
    messages = snapshot["messages"]
    by_kind = Counter(m["kind"] for m in messages)
    audio_count = by_kind["audio"]
    if (status.get("audio") != audio_count or
            status.get("media_messages") != len(messages) or
            status.get("scanned", 0) < len(messages)):
        raise ValueError("Status and checkpoint do not agree")
    candidates = proposal["items"]
    blocked = proposal["blocked"]
    if len(candidates) + len(blocked) > audio_count:
        raise ValueError("Planner has more audio than the snapshot")
    root_ids = {int(v): k for k, v in policy["root_topic_ids"].items()}
    if len(root_ids) != 18:
        raise ValueError("Expected 18 consolidated roots")
    by_destination = Counter(str(item["target_topic"]) for item in candidates)
    if any(int(topic) not in root_ids for topic in by_destination):
        raise ValueError("Planner returned a non-root destination")
    blocked_reasons = Counter(item["reason"] for item in blocked)
    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_sha256": snapshot_sha256,
        "policy_digest": proposal["policy_digest"],
        "proposal_digest": proposal["digest"],
        "migration_prohibited": True,
        "scan": {
            "complete": True,
            "scanned": status["scanned"],
            "media_messages": len(messages),
            "audio": audio_count,
            "photo": by_kind["photo"],
            "image": by_kind["image"],
        },
        "classification": {
            "audio_already_in_place": audio_count - len(candidates) - len(blocked),
            "eligible_pairs_for_review": len(candidates),
            "blocked_pending_review": len(blocked),
            "blocked_reasons": dict(sorted(blocked_reasons.items())),
            "destination_by_topic_id": dict(sorted(by_destination.items(), key=lambda p: int(p[0]))),
            "destination_root_names": {str(i): n for i, n in sorted(root_ids.items())},
        },
        "confirmation": {
            "sent": 0,
            "deleted": 0,
            "plan_only": True,
            "source_audio_unchanged": True,
            "source_photo_unchanged": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-reader", type=Path, required=True)
    parser.add_argument("--private-state", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    # Imports are from an immutable reviewed SHA of the PRIVATE repository.
    sys.path.insert(0, str(args.private_reader.resolve()))
    from forum_topic_policy import load_policy
    from telegram_forum_checkpoint import complete_snapshot, private_summary
    from telegram_safe_migration import plan

    policy = load_policy(args.private_reader / "FORUM_COMPACT_ROUTING.json")
    if policy.get("migration_prohibited") is not True:
        raise SystemExit("Unsafe policy: migration must remain prohibited")

    checkpoint_path = args.private_state / "data/forum-audit/checkpoint.json"
    status_path = args.private_state / "data/forum-audit/status.json"
    raw = checkpoint_path.read_bytes()
    checkpoint = json.loads(raw)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    confirmed = private_summary(checkpoint)
    if any(confirmed.get(field) != status.get(field) for field in
           ("complete", "scanned", "audio", "photo", "image", "media_messages", "error", "blocked_until")):
        raise SystemExit("Aggregate status differs from private checkpoint")
    snapshot = complete_snapshot(checkpoint)
    proposal = plan(snapshot, policy)
    report = aggregate(snapshot, proposal, policy, status,
                       hashlib.sha256(raw).hexdigest())

    # Fail closed rather than silently overwriting a different, previously approved plan.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.exists():
        previous = json.loads(args.report.read_text(encoding="utf-8"))
        if (previous.get("snapshot_sha256") != report["snapshot_sha256"] or
                previous.get("proposal_digest") != report["proposal_digest"]):
            raise SystemExit("Existing report differs; independent review required")
        print("FORUM_READONLY_PLAN=reused_private_report")
        return
    with args.report.open("x", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")
    print("FORUM_READONLY_PLAN=private_report_written")
    print("FORUM_MIGRATION_PROHIBITED=true")


if __name__ == "__main__":
    main()
