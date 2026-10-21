/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function (root, factory) {
    'use strict';
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.TuxedoAssistantMarkdown = api;
})(typeof window === 'object' ? window : globalThis, function () {
    'use strict';
    // A bounded presentation subset, not HTML sanitization. Only these literal
    // node names become elements; all provider text reaches a text node. Model
    // links/images stay inert: only server-owned reference links are actionable.
    const element = (tag, children) => ({tag, children});
    function inline(value, depth = 0) {
        if (depth >= 6) return [value];
        const nodes = [];
        let source = value;
        const text = value => {
            if (typeof nodes.at(-1) === 'string') nodes[nodes.length - 1] += value;
            else nodes.push(value);
        };
        while (source) {
            let match;
            if ((match = /^\\([\\`*_{}\[\]()#+\-.!>|~])/.exec(source))) text(match[1]);
            else if ((match = /^`([^`\n]+)`/.exec(source))) nodes.push(element('code', [match[1]]));
            else if ((match = /^(\*\*|__)(?=\S)([^\n]*?\S)\1/.exec(source))) {
                nodes.push(element('strong', inline(match[2], depth + 1)));
            } else if ((match = /^(\*|_)(?=\S)([^\n]*?\S)\1/.exec(source))) {
                nodes.push(element('em', inline(match[2], depth + 1)));
            } else if ((match = /^~~(?=\S)([^\n]*?\S)~~/.exec(source))) {
                nodes.push(element('del', inline(match[1], depth + 1)));
            } else if ((match = /^!?\[([^\]\n]*)\]\(([^)\n]*)\)/.exec(source))) {
                // Retain the URL as visible text so an invented citation cannot
                // masquerade as a verified financial source or trigger a load.
                text(match[1] + (match[2] ? ` (${match[2]})` : ''));
            } else {
                const next = source.slice(1).search(/[\\`*_!\[~]/);
                const length = next < 0 ? source.length : next + 1;
                text(source.slice(0, length)); source = source.slice(length); continue;
            }
            source = source.slice(match[0].length);
        }
        return nodes;
    }
    const list = line => /^\s{0,3}(?:([-+*])|\d+[.)])\s+(.+)$/.exec(line);
    const fence = line => /^\s{0,3}(`{3,}|~{3,})[^`]*$/.exec(line);
    const heading = line => /^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+)?$/.exec(line);
    const rule = line => /^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line);
    const cells = line => line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map(cell => cell.trim());
    const divider = line => line.includes('|') && cells(line).every(cell => /^:?-{3,}:?$/.test(cell));
    const sourceLabel = value => value.replace(/\s+/g, ' ').trim();
    function referenceFooter(value, references) {
        if (!references.size) return false;
        const pattern = /\[([^\]\n]+)\]\(([^)\n]+)\)/g;
        const links = Array.from(value.matchAll(pattern));
        return links.length > 0 && links.every(link => references.get(link[2])?.has(sourceLabel(link[1])))
            && /^[\s·•,;|—–-]*$/.test(value.replace(pattern, ''));
    }
    function blocks(value, depth = 0, references = new Map()) {
        const lines = value.replace(/\r\n?/g, '\n').split('\n'), nodes = [];
        let index = 0;
        const special = i => fence(lines[i]) || heading(lines[i]) || rule(lines[i]) || list(lines[i])
            || /^\s{0,3}>\s?/.test(lines[i]) || (i + 1 < lines.length && divider(lines[i + 1]));
        while (index < lines.length) {
            const line = lines[index];
            if (!line.trim()) { index += 1; continue; }
            let match;
            if ((match = fence(line))) {
                const marker = match[1], code = [];
                index += 1;
                while (index < lines.length && !new RegExp(`^\\s{0,3}${marker[0]}{${marker.length},}\\s*$`).test(lines[index])) {
                    code.push(lines[index++]);
                }
                if (index < lines.length) index += 1;
                nodes.push(element('pre', [element('code', [code.join('\n')])]));
            } else if ((match = heading(line))) {
                nodes.push(element(`h${Math.min(6, match[1].length + 2)}`, inline(match[2]))); index += 1;
            } else if (rule(line)) { nodes.push(element('hr', [])); index += 1;
            } else if (/^\s{0,3}>\s?/.test(line) && depth < 3) {
                const quote = [];
                while (index < lines.length && /^\s{0,3}>\s?/.test(lines[index])) {
                    quote.push(lines[index++].replace(/^\s{0,3}>\s?/, ''));
                }
                nodes.push(element('blockquote', blocks(quote.join('\n'), depth + 1)));
            } else if ((match = list(line))) {
                const unordered = !!match[1], items = [];
                while (index < lines.length && (match = list(lines[index])) && !!match[1] === unordered) {
                    items.push(element('li', inline(match[2]))); index += 1;
                }
                nodes.push(element(unordered ? 'ul' : 'ol', items));
            } else if (index + 1 < lines.length && line.includes('|') && divider(lines[index + 1]) && cells(line).length <= 20) {
                const header = cells(line), rows = [];
                index += 2;
                while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
                    const row = cells(lines[index++]);
                    rows.push(element('tr', header.map((_, i) => element('td', inline(row[i] || '')))));
                }
                nodes.push(element('table', [element('thead', [element('tr', header.map(cell => element('th', inline(cell))))]),
                    element('tbody', rows)]));
            } else {
                const paragraph = [line]; index += 1;
                while (index < lines.length && lines[index].trim() && !special(index)) paragraph.push(lines[index++]);
                const text = paragraph.join('\n');
                // Only the final reference-only paragraph can duplicate the
                // server's authorized footer. Keep prose, code, images and
                // explanatory link labels visible; raw Markdown is untouched.
                if (depth === 0 && lines.slice(index).every(line => !line.trim())
                        && referenceFooter(text, references)) continue;
                nodes.push(element('p', inline(text)));
            }
        }
        return nodes;
    }
    function parse(value, options = {}) {
        const sources = Array.isArray(options?.references) ? options.references.slice(0, 20) : [];
        const references = new Map();
        for (const source of sources) {
            if (!source || typeof source.url !== 'string' || source.url.length > 2048
                    || !/^\/(?!\/)/.test(source.url) || /[\\\u0000-\u001f\u007f]/.test(source.url)
                    || typeof source.label !== 'string' || !source.label.trim() || source.label.length > 160) continue;
            const label = sourceLabel(source.label), labels = references.get(source.url) || new Set();
            labels.add(label);
            // The old prompt appended the ISO period to some source labels.
            // Only the exact month already present in the authorized URL is
            // equivalent; arbitrary labels can contain warnings and stay visible.
            const months = new URL(source.url, 'https://tuxedo.invalid').searchParams.getAll('month');
            if (months.length === 1 && /^\d{4}-(0[1-9]|1[0-2])$/.test(months[0])) labels.add(`${label} — ${months[0]}`);
            references.set(source.url, labels);
        }
        return blocks(String(value || '').slice(0, 16000), 0, references);
    }
    function render(target, value, options) {
        const doc = target.ownerDocument;
        function node(value) {
            if (typeof value === 'string') return doc.createTextNode(value);
            const result = doc.createElement(value.tag);
            result.append(...value.children.map(node));
            if (value.tag !== 'table') return result;
            const scroll = doc.createElement('div');
            scroll.className = 'assistant-markdown-table'; scroll.tabIndex = 0;
            scroll.append(result); return scroll;
        }
        target.replaceChildren(...parse(value, options).map(node));
        target.classList.add('assistant-message-markdown');
    }
    return {parse, render};
});
