/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoDates) return;
    const initialized = new WeakSet();

    function initialize(root = document) {
        const groups = [...root.querySelectorAll('[data-preferred-date-field]')];
        if (root.matches?.('[data-preferred-date-field]')) groups.unshift(root);
        for (const group of groups) {
            if (initialized.has(group)) continue;
            const input = group.querySelector('input:not([data-native-date-picker])');
            const picker = group.querySelector('[data-native-date-picker]');
            const button = group.querySelector('[data-open-date-picker]');
            if (!input || !picker || !button) continue;
            initialized.add(group);
            const order = input.dataset.dateOrder || group.dataset.dateOrder;
            function toIso(value) {
                if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
                const parts = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
                if (!parts) return '';
                const [, first, second, year] = parts;
                const month = order === 'MDY' ? first : second;
                const day = order === 'MDY' ? second : first;
                return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
            }
            function fromIso(value) {
                const [year, month, day] = value.split('-');
                return order === 'MDY' ? `${month}/${day}/${year}` : `${day}/${month}/${year}`;
            }
            function syncPicker() { picker.value = toIso(input.value.trim()); }
            button.hidden = false;
            syncPicker();
            // Never rewrite on input: middle edits, selections, deletion and
            // assistive input retain their caret and incomplete text.
            input.addEventListener('input', syncPicker);
            input.addEventListener('blur', () => {
                const digits = input.value.trim();
                if (/^\d{8}$/.test(digits)) {
                    input.value = `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
                } else if (/^\d{4}-\d{2}-\d{2}$/.test(digits)) {
                    input.value = fromIso(digits);
                }
                syncPicker();
            });
            button.addEventListener('click', () => {
                syncPicker();
                if (typeof picker.showPicker === 'function') {
                    try { picker.showPicker(); return; } catch (_) { /* Native fallback below. */ }
                }
                picker.className = input.className;
                picker.setAttribute('aria-label', button.textContent.trim());
                picker.removeAttribute('aria-hidden');
                picker.tabIndex = 0;
                picker.focus();
            });
            picker.addEventListener('change', () => {
                input.value = picker.value ? fromIso(picker.value) : '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.focus({ preventScroll: true });
            });
        }
    }
    window.TuxedoDates = { initialize };
    document.addEventListener('DOMContentLoaded', () => initialize());
    document.addEventListener('htmx:load', event => initialize(event.detail.elt));
    document.addEventListener('htmx:historyRestore', () => initialize());
    if (document.readyState !== 'loading') initialize();
})();
