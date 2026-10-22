import tempfile
import argparse
from pathlib import Path
import unittest

from scripts.preview_branch import preview_environment, private_preview_host


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

    def test_private_lan_is_explicit_and_has_exact_allowed_host(self):
        with tempfile.TemporaryDirectory() as directory:
            env = preview_environment(directory, {'ALLOWED_HOSTS': '*'}, bind_host='192.168.1.25')
            self.assertEqual(env['ALLOWED_HOSTS'], 'localhost,127.0.0.1,192.168.1.25')
            self.assertEqual(env['ALLOW_SIGNUPS'], 'False')
            self.assertEqual(env['TUXEDO_ENV_FILE'], '/dev/null')
        for address in ['localhost', '127.0.0.1', '127.0.0.2', '10.1.2.3', '172.16.0.2', '192.168.1.25']:
            self.assertEqual(private_preview_host(address), address)

    def test_wildcards_public_addresses_and_hostnames_are_rejected(self):
        for address in ['0.0.0.0', '8.8.8.8', '169.254.1.2', '172.15.0.2', '::', '::1', '*', 'example.com', '192.168.1.2:8766']:
            with self.subTest(address=address), self.assertRaises(argparse.ArgumentTypeError):
                private_preview_host(address)
