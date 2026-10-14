/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoMonthFilters) { window.TuxedoMonthFilters.init(); return; }
    const states = new WeakMap();
    let openState = null;
    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }
    function init() {
        if (openState && !openState.root.isConnected) openState.dismiss();
        document.querySelectorAll('[data-month-filter]').forEach(root => {
            if (states.has(root)) { states.get(root).sync(); return; }
            const native = root.querySelector('input[type="month"]');
            if (!native?.id || !window.TuxedoForms) return;
            root.querySelectorAll(':scope > .month-filter-trigger, :scope > .month-filter-panel').forEach(node => node.remove());
            const locale = document.documentElement.lang || 'en';
            const names = Array.from({length: 12}, (_, month) => {
                const name = new Intl.DateTimeFormat(locale, {month: 'long'}).format(new Date(2020, month, 1));
                return name[0].toLocaleUpperCase(locale) + name.slice(1);
            });
            const button = element('button', 'month-filter-trigger action-link');
            button.type = 'button'; button.id = `${native.id}-trigger`;
            button.setAttribute('aria-expanded', 'false');
            button.setAttribute('aria-haspopup', 'dialog');
            const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            icon.setAttribute('viewBox', '0 0 24 24'); icon.setAttribute('class', 'h-4 w-4');
            icon.setAttribute('fill', 'none'); icon.setAttribute('stroke', 'currentColor');
            icon.setAttribute('stroke-width', '1.7'); icon.setAttribute('aria-hidden', 'true');
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', 'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z');
            icon.append(path);
            const caption = element('span'); button.append(icon, caption);
            const panel = element('div', 'month-filter-panel');
            panel.id = `${native.id}-panel`; panel.hidden = true;
            panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', root.dataset.monthLabel);
            button.setAttribute('aria-controls', panel.id);
            const heading = element('div', 'flex items-center justify-between gap-3 mb-4');
            heading.append(element('h2', 'text-sm font-semibold', root.dataset.monthLabel));
            const close = element('button', 'quiet-action', '×'); close.type = 'button';
            close.setAttribute('aria-label', root.dataset.closeLabel); heading.append(close);
            const yearLabel = element('label', 'field-label', root.dataset.yearLabel);
            const year = element('input', 'form-input w-full');
            year.id = `${native.id}-year`; year.type = 'number'; year.inputMode = 'numeric';
            year.disabled = true;
            year.min = native.min?.split('-')[0] || '1'; year.max = native.max?.split('-')[0] || '9998';
            year.step = '1'; yearLabel.htmlFor = year.id;
            // Shared form initialization reveals disclosures containing errors.
            // Only an open, invalid draft may expose an alert or aria-invalid.
            const error = element('p', 'text-sm text-expense dark:text-expense-light');
            error.id = `${year.id}-error`; error.hidden = true;
            const monthLabel = element('label', 'field-label mt-4', root.dataset.choiceLabel);
            const choice = element('select', 'form-input w-full');
            choice.id = `${native.id}-choice`; choice.dataset.searchSelect = '';
            // Only month names support Enter on one textual match. Financial
            // record choices keep their explicit arrow-selection contract.
            choice.dataset.searchAutoSingle = '';
            monthLabel.htmlFor = choice.id;
            choice.append(new Option('', ''), ...names.map((name, index) => new Option(name, String(index + 1).padStart(2, '0'))));
            const clear = element('button', 'quiet-action mt-4', root.dataset.clearLabel); clear.type = 'button';
            panel.append(heading, yearLabel, year, error, monthLabel, choice, clear);
            root.append(button, panel);
            root.querySelector('[data-month-fallback]').hidden = true;
            // Reuse the shared searchable choice, including its viewport and
            // real keyboard behavior; do not create a second record picker.
            window.TuxedoForms.init();
            const search = document.getElementById(`${choice.id}-search`);
            function sync() {
                const value = /^(\d{4})-(\d{2})$/.exec(native.value);
                caption.textContent = value && names[Number(value[2]) - 1]
                    ? `${names[Number(value[2]) - 1]} ${value[1]}` : root.dataset.monthLabel;
                button.setAttribute('aria-label', `${root.dataset.monthLabel}: ${caption.textContent}`);
            }
            function place() {
                if (panel.hidden) return;
                const viewport = window.visualViewport;
                const height = viewport?.height || innerHeight;
                const width = viewport?.width || innerWidth;
                const topEdge = Math.max(12, viewport?.offsetTop || 0);
                const dock = document.querySelector('[data-app-navigation="mobile"]');
                const dockTop = dock && getComputedStyle(dock).display !== 'none' ? dock.getBoundingClientRect().top : height;
                panel.style.maxHeight = `${Math.max(160, Math.min(height, dockTop) - topEdge - 24)}px`;
                const anchor = button.getBoundingClientRect();
                const bounds = panel.getBoundingClientRect();
                panel.style.left = `${Math.max(12, Math.min(anchor.left, width - bounds.width - 12))}px`;
                panel.style.top = `${Math.max(topEdge, Math.min(anchor.bottom + 8, Math.min(height, dockTop) - bounds.height - 12))}px`;
            }
            function dismiss(returnFocus = false) {
                panel.hidden = true; button.setAttribute('aria-expanded', 'false');
                // A closed draft is not a GET criterion. Exclude its native
                // constraints too, so fallback submission cannot focus it.
                year.disabled = true;
                year.removeAttribute('aria-invalid'); year.removeAttribute('aria-describedby');
                error.hidden = true; error.removeAttribute('role');
                if (openState?.root === root) openState = null;
                if (returnFocus) button.focus({preventScroll: true});
            }
            function validYear() {
                const valid = /^\d{1,4}$/.test(year.value) && Number(year.value) >= Number(year.min) && Number(year.value) <= Number(year.max);
                error.textContent = valid ? '' : root.dataset.yearError; error.hidden = valid;
                if (valid) { year.removeAttribute('aria-invalid'); year.removeAttribute('aria-describedby'); error.removeAttribute('role'); }
                else { year.setAttribute('aria-invalid', 'true'); year.setAttribute('aria-describedby', error.id); error.setAttribute('role', 'alert'); }
                requestAnimationFrame(place);
                return valid;
            }
            function commit(month) {
                if (month && !validYear()) { year.focus({preventScroll: true}); return; }
                native.value = month ? `${year.value.padStart(4, '0')}-${month}` : '';
                native.dispatchEvent(new Event('change', {bubbles: true}));
                sync(); dismiss(true);
            }
            button.addEventListener('click', () => {
                if (!panel.hidden) { dismiss(); return; }
                openState?.dismiss();
                openState = {root, panel, dismiss, place};
                const value = /^(\d{4})-(\d{2})$/.exec(native.value);
                year.value = value?.[1] || String(new Date().getFullYear());
                year.disabled = false;
                choice.value = value?.[2] || '';
                validYear(); panel.hidden = false; button.setAttribute('aria-expanded', 'true');
                window.TuxedoForms.refresh(panel); place(); search?.focus({preventScroll: true});
                requestAnimationFrame(place);
            });
            choice.addEventListener('change', () => commit(choice.value));
            year.addEventListener('keydown', event => {
                if (event.key === 'Enter') { event.preventDefault(); if (validYear()) search?.focus({preventScroll: true}); }
            });
            close.addEventListener('click', () => dismiss(true));
            clear.addEventListener('click', () => commit(''));
            root.addEventListener('keydown', event => {
                if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); dismiss(true); }
            });
            root.addEventListener('focusout', () => queueMicrotask(() => {
                if (!root.contains(document.activeElement)) dismiss();
            }));
            native.addEventListener('input', sync); native.addEventListener('change', sync);
            states.set(root, {sync}); sync();
        });
    }
    // One global owner avoids retaining disconnected month controls after
    // repeated HTMX navigation; each field's ordinary listeners die with it.
    document.addEventListener('pointerdown', event => { if (openState && !openState.root.contains(event.target)) openState.dismiss(); });
    document.addEventListener('scroll', event => { if (openState && !openState.panel.contains(event.target)) openState.dismiss(); }, true);
    window.addEventListener('resize', () => openState?.place());
    window.visualViewport?.addEventListener('resize', () => openState?.place());
    window.TuxedoMonthFilters = {init};
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:afterSwap', init);
    document.addEventListener('htmx:historyRestore', init);
    document.addEventListener('tuxedo:live-filters-updated', init);
    if (document.readyState !== 'loading') init();
}());
