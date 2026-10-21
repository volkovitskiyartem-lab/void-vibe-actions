"""Offline regression tests for the public read-only forum inventory gate.

These tests execute the *actual* inline Python guard with synthetic aggregate
state and synthetic GitHub API responses. No Telegram or GitHub API is called.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/forum-readonly-count.yml"


def guard_source():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = "      - name: Guard inventory against recent progress and concurrent runs"
    start = lines.index(marker)
    shell = next(i for i in range(start, len(lines))
                 if lines[i] == "          python - <<'PY'")
    finish = next(i for i in range(shell + 1, len(lines))
                  if lines[i] == "          PY")
    body = [line[10:] for line in lines[shell + 1:finish]]
    source = "\n".join(body) + "\n"
    compile(source, str(WORKFLOW) + ":guard", "exec")
    return source


class ReadOnlyGateTests(unittest.TestCase):
    def run_gate(self, *, minutes_old=45, event="workflow_run", complete=False,
                 error=None, blocked_until=None, scanned=15000, runs=None,
                 timestamp=None, jobs_by_run=None):
        now = datetime.now(timezone.utc)
        timestamp = timestamp or (now - timedelta(minutes=minutes_old)).isoformat()
        state = {
            "schema": 1,
            "complete": complete,
            "error": error,
            "blocked_until": blocked_until,
            "updated_at": timestamp,
            "scanned": scanned,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "audit-state/data/forum-audit/status.json"
            status.parent.mkdir(parents=True)
            status.write_text(json.dumps(state), encoding="utf-8")
            fake_gh = root / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "url = sys.argv[-1]\n"
                "if '/actions/runs/' in url and '/jobs?' in url:\n"
                "    run_id = url.split('/actions/runs/')[1].split('/')[0]\n"
                "    jobs = json.loads(os.environ['MOCK_JOBS_BY_RUN']).get(run_id, [])\n"
                "    sys.stdout.write(json.dumps({'jobs': jobs}))\n"
                "else:\n"
                "    sys.stdout.write(os.environ['MOCK_GH_RESPONSE'])\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o700)
            env = os.environ.copy()
            env.update({
                "PATH": str(root) + os.pathsep + env.get("PATH", ""),
                "RUN_ID": "100",
                "EVENT_NAME": event,
                "GITHUB_OUTPUT": str(root / "outputs"),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
                "MOCK_GH_RESPONSE": json.dumps({"workflow_runs": runs or []}),
                "MOCK_JOBS_BY_RUN": json.dumps(jobs_by_run or {}),
            })
            p = subprocess.run(
                [sys.executable, "-c", guard_source()],
                cwd=root, env=env, capture_output=True, text=True,
                timeout=12,
            )
            output = (root / "outputs").read_text() if (root / "outputs").exists() else ""
            return p, output

    def test_recent_real_checkpoint_skips(self):
        p, out = self.run_gate(minutes_old=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("FORUM_FALLBACK=recent_checkpoint", p.stdout)
        self.assertIn("scan=false", out)

    def test_stale_checkpoint_scans_even_with_recent_green_noop(self):
        recent_green = {
            "id": 101,
            "status": "completed",
            "conclusion": "success",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        }
        p, out = self.run_gate(minutes_old=45, runs=[recent_green])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("FORUM_FALLBACK=eligible", p.stdout)
        self.assertIn("scan=true", out)

    def test_active_other_inventory_skips(self):
        p, out = self.run_gate(minutes_old=45, runs=[
            {"id": 102, "status": "in_progress", "conclusion": None}
        ])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=false", out)
        self.assertIn("other_inventory_active", p.stdout)

    def test_own_run_is_not_a_duplicate(self):
        p, out = self.run_gate(minutes_old=45, runs=[
            {"id": 100, "status": "in_progress", "conclusion": None}
        ])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=true", out)

    def test_prior_failure_since_checkpoint_fails_closed(self):
        failed = {
            "id": 102,
            "status": "completed",
            "conclusion": "failure",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }
        p, out = self.run_gate(minutes_old=45, runs=[failed], jobs_by_run={
            "102": [{"name": "checkpoint", "steps": [
                {"name": "Scan in five bounded pages and durably checkpoint each page",
                 "status": "completed", "conclusion": "failure"}]}],
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_cancelled_pre_job_does_not_poison_checkpoint(self):
        cancelled = {"id": 103, "status": "completed", "conclusion": "cancelled",
                     "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=50, runs=[cancelled],
                               jobs_by_run={"103": []})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=true", out)

    def test_failed_guard_with_skipped_scan_is_safe_to_retry(self):
        failed = {"id": 104, "status": "completed", "conclusion": "failure",
                  "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=50, runs=[failed], jobs_by_run={
            "104": [{"name": "checkpoint", "steps": [
                {"name": "Stop after completion or during Telegram cooldown",
                 "status": "completed", "conclusion": "success"},
                {"name": "Guard inventory against recent progress and concurrent runs",
                 "status": "completed", "conclusion": "failure"},
                {"name": "Scan in five bounded pages and durably checkpoint each page",
                 "status": "completed", "conclusion": "skipped"}]}],
        })
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=true", out)

    def test_cancellation_during_scan_stays_blocked(self):
        cancelled = {"id": 105, "status": "completed", "conclusion": "cancelled",
                     "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=45, runs=[cancelled], jobs_by_run={
            "105": [{"name": "checkpoint", "steps": [
                {"name": "Scan in five bounded pages and durably checkpoint each page",
                 "status": "completed", "conclusion": "cancelled"}]}],
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_failed_run_without_jobs_is_ambiguous_and_blocks(self):
        failed = {"id": 106, "status": "completed", "conclusion": "failure",
                  "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=45, runs=[failed],
                               jobs_by_run={"106": []})
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_cancelled_after_successful_scan_uses_private_checkpoint(self):
        cancelled = {"id": 107, "status": "completed", "conclusion": "cancelled",
                     "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=45, runs=[cancelled], jobs_by_run={
            "107": [{"name": "checkpoint", "steps": [
                {"name": "Scan in five bounded pages and durably checkpoint each page",
                 "status": "completed", "conclusion": "success"}]}],
        })
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=true", out)

    def test_unknown_scan_state_fails_closed(self):
        bad = {"id": 108, "status": "completed", "conclusion": "timed_out",
               "created_at": datetime.now(timezone.utc).isoformat()}
        p, out = self.run_gate(minutes_old=45, runs=[bad], jobs_by_run={
            "108": [{"name": "checkpoint", "steps": [
                {"name": "Scan in five bounded pages and durably checkpoint each page",
                 "status": "completed", "conclusion": None}]}],
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_telegram_cooldown_blocks(self):
        until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        p, out = self.run_gate(minutes_old=45, blocked_until=until)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("telegram_cooldown", p.stdout)
        self.assertIn("scan=false", out)

    def test_complete_prevents_scan(self):
        p, out = self.run_gate(minutes_old=90, complete=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=false", out)

    def test_error_fails_closed(self):
        p, out = self.run_gate(minutes_old=90, error="UnknownFailure")
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_future_checkpoint_fails_closed(self):
        timestamp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        p, out = self.run_gate(timestamp=timestamp)
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("scan=true", out)

    def test_manual_request_bypasses_freshness_but_not_active_run(self):
        p, out = self.run_gate(minutes_old=1, event="workflow_dispatch")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scan=true", out)
        p2, out2 = self.run_gate(minutes_old=1, event="workflow_dispatch", runs=[
            {"id": 222, "status": "queued"}
        ])
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertIn("scan=false", out2)

    def test_static_safety_boundaries(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cron: '12 * * * *'", text)
        self.assertIn("group: void-vibe-music-transfer", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("ref: 6e374dfaf249197921fdc77f5015a07e113d0c36", text)
        self.assertIn("ref: state/telegram-forum-inventory", text)
        self.assertIn("for page in 1 2 3 4 5", text)
        self.assertIn("--limit 300", text)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", text)
        self.assertNotIn("timedelta(minutes=75)", text)
        self.assertNotIn("timedelta(minutes=65)", text)
        self.assertNotIn("send_message(", text)
        self.assertNotIn("delete_messages(", text)


if __name__ == "__main__":
    unittest.main()
