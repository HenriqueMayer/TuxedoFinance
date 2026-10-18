/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function (global) {
    'use strict';

    function cents(value) {
        const match = String(value ?? '').trim().match(/^(\d+)(?:\.(\d{0,2}))?$/);
        if (!match) return null;
        return BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'));
    }

    function decimal(value) {
        const digits = value.toString().padStart(3, '0');
        return `${digits.slice(0, -2)}.${digits.slice(-2)}`;
    }

    // Allocate integer cents only. Existing or explicitly edited amounts stay
    // fixed; the first automatic rows receive any indivisible remainder cents.
    function distribute(total, rows) {
        if (total === null || total <= 0n) return {error: 'total'};
        if (rows.length < 2) return {error: 'count'};
        if (total < BigInt(rows.length)) return {error: 'small'};
        const automatic = rows.map((row, index) => row.fixed ? -1 : index).filter(index => index >= 0);
        const fixed = rows.filter(row => row.fixed);
        if (fixed.some(row => row.amount === null || row.amount <= 0n)) return {error: 'amount'};
        const fixedTotal = fixed.reduce((sum, row) => sum + row.amount, 0n);
        const limits = rows.map(row => row.fixed
            ? total - (fixedTotal - row.amount) - BigInt(automatic.length) : null);
        if (fixedTotal > total - BigInt(automatic.length)) return {error: 'limit', limits};
        if (!automatic.length) return fixedTotal === total
            ? {amounts: rows.map(row => row.amount), limits}
            : {error: 'sum', limits};
        const remaining = total - fixedTotal;
        const share = remaining / BigInt(automatic.length);
        const remainder = remaining % BigInt(automatic.length);
        const amounts = rows.map(row => row.amount);
        automatic.forEach((index, order) => { amounts[index] = share + (BigInt(order) < remainder ? 1n : 0n); });
        return {amounts, limits, remainderIndex: automatic.length === 1 && fixed.length ? automatic[0] : -1};
    }

    const math = {cents, decimal, distribute};
    if (typeof module === 'object' && module.exports) module.exports = math;
    if (!global.document || global.TuxedoCategoryAllocation) return;
    const owners = new WeakMap();

    function initialize(form) {
        if (owners.has(form)) return;
        const list = form.querySelector('[data-allocation-rows]');
        const template = form.querySelector('template[data-allocation-template]');
        const totalForms = form.querySelector(`[name="${form.dataset.allocationPrefix}-TOTAL_FORMS"]`);
        const stateField = form.querySelector('[data-allocation-state]');
        const add = form.querySelector('[data-allocation-add]');
        let message = form.querySelector('[data-allocation-message]');
        if (!list || !template || !totalForms || !stateField || !add || !message) return;
        const totalInput = form.dataset.allocationTotal ? form.querySelector(form.dataset.allocationTotal) : null;
        const toggle = form.dataset.allocationToggle ? form.querySelector(form.dataset.allocationToggle) : null;
        const limit = Number(form.dataset.allocationLimit) || 20;
        let rows = [];
        let lastEdited = null;
        let lastError = null;
        let restoring = false;

        function currentTotal() {
            const value = totalInput ? global.TuxedoMoneyInput?.read(totalInput) : form.dataset.allocationAmount;
            return value === null || value === '' ? null : cents(value);
        }

        function readAmount(input) {
            const value = global.TuxedoMoneyInput?.read(input) ?? input.value;
            return cents(value);
        }

        function active() { return !toggle || (toggle.checked && !list.closest('[data-allocation-section]')?.hidden); }
        function visibleRows() { return rows.filter(row => !row.deleted.checked && !row.element.hidden); }
        function show(row, value) {
            row.element.hidden = !value;
            row.deleted.checked = !value;
            if (!value) global.TuxedoForms?.refresh(row.element);
        }

        function remember() {
            stateField.value = JSON.stringify({rows: rows.map(row => ({index: row.index,
                mode: row.fixed ? 'fixed' : 'auto', active: !row.deleted.checked, amountText: row.input.type === 'text'})), lastEdited});
        }

        function translatedAmount(value) {
            const parts = new Intl.NumberFormat(document.documentElement.lang).formatToParts(1234.5);
            const group = parts.find(part => part.type === 'group')?.value || ',';
            const separator = parts.find(part => part.type === 'decimal')?.value || '.';
            const [whole, fraction] = decimal(value < 0n ? 0n : value).split('.');
            return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, group)}${separator}${fraction}`;
        }

        function clearClientError(row) {
            // Deliberate conditional transitions discard old alerts through the
            // shared form contract. Recreate only this module's empty notice.
            if (!row.error.isConnected) {
                row.error = document.createElement('p');
                row.error.dataset.allocationRowError = '';
                row.error.id = `${row.input.id}-allocation-error`;
                row.error.className = 'text-sm text-expense dark:text-expense-light';
                row.element.querySelector('.category-allocation-amount').append(row.error);
            }
            if (!row.input.closest('[data-form-field]')?.querySelector('[data-field-error]')) row.serverInvalid = false;
            row.error.hidden = true;
            row.error.textContent = '';
            row.error.removeAttribute('role');
            if (row.input.dataset.allocationInvalid === 'true') {
                delete row.input.dataset.allocationInvalid;
                if (!row.serverInvalid) row.input.removeAttribute('aria-invalid');
                const ids = (row.input.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id !== row.error.id);
                if (ids.length) row.input.setAttribute('aria-describedby', ids.join(' '));
                else row.input.removeAttribute('aria-describedby');
            }
        }

        function rowError(row, text) {
            if (row.serverInvalid) return; // Rendered Django errors remain the authoritative recovery copy.
            row.error.setAttribute('role', 'alert');
            row.error.textContent = text;
            row.error.hidden = false;
            row.input.dataset.allocationInvalid = 'true';
            row.input.setAttribute('aria-invalid', 'true');
            const ids = new Set((row.input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
            ids.add(row.error.id);
            row.input.setAttribute('aria-describedby', [...ids].join(' '));
        }

        function reconcile({write = true, commit = false} = {}) {
            rows.forEach(row => { clearClientError(row); row.remainder.hidden = true; });
            if (!message.isConnected) {
                message = document.createElement('p');
                message.dataset.allocationMessage = '';
                list.after(message);
            }
            message.hidden = true;
            message.textContent = '';
            message.removeAttribute('role');
            lastError = null;
            if (!active()) { remember(); return true; }
            const visible = visibleRows();
            const total = currentTotal();
            const result = distribute(total, visible.map(row => ({fixed: row.fixed, amount: readAmount(row.input)})));
            if (result.limits) visible.forEach((row, index) => {
                if (row.fixed && result.limits[index] !== null) row.input.max = decimal(result.limits[index] < 0n ? 0n : result.limits[index]);
                else row.input.removeAttribute('max');
            });
            if (result.error === 'total') { remember(); return true; } // The main amount keeps its ordinary server error path.
            if (result.error) {
                lastError = result.error;
                if (result.error === 'amount') {
                    visible.filter(row => row.fixed && (readAmount(row.input) === null || readAmount(row.input) <= 0n))
                        .forEach(row => rowError(row, form.dataset.allocationErrorAmount));
                } else if (result.error === 'limit') {
                    const row = visible.find(item => item.index === lastEdited) || [...visible].reverse().find(item => item.fixed);
                    const index = visible.indexOf(row);
                    if (row) rowError(row, form.dataset.allocationErrorLimit.replace('{amount}', translatedAmount(result.limits[index])));
                } else {
                    message.setAttribute('role', 'alert');
                    message.textContent = form.dataset[`allocationError${result.error[0].toUpperCase()}${result.error.slice(1)}`];
                    message.hidden = false;
                }
            } else {
                visible.forEach((row, index) => {
                    if (!row.fixed && write && (commit || document.activeElement !== row.input || row.input.value !== '')) {
                        row.input.value = decimal(result.amounts[index]);
                    }
                    row.remainder.hidden = index !== result.remainderIndex;
                });
                if (!write && visible.some((row, index) => readAmount(row.input) !== result.amounts[index])) {
                    // Bound errors and history snapshots keep every submitted amount
                    // intact until the user deliberately changes an allocation.
                    lastError = 'sum';
                    message.setAttribute('role', 'alert');
                    message.textContent = form.dataset.allocationErrorSum;
                    message.hidden = false;
                }
            }
            remember();
            return lastError === null;
        }

        function attach(element) {
            const input = element.querySelector('[name$="-amount"]');
            const category = element.querySelector('select[name$="-category"]');
            const deleted = element.querySelector('[name$="-DELETE"]');
            const id = element.querySelector('[name$="-id"]');
            const remove = element.querySelector('[data-allocation-remove]');
            const nativeDelete = element.querySelector('[data-allocation-delete]');
            const error = element.querySelector('[data-allocation-row-error]');
            const remainder = element.querySelector('[data-allocation-remainder]');
            const index = Number(input?.name.match(/-(\d+)-amount$/)?.[1]);
            if (!input || !category || !deleted || !remove || !nativeDelete || !error || !remainder || !Number.isInteger(index)) return null;
            const row = {element, input, category, deleted, id, index, remove, error, remainder,
                fixed: Boolean(id?.value || input.value), serverInvalid: input.getAttribute('aria-invalid') === 'true'};
            const number = element.querySelector('[data-allocation-number]');
            if (number) number.textContent = String(index + 1);
            error.id = `${input.id}-allocation-error`;
            nativeDelete.hidden = true;
            remove.hidden = false;
            remove.parentElement.hidden = false;
            input.inputMode = 'decimal';
            input.addEventListener('input', () => {
                row.fixed = input.value !== '';
                lastEdited = row.index;
                reconcile();
            });
            input.addEventListener('blur', () => {
                if (input.value === '') row.fixed = false;
                const value = readAmount(input);
                if (row.fixed && value !== null && value > 0n) input.value = decimal(value);
                reconcile({commit: true});
            });
            remove.addEventListener('click', () => {
                const before = visibleRows();
                const at = before.indexOf(row);
                show(row, false);
                reconcile({commit: true});
                const next = visibleRows()[Math.min(at, visibleRows().length - 1)];
                const focus = next?.element.querySelector('.search-choice > input') || next?.category || add;
                focus.focus();
            });
            return row;
        }

        function recoverState(initial = false) {
            let saved = null;
            try { saved = JSON.parse(stateField.value); } catch (_) { /* Native/legacy submissions have no progressive UI metadata. */ }
            const states = Array.isArray(saved?.rows) && saved.rows.length <= limit ? saved.rows : [];
            const hasValues = rows.some(row => row.id?.value || row.input.value || row.category.value);
            rows.forEach(row => {
                const state = states.find(item => item?.index === row.index);
                if (state?.amountText === true) row.input.type = 'text';
                row.fixed = state ? state.mode !== 'auto' : Boolean(row.id?.value || row.input.value);
                const meaningful = row.id?.value || row.input.value || row.category.value || row.element.dataset.hasErrors === 'true';
                const requested = form.dataset.allocationAddRequest === 'true';
                show(row, state ? state.active !== false : !row.deleted.checked && (!hasValues || meaningful || requested));
            });
            lastEdited = Number.isInteger(saved?.lastEdited) ? saved.lastEdited : null;
            const fresh = initial && form.dataset.allocationBound !== 'true';
            reconcile({write: fresh && !rows.some(row => row.fixed)});
        }

        function appendRow() {
            const count = Number(totalForms.value);
            if (!Number.isInteger(count) || count >= limit) return null;
            const holder = document.createElement('template');
            holder.innerHTML = template.innerHTML.replaceAll('__prefix__', String(count));
            const element = holder.content.firstElementChild;
            list.append(element);
            const row = attach(element);
            if (!row) return null;
            rows.push(row);
            totalForms.value = String(count + 1);
            // New record choices join the existing shared picker; this module
            // never creates another financial record selector.
            global.TuxedoForms?.init();
            form.dispatchEvent(new Event('tuxedo:allocation-rows-changed'));
            return row;
        }

        function addRow(event) {
            event.preventDefault();
            const row = rows.find(item => item.element.hidden && !item.id?.value) || appendRow();
            if (!row) {
                message.setAttribute('role', 'alert');
                message.textContent = form.dataset.allocationErrorMaximum;
                message.hidden = false;
                return;
            }
            row.category.value = '';
            row.input.value = '';
            row.fixed = false;
            show(row, true);
            global.TuxedoForms?.refresh(row.element);
            reconcile({commit: true});
            (row.element.querySelector('.search-choice > input') || row.category).focus();
        }

        rows = [...list.querySelectorAll('[data-split-row]')].map(attach).filter(Boolean);
        owners.set(form, {
            capture: () => ({formId: form.id, prefix: form.dataset.allocationPrefix,
                rows: rows.map(row => ({index: row.index, mode: row.fixed ? 'fixed' : 'auto', active: !row.deleted.checked,
                    amountText: row.input.type === 'text'})),
                lastEdited}),
            restore: saved => {
                // History may recreate only sequential blank formset slots from
                // this authorized document. Record IDs and values remain owned
                // by server HTML and the identity-scoped form snapshot loader.
                if (!Array.isArray(saved?.rows) || saved.rows.length > limit || saved.rows.length < 2
                        || saved.rows.some((row, index) => row?.index !== index
                            || !['auto', 'fixed'].includes(row.mode) || typeof row.active !== 'boolean'
                            || (row.amountText !== undefined && typeof row.amountText !== 'boolean'))) return;
                while (rows.length < saved.rows.length) if (!appendRow()) return;
                saved.rows.forEach((state, index) => { if (state.amountText === true) rows[index].input.type = 'text'; });
                stateField.value = JSON.stringify({rows: saved.rows,
                    lastEdited: Number.isInteger(saved.lastEdited) ? saved.lastEdited : null});
            },
        });
        // Keep the native fallback after Save in server HTML, so implicit
        // Enter still saves without JavaScript. The enhanced action belongs
        // beside its rows in both visual and keyboard order, without submitting.
        add.type = 'button';
        const actions = add.closest('#category-split-actions');
        const section = list.closest('[data-allocation-section]');
        if (actions && section) section.append(actions);
        add.addEventListener('click', addRow);
        totalInput?.addEventListener('input', () => reconcile());
        totalInput?.addEventListener('change', () => reconcile({commit: true}));
        toggle?.addEventListener('change', () => {
            if (!toggle.checked) rows.forEach((row, index) => { row.fixed = false; show(row, index < 2); });
            reconcile({commit: true});
        });
        form.addEventListener('tuxedo:restore', () => { restoring = true; recoverState(); restoring = false; });
        form.addEventListener('reset', () => queueMicrotask(() => recoverState()));
        form.addEventListener('submit', event => {
            if (event.submitter?.name === 'add_split') return addRow(event);
            if (event.submitter?.name === 'clear_split' || !active() || restoring) return;
            if (!reconcile({commit: true})) {
                event.preventDefault();
                const invalid = visibleRows().find(row => !row.error.hidden)
                    || visibleRows().find(row => row.input.getAttribute('aria-invalid') === 'true');
                if (invalid) invalid.input.focus();
                else { message.tabIndex = -1; message.focus(); }
            }
        });
        recoverState(true);
    }

    function init(root = document) {
        if (root.matches?.('form[data-category-allocation]')) initialize(root);
        root.querySelectorAll('form[data-category-allocation]').forEach(initialize);
    }
    global.TuxedoCategoryAllocation = {init, ...math};
    function forms(root) {
        return [...(root.matches?.('form[data-category-allocation]') ? [root] : []),
            ...root.querySelectorAll('form[data-category-allocation]')];
    }
    global.TuxedoAllocations = {
        capture: root => forms(root).map(form => owners.get(form)?.capture()).filter(Boolean),
        restore: (state, root) => {
            if (!Array.isArray(state)) return;
            init(root);
            forms(root).forEach(form => {
                const saved = state.find(item => item?.formId === form.id && item.prefix === form.dataset.allocationPrefix);
                if (saved) owners.get(form)?.restore(saved);
            });
        },
    };
    document.addEventListener('DOMContentLoaded', () => init());
    document.addEventListener('htmx:afterSwap', event => init(event.detail?.target || document));
    document.addEventListener('htmx:load', event => init(event.detail?.elt || document));
    if (document.readyState !== 'loading') init();
})(typeof window === 'undefined' ? globalThis : window);
