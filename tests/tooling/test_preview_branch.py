import tempfile
from pathlib import Path
import unittest

from scripts.preview_branch import preview_environment


class BranchPreviewIsolationTests(unittest.TestCase):
    def test_overrides_installation_environment_and_uses_ephemeral_key(self):
        with tempfile.TemporaryDirectory() as directory:
            inherited = {'TUXEDO_DATA_DIR': '/installation', 'TUXEDO_ENV_FILE': '/private/.env', 'DJANGO_SETTINGS_MODULE': 'installation.settings', 'SECRET_KEY': 'installation-secret', 'HTTPS': 'True', 'ALLOWED_HOSTS': '*', 'ALLOW_SIGNUPS': 'True'}
            env = preview_environment(directory, inherited)
            self.assertEqual(env['TUXEDO_DATA_DIR'], str(Path(directory).resolve()))
            self.assertEqual(env['TUXEDO_ENV_FILE'], '/dev/null')
            self.assertEqual(env['DJANGO_SETTINGS_MODULE'], 'core.settings')
            self.assertNotEqual(env['SECRET_KEY'], inherited['SECRET_KEY'])
            self.assertEqual(env['HTTPS'], 'False')
            self.assertEqual(env['ALLOW_SIGNUPS'], 'False')
            self.assertEqual(env['ALLOWED_HOSTS'], 'localhost,127.0.0.1')
            self.assertEqual(inherited['TUXEDO_DATA_DIR'], '/installation')
