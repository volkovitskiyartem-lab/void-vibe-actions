"""Static production contract checks; never dispatches a workflow."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompactWorkflowTests(unittest.TestCase):
    def test_both_music_publishers_explicitly_enable_compact_routing(self):
        for filename in ('music.yml', 'fresh-bulk.yml'):
            with self.subTest(filename=filename):
                source = (ROOT / '.github/workflows' / filename).read_text()
                self.assertRegex(source, r"    env:\n      FORUM_COMPACT_ROUTING: 'true'")
                self.assertIn("vars.MUSIC_TRANSFER_PAUSED != 'true'", source)
                self.assertIn('group: music-router', source)
                self.assertIn("FORUM_COMPACT_ROUTING: 'false'", source)

    def test_refresh_pins_private_code_and_preserves_the_pilot_baseline(self):
        source = (ROOT / '.github/workflows/forum-incremental-refresh.yml').read_text()
        self.assertRegex(source, r'ref: [0-9a-f]{40}\n')
        self.assertIn('ref: state/telegram-forum-inventory', source)
        self.assertIn('data/forum-refresh/checkpoint.json', source)
        self.assertIn('git add -- data/forum-refresh', source)
        self.assertIn('--refresh --limit 300', source)
        self.assertIn('for page in 1 2 3 4 5', source)
        self.assertNotIn('upload-artifact', source)
        self.assertNotIn('telegram_pilot_apply.py', source)


if __name__ == '__main__':
    unittest.main()
