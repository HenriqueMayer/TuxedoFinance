// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../static/js/money-input.js'), 'utf8');

function fixture(locale = 'en', initial = '', enabled = true) {
    class Target {
        listeners = new Map();
        addEventListener(name, callback) {
            const callbacks = this.listeners.get(name) || [];
            this.listeners.set(name, [...callbacks, callback]);
        }
        emit(name, event = {}) { for (const callback of this.listeners.get(name) || []) callback(event); }
    }
    const form = new Target();
    const input = Object.assign(new Target(), {
        tagName: 'INPUT', type: 'number', name: 'amount', value: initial,
        defaultValue: initial, dataset: {}, form, disabled: false,
        selectionStart: initial.length, selectionEnd: initial.length,
        getAttribute: name => name === 'value' ? initial : null,
        setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; },
    });
    const document = Object.assign(new Target(), {
        readyState: 'loading', documentElement: {lang: locale},
        querySelectorAll: () => enabled ? [input] : [],
    });
    const window = {};
    vm.runInNewContext(source, {window, document, Intl, WeakSet, queueMicrotask});
    window.TuxedoMoneyInput.initialize();
    function insert(value, data = null, position = value.length, extra = {}) {
        input.value = value;
        input.selectionStart = position;
        input.selectionEnd = position;
        input.emit('input', {data, ...extra});
    }
    function data() {
        const formData = new Map([['amount', input.value], ['title', 'Example']]);
        form.emit('formdata', {formData});
        return formData;
    }
    function paste(value) {
        input.emit('paste', {clipboardData: {getData: () => value}});
        insert(value, null, value.length, {inputType: 'insertFromPaste'});
    }
    return {window, document, input, form, insert, paste, data};
}

test('digit entry shifts exact cents while the submitted field remains canonical', () => {
    const f = fixture();
    for (const [candidate, digit, display] of [
        ['1', '1', '0.01'], ['0.012', '2', '0.12'],
        ['0.123', '3', '1.23'], ['1.234', '4', '12.34'],
    ]) {
        f.insert(candidate, digit);
        assert.equal(f.input.value, display);
    }
    assert.equal(f.data().get('amount'), '12.34');
    assert.equal(f.data().get('title'), 'Example');
    assert.equal(f.input.type, 'text');
    assert.equal(f.input.inputMode, 'decimal');
});

test('allocation readers share exact localized submission amounts without serialization', () => {
    for (const [locale, value] of [['en', '123456789012.34'], ['pt-BR', '123456789012.34']]) {
        const f = fixture(locale, value);
        let serialized = 0;
        f.form.addEventListener('formdata', () => { serialized++; });
        assert.equal(f.window.TuxedoMoneyInput.read(f.input), value);
        assert.equal(serialized, 0);
        f.input.value = '';
        assert.equal(f.window.TuxedoMoneyInput.read(f.input), '');
        f.input.value = 'not an amount';
        assert.equal(f.window.TuxedoMoneyInput.read(f.input), null);
    }
});

test('allocation readers retain ordinary numeric field precision and reject extra decimals', () => {
    const f = fixture();
    assert.equal(f.window.TuxedoMoneyInput.read({value: '0.01'}), '0.01');
    assert.equal(f.window.TuxedoMoneyInput.read({value: '0.001'}), null);
    assert.equal(f.window.TuxedoMoneyInput.read({value: ''}), '');
    assert.equal(f.window.TuxedoMoneyInput.read(null), null);
});

test('locale presentation and explicit decimal pastes preserve the monetary value', () => {
    for (const [locale, expected] of [['en', '1,234.56'], ['pt-br', '1.234,56']]) {
        const f = fixture(locale);
        f.paste('1.234,56');
        assert.equal(f.input.value, expected);
        assert.equal(f.data().get('amount'), '1234.56');
        f.paste('123.45');
        assert.equal(f.data().get('amount'), '123.45');
        f.paste('R$ 1.234,56');
        assert.equal(f.data().get('amount'), '1234.56');
    }
});

test('deletion, selection replacement and a middle caret keep their digit position', () => {
    const f = fixture('en', '12.34');
    f.insert('12.3', null, 4, {inputType: 'deleteContentBackward'});
    assert.equal(f.input.value, '1.23');
    assert.equal(f.input.selectionStart, 4);
    f.insert('9876', '9876');
    assert.equal(f.input.value, '98.76');
    f.insert('9.76', null, 1, {inputType: 'deleteContentForward'});
    assert.equal(f.input.value, '9.76');
    assert.equal(f.input.selectionStart, 1);
    f.insert('', null, 0, {inputType: 'deleteContentBackward'});
    assert.equal(f.input.value, '');
    assert.equal(f.data().get('amount'), '');
});

test('large amounts use strings without float rounding or truncation', () => {
    const f = fixture('pt-br');
    f.insert('900719925474099312', '900719925474099312');
    assert.equal(f.input.value, '9.007.199.254.740.993,12');
    assert.equal(f.data().get('amount'), '9007199254740993.12');
});

test('invalid pasted/bound values and negative amounts reach ordinary server validation', () => {
    const f = fixture('en', 'invalid bound text');
    assert.equal(f.input.value, 'invalid bound text');
    assert.equal(f.data().get('amount'), 'invalid bound text');
    for (const value of ['123.456', '1,23.45', '12abc']) {
        f.paste(value);
        assert.equal(f.input.value, value);
        assert.equal(f.data().get('amount'), value);
    }
    f.paste('-12.34');
    assert.equal(f.data().get('amount'), '-12.34');
    const bound = fixture('pt-br', '123.456');
    bound.input.emit('change');
    bound.form.emit('tuxedo:restore');
    assert.equal(bound.input.value, '123.456');
    assert.equal(bound.data().get('amount'), '123.456');
});

test('initial records, reset and authorized history restoration are idempotent', async () => {
    const f = fixture('pt-br', '1234.56');
    assert.equal(f.input.value, '1.234,56');
    assert.equal(f.input.defaultValue, '1.234,56');
    f.window.TuxedoMoneyInput.initialize();
    f.document.emit('htmx:afterSwap', {detail: {target: f.document}});
    f.document.emit('htmx:load');
    f.document.emit('htmx:load', {detail: {elt: f.document}});
    assert.equal(f.input.listeners.get('input').length, 1);
    f.input.value = '98,76';
    f.form.emit('tuxedo:restore');
    assert.equal(f.input.value, '98,76');
    assert.equal(f.data().get('amount'), '98.76');
    f.input.value = f.input.defaultValue;
    f.form.emit('reset');
    await Promise.resolve();
    assert.equal(f.data().get('amount'), '1234.56');
    f.input.disabled = true;
    const formData = new Map();
    f.form.emit('formdata', {formData});
    assert.equal(formData.has('amount'), false);
});

test('IME composition is left intact until the committed value is available', () => {
    const f = fixture('pt-br');
    f.input.emit('compositionstart');
    f.insert('１２３４', '１２３４', 4, {isComposing: true});
    assert.equal(f.input.value, '１２３４');
    f.input.emit('compositionend');
    assert.equal(f.input.value, '12,34');
    assert.equal(f.data().get('amount'), '12.34');
});

test('ordinary monetary fields keep their native behavior without an explicit opt-in', () => {
    const f = fixture('pt-br', '1234.56', false);
    assert.equal(f.input.type, 'number');
    assert.equal(f.input.value, '1234.56');
    assert.equal(f.input.listeners.size, 0);
    assert.equal(f.form.listeners.size, 0);
});
