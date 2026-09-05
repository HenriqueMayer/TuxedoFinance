"""Verify that either README can block an inconsistent release.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_version


class VersionTests(unittest.TestCase):
    def test_each_readme_must_have_matching_visible_and_accessible_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('pyproject.toml', 'uv.lock', 'CHANGELOG.md', 'README.md', 'README.pt-BR.md'):
                (root / name).write_bytes((check_version.ROOT / name).read_bytes())
            version = check_version.read_toml(root / 'pyproject.toml')['project']['version']
            for name in ('README.md', 'README.pt-BR.md'):
                original = (root / name).read_text()
                for old, new in (
                    (f'badge/version-{version}-', 'badge/version-999.999.999-'),
                    (f' {version}"', ' 999.999.999"'),
                ):
                    with self.subTest(readme=name, mutation=old):
                        (root / name).write_text(original.replace(old, new))
                        with patch.object(check_version, 'ROOT', root), redirect_stderr(StringIO()):
                            with self.assertRaises(SystemExit) as error:
                                check_version.main()
                        self.assertEqual(error.exception.code, 1)
                        (root / name).write_text(original)

    def test_missing_or_duplicate_badge_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            for contents in ('# No badge', '<img src="https://img.shields.io/badge/version-0.2.0-blue" alt="Version 0.2.0">' * 2):
                with self.subTest(contents=contents):
                    path.write_text(contents)
                    with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                        check_version.check_readme(path, '0.2.0', 'Version')
