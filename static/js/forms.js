/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoForms) return;
    const pickers = new WeakMap();
    const disclosures = new WeakMap();
    const normalize = value => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase();

    function setHidden(group, hidden, preserveErrors = true) {
        if (!group) return;
        if (hidden && !preserveErrors) {
            const errors = Array.from(group.querySelectorAll('[role="alert"], [data-field-error]'));
            const errorIds = new Set(errors.map(error => error.id));
            errors.forEach(error => error.remove());
            group.querySelectorAll('[aria-describedby]').forEach(input => {
                const ids = input.getAttribute('aria-describedby').split(/\s+/).filter(id => !errorIds.has(id));
                if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
                else input.removeAttribute('aria-describedby');
            });
            group.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
            [group, ...group.querySelectorAll('[data-has-errors]')].forEach(element => {
                element.dataset.hasErrors = 'false';
            });
        }
        group.hidden = Boolean(hidden && !(preserveErrors && group.dataset.hasErrors === 'true'));
        if (!group.hidden && group.dataset.hasErrors === 'true') {
            for (let parent = group.parentElement; parent; parent = parent.parentElement) {
                if (parent.tagName === 'DETAILS') parent.open = true;
            }
        }
    }

    function enhance(select, strings) {
        if (pickers.has(select) || !select.id) return;
        const searchId = select.dataset.searchId || `${select.id}-search`;
        const cached = select.nextElementSibling;
        const labels = Array.from(document.querySelectorAll('label')).filter(label =>
            label.htmlFor === select.id || label.htmlFor === searchId);
        // HTMX history stores markup, not event listeners or WeakMap entries.
        if (cached && cached.classList.contains('search-choice')) cached.remove();
        labels.forEach(label => { label.htmlFor = select.id; });
        if (select.disabled) { select.hidden = false; return; }
        const multiple = select.multiple;
        const label = labels[0];
        const name = select.getAttribute('aria-label') || (label && label.textContent.trim()) || select.name;
        const root = document.createElement('div');
        root.className = 'search-choice space-y-2';
        const input = document.createElement('input');
        input.id = searchId;
        input.type = 'search';
        input.autocomplete = 'off';
        input.className = select.className;
        input.placeholder = strings.search;
        if (!label) input.setAttribute('aria-label', name);
        const help = document.createElement('p');
        help.id = `${input.id}-help`;
        help.className = 'text-xs text-forest/70 dark:text-night-muted';
        help.textContent = multiple ? strings.multipleHelp : strings.help;
        const status = document.createElement('p');
        status.id = `${input.id}-selection`;
        status.className = 'text-sm text-forest/70 dark:text-night-muted';
        status.setAttribute('aria-live', 'polite');
        const list = document.createElement('div');
        list.id = `${input.id}-results`;
        list.className = 'search-choice-results max-h-48 overflow-y-auto rounded-xl border border-forest/30 bg-white p-1 dark:border-cream/30 dark:bg-night-surface';
        list.setAttribute('aria-label', name);
        list.setAttribute('role', multiple ? 'group' : 'listbox');
        if (!multiple) {
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
            input.setAttribute('aria-required', String(select.required));
        }
        input.setAttribute('aria-controls', list.id);
        const clear = document.createElement('button');
        clear.type = 'button';
        clear.className = 'text-xs font-medium uppercase tracking-widest text-caramel-ink hover:underline dark:text-caramel-light';
        clear.textContent = strings.clear;
        clear.setAttribute('aria-label', `${strings.clear}: ${name}`);
        root.append(input, help, status, list, clear);
        select.after(root);
        labels.forEach(item => { item.htmlFor = input.id; });
        select.hidden = true;
        select.tabIndex = -1;
        let active = -1;
        let matches = [];
        let items = [];
        let editing = false;
        let revealFrame;

        function revealResults() {
            cancelAnimationFrame(revealFrame);
            revealFrame = requestAnimationFrame(() => {
                if (!input.isConnected || document.activeElement !== input || list.hidden || !input.getClientRects().length) return;
                const viewport = window.visualViewport;
                const viewportTop = viewport ? viewport.offsetTop : 0;
                const bottom = viewportTop + (viewport ? viewport.height : window.innerHeight) - 16;
                const header = document.querySelector('body > header');
                const top = Math.max(viewportTop, header ? header.getBoundingClientRect().bottom : 0) + 16;
                const inputTop = input.getBoundingClientRect().top;
                const gap = list.getBoundingClientRect().top - inputTop;
                // Keep the search and results together, including in a short mobile viewport.
                list.style.maxHeight = `min(12rem, ${Math.max(44, bottom - top - gap)}px)`;
                if (active >= 0) markActive();
                const resultBottom = list.getBoundingClientRect().bottom;
                const distance = inputTop < top ? inputTop - top
                    : Math.min(Math.max(0, resultBottom - bottom), inputTop - top);
                if (distance) window.scrollBy({ top: distance, behavior: 'instant' });
            });
        }

        function committedText() {
            return Array.from(select.selectedOptions).filter(option => option.value).map(option => option.text).join(', ');
        }
        function close() {
            list.hidden = !multiple;
            if (!multiple) input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            active = -1;
            editing = false;
            if (!multiple) input.value = committedText();
        }
        function sync() {
            const text = committedText();
            status.textContent = text ? `${strings.selected} ${text}` : strings.none;
            clear.hidden = !Array.from(select.selectedOptions).some(option => option.value);
            input.disabled = select.disabled;
            clear.disabled = select.disabled;
            if (select.hasAttribute('aria-invalid')) input.setAttribute('aria-invalid', 'true');
            else input.removeAttribute('aria-invalid');
            const describedBy = (select.getAttribute('aria-describedby') || '').split(/\s+/)
                .filter(id => id && document.getElementById(id));
            input.setAttribute('aria-describedby', [...describedBy, help.id, status.id].join(' '));
            if (!multiple && !editing) input.value = text;
        }
        function markActive() {
            items.forEach((item, index) => item.setAttribute('aria-selected', String(index === active)));
            if (active < 0) input.removeAttribute('aria-activedescendant');
            else {
                const item = items[active];
                input.setAttribute('aria-activedescendant', item.id);
                // The positioned results container is the option's offset parent.
                const top = item.offsetTop;
                if (top < list.scrollTop) list.scrollTop = top;
                else if (top + item.offsetHeight > list.scrollTop + list.clientHeight) {
                    list.scrollTop = top + item.offsetHeight - list.clientHeight;
                }
            }
        }
        function choose(option) {
            if (!option || option.hidden || option.disabled) return;
            select.value = option.value;
            close();
            select.dispatchEvent(new Event('change', { bubbles: true }));
            sync();
        }
        function matchingOptions() {
            const query = normalize(editing || multiple ? input.value.trim() : '');
            return Array.from(select.options).filter(option => option.value && !option.hidden && !option.disabled
                && !option.closest('optgroup[disabled]')
                && normalize(option.dataset.search || option.text).includes(query));
        }
        function render() {
            matches = matchingOptions();
            active = -1;
            input.removeAttribute('aria-activedescendant');
            list.replaceChildren();
            items = matches.map((option, index) => {
                const item = document.createElement(multiple ? 'label' : 'div');
                item.id = `${list.id}-${index}`;
                item.className = 'search-choice-option';
                if (multiple) {
                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.checked = option.selected;
                    checkbox.className = 'h-4 w-4 accent-caramel';
                    const text = document.createElement('span');
                    text.textContent = option.text;
                    item.append(checkbox, text);
                    checkbox.addEventListener('change', () => {
                        option.selected = checkbox.checked;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        sync();
                    });
                } else {
                    item.role = 'option';
                    item.setAttribute('aria-selected', 'false');
                    item.textContent = option.text;
                    item.addEventListener('pointerdown', event => event.preventDefault());
                    item.addEventListener('click', () => choose(option));
                }
                list.append(item);
                return item;
            });
            if (!matches.length) {
                const empty = document.createElement('p');
                empty.className = 'px-3 py-2 text-sm text-forest/70 dark:text-night-muted';
                empty.textContent = strings.empty;
                empty.role = 'status';
                list.append(empty);
            }
            list.hidden = false;
            if (!multiple) input.setAttribute('aria-expanded', 'true');
        }
        input.addEventListener('focus', () => {
            if (!multiple) { input.select(); render(); }
            revealResults();
        });
        input.addEventListener('input', () => { editing = true; render(); revealResults(); });
        input.addEventListener('keydown', event => {
            if (event.isComposing) return;
            if (event.key === 'Escape' || (!multiple && event.key === 'Tab')) {
                if (event.key === 'Escape') event.preventDefault();
                close();
                return;
            }
            if (event.key === 'Enter') {
                event.preventDefault();
                if (!multiple && !list.hidden && active >= 0) choose(matches[active]);
                return;
            }
            if (!multiple && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
                event.preventDefault();
                if (list.hidden) render();
                revealResults();
                if (!matches.length) return;
                active = active < 0 ? (event.key === 'ArrowDown' ? 0 : matches.length - 1)
                    : Math.max(0, Math.min(matches.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)));
                markActive();
            }
        });
        input.addEventListener('blur', () => { if (!multiple) close(); });
        clear.addEventListener('click', () => {
            Array.from(select.options).forEach(option => { option.selected = false; });
            if (!multiple) select.value = '';
            close();
            if (multiple) { input.value = ''; render(); }
            select.dispatchEvent(new Event('change', { bubbles: true }));
            sync();
            input.focus();
        });
        const api = { sync, close, revealResults, refresh: () => {
            sync();
            if (multiple) {
                const next = matchingOptions();
                if (next.length !== matches.length || next.some((option, index) => option !== matches[index])) render();
                items.forEach((item, index) => {
                    const checkbox = item.querySelector('input');
                    checkbox.checked = matches[index].selected;
                    checkbox.disabled = select.disabled;
                });
            } else if (!list.hidden) render();
        } };
        pickers.set(select, api);
        sync();
        if (multiple) render(); else close();
    }

    function init() {
        const strings = document.querySelector('[data-form-ui-strings]');
        if (strings) document.querySelectorAll('select[data-search-select]').forEach(select => enhance(select, strings.dataset));
        document.querySelectorAll('details').forEach(details => {
            if (details.querySelector('[aria-invalid="true"], [role="alert"], [data-has-errors="true"]')) details.open = true;
        });
        document.querySelectorAll('[data-form-when]').forEach(group => {
            if (disclosures.has(group)) return;
            const control = document.getElementById(group.dataset.formWhen);
            if (!control) return;
            const update = clear => {
                const matches = group.dataset.formValue === 'positive' ? Number(control.value) > 0
                    : group.dataset.formValue === 'checked' ? control.checked
                    : group.dataset.formValue === 'unchecked' ? !control.checked
                    : control.value === group.dataset.formValue;
                if (!matches && clear) {
                    group.querySelectorAll('input, select, textarea').forEach(input => {
                        if (['checkbox', 'radio'].includes(input.type)) input.checked = false;
                        else if (input.multiple) Array.from(input.options).forEach(option => { option.selected = false; });
                        else input.value = input.dataset.inactiveValue || '';
                        pickers.get(input)?.close();
                        pickers.get(input)?.sync();
                    });
                }
                setHidden(group, !matches, !clear);
                if (!matches && clear) group.querySelectorAll('[data-form-when]').forEach(child => disclosures.get(child)?.(true));
            };
            disclosures.set(group, update);
            control.addEventListener('change', () => update(true));
            if (group.dataset.formValue === 'positive') control.addEventListener('input', () => update(true));
            update(false);
        });
    }
    function refresh(scope = document) {
        scope.querySelectorAll('select[data-search-select]').forEach(select => pickers.get(select)?.refresh());
    }
    window.TuxedoForms = { init, setHidden, refresh };
    function revealFocusedPicker() {
        const root = document.activeElement?.closest('.search-choice');
        pickers.get(root?.previousElementSibling)?.revealResults();
    }
    window.addEventListener('resize', revealFocusedPicker);
    window.visualViewport?.addEventListener('resize', revealFocusedPicker);
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:historyRestore', init);
    document.addEventListener('change', event => {
        // Domain handlers run first, including changes to other native selects.
        queueMicrotask(() => refresh(event.target.closest('form') || document));
    });
    document.addEventListener('reset', event => setTimeout(() => refresh(event.target), 0));
}());
