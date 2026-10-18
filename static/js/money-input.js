/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoMoneyInput) return;
    const initialized = new WeakSet();
    const readers = new WeakMap();

    function separators(locale) {
        try {
            const parts = new Intl.NumberFormat(locale).formatToParts(1234.5);
            return {
                decimal: parts.find(part => part.type === 'decimal')?.value || '.',
                group: parts.find(part => part.type === 'group')?.value || ',',
            };
        } catch (_) { return {decimal: '.', group: ','}; }
    }

    function canonical(value) {
        const match = String(value).match(/^([+-]?)(\d+)(?:\.(\d{0,2}))?$/);
        if (!match) return null;
        const whole = match[2].replace(/^0+(?=\d)/, '');
        return `${match[1] === '-' ? '-' : ''}${whole}.${(match[3] || '').padEnd(2, '0')}`;
    }

    function fromCents(value) {
        const digits = value.replace(/\D/g, '').replace(/^0+(?=\d)/, '');
        if (!digits) return value.trim() === '-' ? '-' : '';
        const padded = digits.padStart(3, '0');
        return `${value.trim().startsWith('-') ? '-' : ''}${padded.slice(0, -2)}.${padded.slice(-2)}`;
    }

    function explicit(value, marks) {
        const text = value.normalize('NFKC').trim()
            .replace(/^(?:[A-Z]{3}|R\$|\$|€|£)\s*/i, '').replace(/\s/g, '');
        if (!/^[+-]?\d[\d.,]*$/.test(text)) return null;
        const sign = text.startsWith('-') ? '-' : '';
        const unsigned = text.replace(/^[+-]/, '');
        const dot = unsigned.lastIndexOf('.');
        const comma = unsigned.lastIndexOf(',');
        if (dot < 0 && comma < 0) return canonical(sign + unsigned);
        const decimal = dot > comma ? '.' : ',';
        const other = decimal === '.' ? ',' : '.';
        const parts = unsigned.split(decimal);
        if (dot >= 0 && comma >= 0) {
            if (parts.length !== 2 || !/^\d{0,2}$/.test(parts[1])) return null;
            const groups = parts[0].split(other);
            if (!/^\d{1,3}$/.test(groups[0]) || groups.slice(1).some(group => !/^\d{3}$/.test(group))) return null;
            return canonical(`${sign}${groups.join('')}.${parts[1]}`);
        }
        // A single ambiguous separator follows the interface locale; never
        // silently round a pasted third decimal place into a monetary amount.
        if (decimal === marks.group && /^\d{1,3}$/.test(parts[0])
                && parts.slice(1).every(part => /^\d{3}$/.test(part))) {
            return canonical(sign + parts.join(''));
        }
        if (parts.length !== 2 || !/^\d{0,2}$/.test(parts[1])) return null;
        return canonical(`${sign}${parts[0]}.${parts[1]}`);
    }

    function format(value, marks) {
        const parsed = canonical(value);
        if (parsed === null) return value;
        const [whole, fraction] = parsed.split('.');
        return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, marks.group)}${marks.decimal}${fraction}`;
    }

    function caret(value, digitsRight) {
        if (!digitsRight) return value.length;
        let remaining = digitsRight;
        for (let position = value.length - 1; position >= 0; position--) {
            if (/\d/.test(value[position]) && --remaining === 0) {
                while (position > 0 && /[.,]/.test(value[position - 1])) position--;
                return position;
            }
        }
        return value.startsWith('-') ? 1 : 0;
    }

    function enhance(input) {
        if (initialized.has(input) || input.tagName !== 'INPUT' || !input.form || !input.name) return;
        initialized.add(input);
        const marks = separators(input.dataset.moneyLocale || document.documentElement.lang || 'en');
        const form = input.form;
        let composing = false;
        let pasted = null;
        const initial = input.getAttribute('value') ?? input.value;
        const invalidInitial = initial !== '' && canonical(initial) === null ? initial : null;
        // The existing named field remains the only editable control. Native
        // formdata serialization converts its display back to Django's decimal
        // contract, including form.submit(); no hidden duplicate or state store.
        input.type = 'text';
        input.inputMode = 'decimal';
        input.value = initial === '' ? '' : format(canonical(initial) ?? initial, marks);
        input.defaultValue = input.value;
        readers.set(input, () => input.value === '' ? '' : explicit(input.value, marks));

        function render(value, position, explicitInsertion = false) {
            const normalized = value.normalize('NFKC');
            const digitsRight = normalized.slice(position ?? normalized.length).replace(/\D/g, '').length;
            const result = explicitInsertion ? explicit(normalized, marks)
                : (/^[+-]?[\d.,\s]*$/.test(normalized) ? fromCents(normalized) : null);
            input.value = result === null ? value : format(result, marks);
            if (position !== null && position !== undefined && result !== null) {
                const next = caret(input.value, digitsRight);
                input.setSelectionRange(next, next);
            }
        }

        input.addEventListener('paste', event => {
            pasted = event.clipboardData?.getData('text') || null;
        });
        input.addEventListener('compositionstart', () => { composing = true; });
        input.addEventListener('compositionend', () => {
            composing = false;
            render(input.value, input.selectionStart);
        });
        input.addEventListener('input', event => {
            if (composing || event.isComposing) return;
            const inserted = pasted ?? event.data ?? '';
            const hasExplicitDecimal = inserted.length > 1 && /[.,]/.test(inserted);
            pasted = null;
            render(input.value, input.selectionStart, hasExplicitDecimal);
        });
        input.addEventListener('change', () => {
            if (composing || !input.value || input.value === invalidInitial) return;
            const parsed = explicit(input.value, marks);
            if (parsed !== null) input.value = format(parsed, marks);
        });
        form.addEventListener('formdata', event => {
            if (input.disabled || !event.formData.has(input.name)) return;
            if (input.value === invalidInitial) return;
            const parsed = input.value === '' ? '' : explicit(input.value, marks);
            // Invalid bound or pasted text reaches the ordinary server error
            // path intact; neither rounding nor a guessed value conceals it.
            if (parsed !== null) event.formData.set(input.name, parsed);
        });
        function refresh() {
            if (!input.value || input.value === invalidInitial) return;
            const parsed = explicit(input.value, marks);
            if (parsed !== null) input.value = format(parsed, marks);
        }
        form.addEventListener('reset', () => queueMicrotask(refresh));
        form.addEventListener('tuxedo:restore', refresh);
    }

    function initialize(root = document) {
        const inputs = [...root.querySelectorAll('input[data-money-input]')];
        if (root.matches?.('input[data-money-input]')) inputs.unshift(root);
        inputs.forEach(enhance);
    }

    // Allocation previews consume the same exact decimal interpretation as
    // native submission, without constructing FormData or rounding through Number.
    function read(input) {
        if (!input) return null;
        return readers.has(input) ? readers.get(input)()
            : input.value === '' ? '' : canonical(input.value);
    }
    window.TuxedoMoneyInput = {initialize, read};
    document.addEventListener('DOMContentLoaded', () => initialize());
    // Run before previous-workspace captures the freshly swapped form's
    // baseline. Display formatting must never look like an unsaved edit.
    document.addEventListener('htmx:afterSwap', event => initialize(event.detail?.target || document));
    document.addEventListener('htmx:load', event => initialize(event.detail?.elt || document));
    document.addEventListener('htmx:historyRestore', () => initialize());
    if (document.readyState !== 'loading') initialize();
})();
