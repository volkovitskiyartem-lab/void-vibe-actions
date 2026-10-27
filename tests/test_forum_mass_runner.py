"""Guard the privileged boundary: PRs never receive private/TG credentials."""
from pathlib import Path
import re
import unittest
import yaml


class MassRunnerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parents[1]/'.github/workflows/forum-mass-copy.yml'
        self.doc = yaml.load(self.path.read_text(), Loader=yaml.BaseLoader)
        self.job = self.doc['jobs']['bounded_copy']

    def test_secrets_remain_main_only_and_live_apply_is_explicitly_opted_in(self):
        guard = self.job['if']
        for required in ("github.event_name != 'pull_request'", "github.ref == 'refs/heads/main'",
            "github.repository == 'volkovitskiyartem-lab/void-vibe-actions'",
            "vars.PUBLIC_RUNNER_ENABLED == 'true'", "vars.FORUM_MASS_ENABLED == 'true'",
            "vars.ROUTER_PAUSED != 'true'", "vars.MUSIC_TRANSFER_PAUSED != 'true'"):
            self.assertIn(required, guard)
        self.assertEqual(self.doc['permissions'], {'contents':'read'})
        self.assertEqual(self.doc['on']['workflow_dispatch']['inputs']['mode']['default'], 'preview')
        self.assertNotIn('push', self.doc['on'])

    def test_all_private_checkouts_and_inventory_are_pinned_and_state_never_bootstraps(self):
        steps = [s for s in self.job['steps'] if s.get('uses') == 'actions/checkout@v4']
        self.assertEqual(len(steps),3)
        for step in steps:
            self.assertEqual(step['with']['repository'],'volkovitskiyartem-lab/void-vibe-router')
            self.assertEqual(step['with']['persist-credentials'],'false')
        for step in steps[:2]:
            self.assertRegex(step['with']['ref'],r'^[0-9a-f]{40}$')
        self.assertEqual(steps[2]['with']['ref'],'router-state')
        text = self.path.read_text()
        self.assertNotIn('--force',text)
        self.assertNotIn('--orphan',text)
        self.assertNotIn('upload-artifact',text)

    def test_preview_has_no_telegram_secrets_and_apply_has_its_own_git_token(self):
        preview = next(s for s in self.job['steps'] if 'without Telegram' in s.get('name',''))
        self.assertNotIn('TG_SESSION',str(preview))
        apply = next(s for s in self.job['steps'] if s.get('name','').startswith('Apply bounded'))
        self.assertEqual(apply['if'],"env.RUN_MODE == 'apply' || env.RUN_MODE == 'reconcile_holds'")
        self.assertEqual(apply['env']['GH_TOKEN'],'${{ secrets.PRIVATE_REPO_TOKEN }}')
        self.assertIn('--approved-plan 58753025f57470190130a1469b4038d0fa77a78642788725e1edcc3633242149',apply['run'])

    def test_hold_recheck_is_manual_digest_bound_and_shell_input_is_only_environment(self):
        inputs=self.doc['on']['workflow_dispatch']['inputs']
        self.assertIn('reconcile_holds',inputs['mode']['options'])
        self.assertIn('hold_digest',inputs)
        apply=next(s for s in self.job['steps'] if s.get('name','').startswith('Apply bounded'))
        self.assertEqual(apply['env']['APPROVED_HOLDS'],'${{ inputs.hold_digest }}')
        self.assertIn('--approved-holds "$APPROVED_HOLDS"',apply['run'])
        self.assertNotIn('${{ inputs.hold_digest }}',apply['run'])
        self.assertIn('"$RUN_MODE"',apply['run'])

    def test_shared_job_lock_and_frequent_entry_cannot_dispatch_unbounded_chains(self):
        self.assertEqual(self.job['concurrency']['group'],'music-router')
        self.assertEqual(self.job['concurrency']['cancel-in-progress'],'false')
        self.assertEqual(self.doc['on']['schedule'],[{'cron':'9,24,39,54 * * * *'}])
        self.assertNotIn('gh workflow run',self.path.read_text())


if __name__ == '__main__':
    unittest.main()
