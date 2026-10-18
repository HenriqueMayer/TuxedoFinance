# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase, mock

from scripts import docker_smoke
from scripts.docker_smoke import Installation, isolated_environment


class DockerIsolationTests(TestCase):
    def test_parent_installation_and_compose_settings_are_discarded(self):
        private = {
            'SECRET_KEY': 'installation-key', 'TUXEDO_DATA_DIR': '/private-data',
            'TUXEDO_ENV_FILE': '/private-config', 'E2E_BASE_URL': 'http://personal-server',
            'COMPOSE_FILE': '/personal-compose.yaml', 'COMPOSE_PROJECT_NAME': 'personal',
            'DJANGO_SETTINGS_MODULE': 'private.settings', 'DEBUG': 'False', 'HTTPS': 'True', 'ALLOW_SIGNUPS': 'False',
        }
        with mock.patch.dict(os.environ, private):
            env = isolated_environment()
        for key in private:
            self.assertNotIn(key, env)

    def test_each_run_owns_a_distinct_compose_project(self):
        first, second = Installation('local:test'), Installation('local:test')
        self.assertNotEqual(first.project, second.project)
        self.assertTrue(first.project.startswith('tuxedo-test-'))

    def test_runtime_and_logs_stay_in_local_outputs_without_touching_legacy_files(self):
        with tempfile.TemporaryDirectory(prefix='tuxedo-docker-isolation-') as directory:
            root = Path(directory)
            (root / 'compose.yaml').write_text('services: {}\n')
            legacy = root / 'test-results/legacy.log'
            legacy.parent.mkdir()
            legacy.write_text('preserve existing log')
            with mock.patch.object(docker_smoke, 'ROOT', root), mock.patch.object(
                Installation, 'compose', return_value=subprocess.CompletedProcess([], 0, b'log', b''),
            ) as compose:
                with Installation('local:test') as app:
                    runtime = Path(app.directory.name)
                    self.assertEqual(runtime.parent, root / '.local/test-results/runtime')
                    self.assertEqual((runtime / '.env').stat().st_mode & 0o777, 0o600)
                self.assertFalse(runtime.exists())
                self.assertEqual((root / f'.local/test-results/{app.project}.log').read_bytes(), b'log')
                compose.assert_any_call('down', '--volumes', '--remove-orphans')
            self.assertEqual(legacy.read_text(), 'preserve existing log')
