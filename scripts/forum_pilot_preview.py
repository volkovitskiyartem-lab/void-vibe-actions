"""Immutable, PRIVATE-only, 10-pair read-only pilot preview. Never sends/deletes.

Samples from the reviewed migration proposal, not raw user genres. Excludes
shared artwork, ambiguous duplicates and protected topics. The preview is NOT
an authorization to copy messages; no Telegram connection is established.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def preview(snapshot, proposal, policy, baseline, *, limit=10):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Pilot sample must be 1..10")
    if baseline.get("migration_prohibited") is not True or policy.get("migration_prohibited") is not True:
        raise ValueError("Read-only operation requires migration_prohibited=true")
    if snapshot.get("schema") != 2 or snapshot.get("complete_scan") is not True:
        raise ValueError("Full immutable inventory required")
    if baseline.get("proposal_digest") != proposal.get("digest"):
        raise ValueError("Proposal fingerprint mismatch")
    if baseline.get("scan", {}).get("audio") != sum(x.get("kind") == "audio" for x in snapshot["messages"]):
        raise ValueError("Audio inventory mismatch")
    allowed = set(int(x) for x in policy["root_topic_ids"].values())
    blocked = {x["source_message_id"] for x in proposal["blocked"]}
    replies = Counter(x.get("reply") for x in snapshot["messages"] if x.get("kind") == "audio"
                      and x.get("reply"))
    cover_occurrences = Counter(x["cover"]["id"] for x in proposal["items"])
    used_media = set()
    candidates = []
    skips = Counter()
    for item in sorted(proposal["items"], key=lambda x: (x["target_topic"], x["source"]["id"])):
        source, cover = item["source"], item["cover"]
        target = item["target_topic"]
        if source["id"] in blocked or target not in allowed or target == source["topic"]:
            skips["not_eligible"] += 1
            continue
        if replies[cover["id"]] > 1 or cover_occurrences[cover["id"]] > 1:
            skips["shared_cover"] += 1
            continue
        if source["media_id"] == cover["media_id"]:
            skips["same_media"] += 1
            continue
        if (source["media_id"] in used_media or cover["media_id"] in used_media):
            skips["reused_media"] += 1
            continue
        if not isinstance(source.get("caption"), str) or not isinstance(cover.get("caption"), str):
            skips["missing_caption"] += 1
            continue
        candidates.append(item)

    # Favor distinct genre roots first, remaining places from stable order.
    selected = []
    roots_seen = set()
    for item in candidates:
        if item["target_topic"] not in roots_seen:
            selected.append(item)
            roots_seen.add(item["target_topic"])
            if len(selected) == limit:
                break
    if len(selected) < limit:
        for item in candidates:
            if item not in selected:
                selected.append(item)
                if len(selected) == limit:
                    break
    if not selected:
        raise ValueError("No independently covered pilot candidates")

    records = []
    for item in selected:
        src, cover = item["source"], item["cover"]
        records.append({
            "source_message_id": src["id"], "source_topic_id": src["topic"],
            "target_topic_id": item["target_topic"],
            "cover_message_id": cover["id"],
            "source_media_id": src["media_id"], "cover_media_id": cover["media_id"],
            "audio_metadata_sha256": digest({
                "caption": src["caption"], "attributes": src["attributes"],
                "size": src["size"], "filename": src["filename"], "entities": src["entities"]}),
            "cover_metadata_sha256": digest({
                "caption": cover["caption"], "size": cover["size"], "entities": cover["entities"]}),
        })
    base = {
        "schema": 1,
        "pilot_limit": limit,
        "selected_count": len(records),
        "baseline_snapshot_sha256": baseline["snapshot_sha256"],
        "baseline_proposal_digest": proposal["digest"],
        "policy_digest": proposal["policy_digest"],
        "selected": records,
    }
    base["pilot_digest"] = digest(base)
    base["approval_required"] = True
    base["migration_prohibited"] = True
    base["sent"] = 0
    base["deleted"] = 0
    base["blocked_shared_cover_count"] = skips["shared_cover"]
    return base


def main():
    import argparse
    import sys
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-reader", required=True, type=Path)
    parser.add_argument("--private-state", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.private_reader.resolve()))
    from forum_topic_policy import load_policy
    from telegram_forum_checkpoint import complete_snapshot, private_summary
    from telegram_safe_migration import plan
    state_dir = args.private_state / "data/forum-audit"
    checkpoint = json.loads((state_dir / "checkpoint.json").read_text(encoding="utf-8"))
    status = json.loads((state_dir / "status.json").read_text(encoding="utf-8"))
    check = private_summary(checkpoint)
    if any(status.get(x) != check.get(x) for x in ("complete", "error", "scanned", "audio", "photo", "media_messages")):
        raise SystemExit("Private status differs from checkpoint")
    if check["complete"] is not True or check["error"] is not None:
        raise SystemExit("Incomplete snapshot")
    baseline = json.loads((state_dir / "compact-routing-plan-summary.json").read_text(encoding="utf-8"))
    raw = (state_dir / "checkpoint.json").read_bytes()
    if baseline["snapshot_sha256"] != hashlib.sha256(raw).hexdigest():
        raise SystemExit("Baseline snapshot checksum differs")
    policy = load_policy(args.private_reader / "FORUM_COMPACT_ROUTING.json")
    snapshot = complete_snapshot(checkpoint)
    proposal = plan(snapshot, policy)
    result = preview(snapshot, proposal, policy, baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("pilot_digest") != result["pilot_digest"]:
            raise SystemExit("Existing private pilot differs: do not overwrite")
        print("PRIVATE_PILOT_PREVIEW=already_persisted")
        return
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    # No private message IDs, media content or hashes in public Actions logs.
    print("PRIVATE_PILOT_PREVIEW=created; needs exact approval before copy")
    print("PRIVATE_PILOT_PAIRS=" + str(result["selected_count"]))
    print("TELEGRAM_SENT=0; DELETED=0")


if __name__ == "__main__":
    main()
