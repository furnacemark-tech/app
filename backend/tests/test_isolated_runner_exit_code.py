import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.run_isolated_backend_tests import runner_exit_code


class RunnerExitCodeTests(unittest.TestCase):
    def test_preserves_pytest_failure(self):
        self.assertEqual(runner_exit_code(2, True, True), 2)

    def test_fails_when_preview_counts_change(self):
        self.assertEqual(runner_exit_code(0, False, True), 1)

    def test_fails_when_disposable_database_remains(self):
        self.assertEqual(runner_exit_code(0, True, False), 1)

    def test_succeeds_only_when_every_check_passes(self):
        self.assertEqual(runner_exit_code(0, True, True), 0)


if __name__ == "__main__":
    unittest.main()
