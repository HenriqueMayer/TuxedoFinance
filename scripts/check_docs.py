#!/usr/bin/env python3
"""Check repository-local documentation links and anchors without network access.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

import argparse
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
INLINE_LINK = re.compile(r'\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n)]*)?\)')
DEFINITION = re.compile(r'^ {0,3}\[([^\]\n]+)\]:\s*(<[^>\n]+>|\S+)', re.M)
REFERENCE_LINK = re.compile(r'\[([^\]\n]+)\]\[([^\]\n]*)\]')


@dataclass(frozen=True)
class Issue:
    document: Path
    reference: str
    reason: str


class HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key in ('href', 'src'):
            if attributes.get(key):
                self.links.append(attributes[key])
        if attributes.get('id'):
            self.anchors.add(attributes['id'])
        if tag == 'a' and attributes.get('name'):
            self.anchors.add(attributes['name'])

    handle_startendtag = handle_starttag


def without_examples(source):
    """Keep prose markup, excluding fenced blocks and inline code examples."""
    kept = []
    fence = None
    for line in source.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        # Preserve the text of inline code for heading slugs; remove its
        # contents only while collecting links, below.
        kept.append(line)
    return '\n'.join(kept)


def heading_slug(title):
    title = re.sub(r'!?\[([^\]]+)\]\([^)]+\)', r'\1', title)
    title = re.sub(r'<[^>]*>', '', unescape(title)).lower().replace('`', '')
    return re.sub(r'[^\w\- ]', '', title).replace(' ', '-')


def document_anchors(path):
    source = without_examples(path.read_text(encoding='utf-8'))
    html = HTMLReferences()
    # Inline HTML examples do not create real anchors in Markdown. Heading
    # text retains its code contents so `Field` still slugs as "field".
    html.feed(re.sub(r'(`+)[^\n]*?\1', '', source) if path.suffix.lower() == '.md' else source)
    anchors = html.anchors
    if path.suffix.lower() != '.md':
        return anchors
    counts = {}
    for title in re.findall(r'^ {0,3}#{1,6}\s+(.+?)\s*#*$', source, re.M):
        slug = heading_slug(title)
        count = counts.get(slug, 0)
        anchors.add(slug if not count else f'{slug}-{count}')
        counts[slug] = count + 1
    return anchors


def local_references(path):
    source = without_examples(path.read_text(encoding='utf-8'))
    if path.suffix.lower() == '.md':
        # Removing inline code also empties backticked link labels, but the
        # surrounding [](target) remains a valid link for this check.
        source = re.sub(r'(`+)[^\n]*?\1', '', source)
        links = [match[1] for match in INLINE_LINK.finditer(source)]
        definitions = {key.casefold(): value for key, value in DEFINITION.findall(source)}
        links.extend(definitions.values())
        for label, key in REFERENCE_LINK.findall(source):
            name = (key or label).casefold()
            if name not in definitions:
                yield None, f'undefined reference label: {key or label}'
        for link in links:
            yield link.strip('<>'), None
    html = HTMLReferences()
    html.feed(source)
    for link in html.links:
        yield link, None


def check_documents(root, documents):
    root = root.resolve()
    issues = []
    checked = 0
    anchor_cache = {}
    for document in documents:
        for raw, error in local_references(document):
            if error:
                issues.append(Issue(document, '', error))
                continue
            parsed = urlsplit(unescape(raw))
            if parsed.scheme or parsed.netloc:
                continue
            checked += 1
            target = (document.parent / unquote(parsed.path)).resolve() if parsed.path else document.resolve()
            if parsed.path.startswith('/') or not target.is_relative_to(root):
                issues.append(Issue(document, raw, 'local link must stay inside the repository'))
            elif not target.exists():
                issues.append(Issue(document, raw, 'missing path'))
            elif parsed.fragment and target.suffix.lower() in ('.md', '.html'):
                if target not in anchor_cache:
                    anchor_cache[target] = document_anchors(target)
                if unquote(parsed.fragment) not in anchor_cache[target]:
                    issues.append(Issue(document, raw, 'missing anchor'))
    return checked, issues


def tracked_documents(root):
    """Include new source guides, excluding ignored installation/artifact trees."""
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z',
         '--', '*.md', 'docs/design-system.html'],
        cwd=root, check=True, capture_output=True, text=True,
    )
    return sorted({root / name for name in result.stdout.split('\0') if name and (root / name).is_file()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Git source checkout to inspect')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    documents = tracked_documents(root)
    checked, issues = check_documents(root, documents)
    for issue in issues:
        print(f'{issue.document.relative_to(root)}: {issue.reference}: {issue.reason}')
    print(f'{len(documents)} documents; {checked} local references; {len(issues)} unresolved.')
    return bool(issues)


if __name__ == '__main__':
    raise SystemExit(main())
