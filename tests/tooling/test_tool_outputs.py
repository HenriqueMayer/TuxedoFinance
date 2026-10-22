"""Check local tool destinations without creating application data.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ToolOutputTests(unittest.TestCase):
    def test_coverage_creates_missing_output_parent_and_all_reports_locally(self):
        with tempfile.TemporaryDirectory(prefix='tuxedo-coverage-output-') as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / 'pyproject.toml', root / 'pyproject.toml')
            (root / 'sample.py').write_text('value = 1\n')
            self.assertFalse((root / '.local').exists())
            for arguments in (['run', 'sample.py'], ['xml'], ['html']):
                result = subprocess.run(
                    [sys.executable, '-m', 'coverage', *arguments], cwd=root,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
            for path in ('.local/coverage/.coverage', '.local/coverage/coverage.xml',
                         '.local/coverage/html/index.html'):
                self.assertTrue((root / path).is_file(), path)
            for legacy in ('.coverage', 'coverage.xml', 'htmlcov'):
                self.assertFalse((root / legacy).exists(), legacy)

    def test_ruff_cache_is_configured_in_local_directory(self):
        config = tomllib.loads((ROOT / 'pyproject.toml').read_text())
        self.assertEqual(config['tool']['ruff']['cache-dir'], '.local/cache/ruff')

    @unittest.skipUnless(shutil.which('node') and (ROOT / 'node_modules/@playwright/test').is_dir(),
                         'Playwright development dependencies are needed to load its configuration')
    def test_playwright_paths_are_absolute_even_from_another_working_directory(self):
        code = '''
const config = require(process.argv[1]);
console.log(JSON.stringify({testDir: config.testDir, outputDir: config.outputDir,
    reportDir: config.reporter.find(item => item[0] === 'html')[1].outputFolder}));
'''
        with tempfile.TemporaryDirectory(prefix='tuxedo-playwright-config-') as directory:
            import os
            result = subprocess.run(
                ['node', '-e', code, str(ROOT / 'tests/playwright.config.js')], cwd=directory,
                env=dict(os.environ, CI='1'), check=True, capture_output=True, text=True,
            )
        paths = json.loads(result.stdout)
        self.assertEqual(paths, {
            'testDir': str(ROOT / 'tests/e2e'),
            'outputDir': str(ROOT / '.local/test-results/browser'),
            'reportDir': str(ROOT / '.local/playwright-report'),
        })
        self.assertNotEqual(Path(paths['outputDir']), ROOT / '.local/test-results/runtime')
