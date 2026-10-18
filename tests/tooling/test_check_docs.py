"""Documentation moves must retain local destinations and legacy anchors.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import check_docs


class DocumentationLinkTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='tuxedo-doc-links-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def test_relative_links_encoded_paths_and_html_assets_resolve(self):
        self.write('docs/Forms guide.md', '# Forms\n\n## Keyboard & choices\n')
        self.write('assets/theme.css', 'body { color: black; }')
        page = self.write('docs/index.html', '<section id="overview"></section>')
        source = self.write('README.md', '\n'.join([
            '[`Forms`](<docs/Forms guide.md#keyboard--choices>)',
            '[Encoded](docs/Forms%20guide.md#forms)',
            '<link href="assets/theme.css?v=123" rel="stylesheet">',
            '[Overview](docs/index.html#overview)',
        ]))
        count, issues = check_docs.check_documents(self.root, [source, page])
        self.assertEqual(count, 4)
        self.assertEqual(issues, [])

    def test_missing_file_and_anchor_are_reported_separately(self):
        self.write('guide.md', '# Existing\n')
        source = self.write('README.md', '[Absent](absent.md)\n[Section](guide.md#missing)')
        _, issues = check_docs.check_documents(self.root, [source])
        self.assertEqual([issue.reason for issue in issues], ['missing path', 'missing anchor'])

    def test_duplicate_unicode_headings_and_legacy_ids_remain_linkable(self):
        source = self.write('guide.md', '\n'.join([
            '# Visão `clara`.', '## Repeated', '## Repeated',
            '<a id="old-contract"></a>', '<a name="older-contract"></a>',
            '[First](#repeated)', '[Second](#repeated-1)',
            '[Unicode](#vis%C3%A3o-clara)', '[Legacy](#old-contract)',
            '[Older](#older-contract)',
        ]))
        count, issues = check_docs.check_documents(self.root, [source])
        self.assertEqual(count, 5)
        self.assertEqual(issues, [])

    def test_examples_do_not_create_links_or_anchors(self):
        source = self.write('README.md', '\n'.join([
            '# Guide', '```markdown', '[Missing](absent.md)',
            '<a id="not-a-section"></a>', '```',
            '~~~~html', '<a href="other.html">example</a>', '~~~~',
            '`[Not a link](absent.md)` and `<a href="other.html">`.',
            '`<a id="inline-example"></a>`',
            '[Real](#guide)',
        ]))
        count, issues = check_docs.check_documents(self.root, [source])
        self.assertEqual(count, 1)
        self.assertEqual(issues, [])
        self.assertNotIn('not-a-section', check_docs.document_anchors(source))
        self.assertNotIn('inline-example', check_docs.document_anchors(source))

    def test_explicit_reference_links_and_undefined_labels(self):
        self.write('guide.md', '# Guide')
        source = self.write('README.md', '\n'.join([
            '[Read][Guide]', '[guide][]', '[Missing][unknown]',
            '[Guide]: guide.md#guide', '[Remote]: https://example.invalid/no-network',
        ]))
        count, issues = check_docs.check_documents(self.root, [source])
        self.assertEqual(count, 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].reason, 'undefined reference label: unknown')

    def test_external_destinations_are_not_requested(self):
        source = self.write('README.md', '\n'.join([
            '[Web](https://example.invalid/missing)', '[Mail](mailto:test@example.invalid)',
            '[App](plugin://example)', '![Inline](data:image/png;base64,123)',
        ]))
        self.assertEqual(check_docs.check_documents(self.root, [source]), (0, []))

    def test_absolute_and_escaping_local_paths_are_rejected(self):
        source = self.write('README.md', '[Outside](../outside.md)\n[Absolute](/tmp/example.md)')
        _, issues = check_docs.check_documents(self.root, [source])
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(issue.reason == 'local link must stay inside the repository' for issue in issues))

    def test_cli_includes_untracked_guides_and_ignores_generated_output(self):
        self.write('.gitignore', '.local/\n')
        self.write('README.md', '[New](docs/new.md#contract)')
        self.write('docs/new.md', '# Contract')
        self.write('.local/generated.md', '[Bad](missing.md)')
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        subprocess.run(['git', 'add', 'README.md', '.gitignore'], cwd=self.root, check=True)
        script = check_docs.ROOT / 'scripts/check_docs.py'
        command = [sys.executable, str(script), '--root', str(self.root)]
        good = subprocess.run(command, cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertIn('2 documents;', good.stdout)
        self.write('docs/new.md', '# Renamed')
        broken = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(broken.returncode, 1)
        self.assertIn('missing anchor', broken.stdout)
