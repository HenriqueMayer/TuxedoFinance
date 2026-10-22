"""Settings security coverage for core."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from django.test import SimpleTestCase


class SettingsSecurityTests(SimpleTestCase):
    def test_secret_key_is_required_at_startup(self):
        environment = os.environ.copy()
        environment.pop('SECRET_KEY', None)
        environment['TUXEDO_ENV_FILE'] = '/path/that/does/not/exist/.env'
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY must be set in the environment.', result.stderr)

    def test_secret_key_can_be_loaded_from_env_file(self):
        environment = os.environ.copy()
        environment.pop('SECRET_KEY', None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / '.env'
            env_file.write_text('SECRET_KEY=local-file-secret\n', encoding='utf-8')
            environment['TUXEDO_ENV_FILE'] = str(env_file)
            result = subprocess.run(
                [sys.executable, 'manage.py', 'check'],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_process_secret_key_overrides_env_file(self):
        environment = os.environ.copy()
        environment['SECRET_KEY'] = 'process-secret'
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / '.env'
            env_file.write_text('SECRET_KEY=file-secret\n', encoding='utf-8')
            environment['TUXEDO_ENV_FILE'] = str(env_file)
            result = subprocess.run(
                [
                    sys.executable,
                    '-c',
                    'from django.conf import settings; print(settings.SECRET_KEY)',
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'process-secret')

    def test_tuxedo_data_dir_sets_database_location(self):
        environment = os.environ.copy()
        environment['SECRET_KEY'] = 'process-secret'
        environment['TUXEDO_ENV_FILE'] = '/path/that/does/not/exist/.env'
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment['TUXEDO_DATA_DIR'] = temporary_directory
            result = subprocess.run(
                [
                    sys.executable,
                    '-c',
                    (
                        'from django.conf import settings; '
                        'print(settings.DATABASES["default"]["NAME"])'
                    ),
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            Path(result.stdout.strip()),
            Path(temporary_directory) / 'db.sqlite3',
        )
