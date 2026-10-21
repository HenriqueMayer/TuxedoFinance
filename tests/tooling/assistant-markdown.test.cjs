// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parse} = require('../../static/js/assistant-markdown.js');

const flatten = nodes => nodes.map(node => typeof node === 'string' ? node : flatten(node.children)).join('');
const tags = nodes => nodes.flatMap(node => typeof node === 'string' ? [] : [node.tag, ...tags(node.children)]);

test('Financial reply formatting includes emphasis, lists and readable tables', () => {
    const value = parse('# Resumo\n\n**Valor**: `BRL 100,00`; *estimativa*.\n\n- Receita\n- Despesa\n\n1. Revisar\n2. Confirmar\n\n| Tipo | Valor |\n| --- | ---: |\n| Previsto | **10,00** |');
    assert.deepEqual(tags(value), ['h3', 'p', 'strong', 'code', 'em', 'ul', 'li', 'li', 'ol', 'li', 'li',
        'table', 'thead', 'tr', 'th', 'th', 'tbody', 'tr', 'td', 'td', 'strong']);
    assert.match(flatten(value), /BRL 100,00/);
});

test('Streaming partial markup can be rerendered when the closing delimiter arrives', () => {
    assert.equal(flatten(parse('O **valor')), 'O **valor');
    assert.deepEqual(parse('O **valor**'), [{tag: 'p', children: ['O ', {tag: 'strong', children: ['valor']}]}]);
    assert.deepEqual(parse('```\nconst valor = 10;'), [{tag: 'pre', children: [{tag: 'code', children: ['const valor = 10;']}]}]);
});

test('Provider HTML, encoded entities and scripts remain literal text', () => {
    const malicious = '<img src=x onerror="alert(1)"><script>alert(2)</script>\n\n&lt;svg onload=alert(3)&gt;';
    const value = parse(malicious);
    assert.deepEqual(tags(value), ['p', 'p']);
    assert.equal(flatten(value), malicious.replace('\n\n', ''));
});

test('Generated links and images cannot create links or fetch resources', () => {
    const value = parse('[Conta](/banking/123/) ![x](https://example.test/pixel) [x](javascript:alert(1))');
    assert.deepEqual(tags(value), ['p']);
    assert.equal(flatten(value), 'Conta (/banking/123/) x (https://example.test/pixel) x (javascript:alert(1))');
});

test('Only a trailing reference-only paragraph duplicated by authorized sources is omitted', () => {
    const options = {references: [{url: '/sandbox/', label: 'Simulação'},
        {url: '/planning/?month=2026-10', label: 'Planejamento'}]};
    const summary = '**Estimativa:** BRL 100,00. Nada foi salvo.';
    const footer = '[Simulação](/sandbox/) · [Planejamento — 2026-10](/planning/?month=2026-10)';
    const original = `${summary}\n\n${footer}\n\n`;
    assert.deepEqual(parse(original, options), parse(summary));
    assert.equal(original, `${summary}\n\n${footer}\n\n`);
    assert.match(flatten(parse(original)), /\/sandbox\//);
    assert.match(flatten(parse(original, {references: []})), /\/sandbox\//);
    assert.deepEqual(parse(footer, options), []);
});

test('Inline explanations, unknown sources and query differences remain visible and inert', () => {
    const options = {references: [{url: '/sandbox/', label: 'Simulação'},
        {url: '/planning/?month=2026-10', label: 'Planejamento'}]};
    for (const value of [
        'Veja [Simulação](/sandbox/) para ajustar a renda.',
        '[Simulação](/sandbox/)\n\nNada foi salvo.',
        '[Simulação](/sandbox/) · [Outra fonte](/banking/123/)',
        '[Planejamento de novembro](/planning/?month=2026-11)',
        '[Câmbio ausente: resultado incompleto](/sandbox/)',
        '[Não foi possível calcular com segurança](/sandbox/)',
        '[Planejamento — 2026-10: câmbio ausente](/planning/?month=2026-10)',
        '[Planejamento — 2026-11](/planning/?month=2026-10)',
        '[Simulação](/sandbox/) [Falso](javascript:alert(1))',
        '![Imagem](/sandbox/)',
        '`[Exemplo](/sandbox/)`',
        '> [Citação](/sandbox/)',
        '```\n[Exemplo](/sandbox/)\n```',
        '```\n[Exemplo](/sandbox/)\n\n[Outro exemplo](/planning/?month=2026-10)',
    ]) {
        assert.deepEqual(parse(value, options), parse(value), value);
        assert.ok(!tags(parse(value, options)).includes('a'));
    }
});

test('Reference footer matching does not trust external or malformed destinations', () => {
    for (const url of ['https://example.test/pixel', '//example.test/pixel', '/\\example.test', '/x\u0000']) {
        const value = `[Não verificado](${url})`;
        assert.deepEqual(parse(value, {references: [{url, label: 'Não verificado'}]}), parse(value));
    }
    assert.deepEqual(parse('[Fonte](/sandbox/)', {references: 'not-an-array'}), parse('[Fonte](/sandbox/)'));
    assert.deepEqual(parse('[Fonte](/sandbox/)', {referenceURLs: ['/sandbox/']}), parse('[Fonte](/sandbox/)'));
    assert.deepEqual(parse('[Fonte](/sandbox/)', null), parse('[Fonte](/sandbox/)'));
});

test('Code blocks preserve HTML and Markdown without formatting or language attributes', () => {
    const value = parse('```html onmouseover=alert(1)\n<strong>**literal**</strong>\n```');
    assert.deepEqual(value, [{tag: 'pre', children: [{tag: 'code', children: ['<strong>**literal**</strong>']}]}]);
});

test('Untrusted punctuation and nested quotes keep the bounded tag vocabulary', () => {
    const value = parse('> **Cuidado**\n> > > > <iframe src="https://example.test">\n\n~~revisar~~ \\*literal\\*');
    const allowed = new Set(['p', 'strong', 'em', 'del', 'code', 'blockquote']);
    assert(tags(value).every(tag => allowed.has(tag)));
    assert.match(flatten(value), /<iframe/);
    assert.match(flatten(value), /\*literal\*/);
});

test('Response bounds apply before parsing and very wide tables remain complete plain text', () => {
    assert.equal(flatten(parse('a'.repeat(17000))).length, 16000);
    const row = Array(25).fill('A').join(' | ');
    const divider = Array(25).fill('---').join(' | ');
    assert.deepEqual(tags(parse(`${row}\n${divider}\n${row}`)), ['p']);
    assert.equal(flatten(parse(`${row}\n${divider}\n${row}`)), `${row}\n${divider}\n${row}`);
});
