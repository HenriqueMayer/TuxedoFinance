# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Benchmark startup must not inherit an installation's private configuration."""
import os
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scripts.benchmark_reporting import benchmark_environment, measure


class BenchmarkIsolationTests(TestCase):
    def test_synthetic_environment_replaces_installation_targets_and_key(self):
        with patch.dict(os.environ, {'TUXEDO_DATA_DIR': '/owner/data', 'TUXEDO_ENV_FILE': '/owner/private',
                                     'SECRET_KEY': 'owner-key', 'DJANGO_SETTINGS_MODULE': 'owner.settings',
                                     'COMPOSE_PROJECT_NAME': 'owner', 'E2E_BASE_URL': 'http://owner'}):
            first = benchmark_environment('/disposable')
            second = benchmark_environment('/disposable')
        self.assertEqual(first['TUXEDO_DATA_DIR'], '/disposable')
        self.assertEqual(first['TUXEDO_ENV_FILE'], '/disposable/.env')
        self.assertEqual(first['DJANGO_SETTINGS_MODULE'], 'core.settings')
        self.assertNotEqual(first['SECRET_KEY'], 'owner-key')
        self.assertNotEqual(first['SECRET_KEY'], second['SECRET_KEY'])
        self.assertEqual(first['ALLOWED_HOSTS'], 'testserver')
        self.assertNotIn('COMPOSE_PROJECT_NAME', first)
        self.assertNotIn('E2E_BASE_URL', first)

    def test_worker_refuses_an_already_configured_installation(self):
        configured = SimpleNamespace(settings=SimpleNamespace(configured=True))
        with patch.dict(sys.modules, {'django.conf': configured}):
            with self.assertRaisesRegex(RuntimeError, 'fresh process'):
                measure(0, 3)
