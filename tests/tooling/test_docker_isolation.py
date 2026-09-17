# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import os
from unittest import TestCase, mock

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
