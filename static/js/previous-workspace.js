/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoPreviousWorkspace) return;
    window.TuxedoPreviousWorkspace = true;
    const key = 'tuxedo.previous-workspace.v1';
    let lastFocus = '';
    let restoring = false;
    const main = () => document.querySelector('main[data-workspace-user]');
    const url = () => location.pathname + location.search;
    function read() {
        try { return JSON.parse(sessionStorage.getItem(key) || 'null'); } catch (_) { return null; }
    }
    function write(value) {
        try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch (_) {
            try { sessionStorage.removeItem(key); } catch (_) { /* Storage may be unavailable. */ }
        }
    }
    function identity() {
        const root = main();
        return root && [root.dataset.workspaceUser, root.dataset.workspaceFormat, document.documentElement.lang,
            document.querySelector('meta[name="tuxedo-assets"]')?.content].join('|');
    }
    function fields(form) {
        return Array.from(form.elements).filter(field => field.name &&
            ['INPUT', 'SELECT', 'TEXTAREA'].includes(field.tagName) &&
            !['password', 'file', 'hidden', 'submit', 'button', 'reset'].includes(field.type) &&
            !field.name.toLowerCase().includes('password'));
    }
    function capture() {
        const root = main();
        if (!root || location.pathname.startsWith('/accounts/')) return null;
        return { identity: identity(), url: url(), title: root.querySelector('h1')?.textContent.trim() || document.title,
            top: scrollY, left: scrollX, focus: lastFocus,
            forms: Array.from(root.querySelectorAll('form')).map(form => ({
                action: form.getAttribute('action') || '',
                fields: fields(form).map(field => ({name: field.name, type: field.type, value: field.value,
                    checked: field.checked, selected: field.multiple ? Array.from(field.selectedOptions, option => option.value) : null})),
            })),
            yieldRows: root.querySelector('[data-yield-rows]')?.children.length || 0,
            rows: ['variable', 'deduction'].map(prefix => root.querySelectorAll(`[data-${prefix}-row]`).length),
            details: Array.from(root.querySelectorAll('details'), node => node.open),
            categories: Array.from(root.querySelectorAll('[data-category-toggle]'), node => [node.getAttribute('aria-controls'), node.getAttribute('aria-expanded')]),
        };
    }
    function prepare(destination) {
        if (restoring || destination === url()) return;
        const state = read();
        const previous = state?.previous;
        const resume = previous?.identity === identity() && previous.url === destination ? previous : null;
        write({previous: capture(), resume, destination});
    }
    function restore(snapshot) {
        const root = main();
        restoring = true;
        ['variable', 'deduction'].forEach((prefix, index) => {
            const container = root.querySelector(`[data-${prefix}-rows]`);
            const template = root.querySelector(`#sandbox-${prefix}-template`);
            if (!container || !template) return;
            while (container.children.length > snapshot.rows[index]) container.lastElementChild.remove();
            while (container.children.length < snapshot.rows[index]) container.append(template.content.cloneNode(true));
            container.querySelectorAll(`[data-remove-${prefix}]`).forEach((button, i) => { button.value = `remove_${prefix}_${i}`; });
        });
        const yieldRows = root.querySelector('[data-yield-rows]');
        const yieldTemplate = root.querySelector('#yield-override-template');
        if (yieldRows && yieldTemplate) {
            const count = Math.min(120, Math.max(1, snapshot.yieldRows || 12));
            yieldRows.replaceChildren();
            for (let index = 0; index < count; index++) {
                const row = yieldTemplate.content.cloneNode(true);
                row.querySelector('th').textContent = String(index + 1);
                row.querySelectorAll('input').forEach(input => {
                    input.name = input.name.replace('__index__', String(index));
                    input.setAttribute('aria-label', input.getAttribute('aria-label').replace('__number__', String(index + 1)));
                });
                yieldRows.append(row);
            }
        }
        root.querySelectorAll('form').forEach((form, index) => {
            const saved = snapshot.forms[index];
            if (!saved || saved.action !== (form.getAttribute('action') || '')) return;
            const remaining = [...saved.fields];
            fields(form).forEach(field => {
                const index = remaining.findIndex(item => item.name === field.name && item.type === field.type);
                if (index < 0) return;
                const item = remaining.splice(index, 1)[0];
                if (field.multiple) Array.from(field.options).forEach(option => { option.selected = item.selected.includes(option.value); });
                else field.value = item.value;
                if (['checkbox', 'radio'].includes(field.type)) field.checked = item.checked;
            });
            // Refresh presentation without firing change/input or submitting a POST.
            form.dispatchEvent(new Event('tuxedo:restore', {bubbles: true}));
        });
        root.querySelectorAll('details').forEach((node, i) => { node.open = Boolean(snapshot.details[i]); });
        snapshot.categories.forEach(([id, expanded]) => {
            const node = document.getElementById(id);
            const button = Array.from(root.querySelectorAll('[data-category-toggle]')).find(item => item.getAttribute('aria-controls') === id);
            if (node && button) { node.hidden = expanded === 'false'; button.setAttribute('aria-expanded', expanded); }
        });
        window.TuxedoForms?.init();
        window.TuxedoForms?.refresh(root);
        root.querySelector('[data-workspace-restored]').hidden = false;
        requestAnimationFrame(() => {
            document.getElementById(snapshot.focus)?.focus({preventScroll: true});
            scrollTo({top: snapshot.top, left: snapshot.left, behavior: 'instant'});
            restoring = false;
        });
    }
    function init() {
        const root = main();
        const state = read();
        if (!root || state?.previous?.identity !== identity()) { write(null); return; }
        if (state.destination && state.destination !== url()) return;
        if (state.destination) write({previous: state.previous, resume: state.resume});
        const link = root.querySelector('[data-previous-workspace]');
        if (state.previous.url !== url() && state.previous.url.startsWith('/') && !state.previous.url.startsWith('//')) {
            link.href = state.previous.url;
            link.querySelector('span').textContent = state.previous.title;
            link.hidden = false;
        }
        const snapshot = state.resume?.url === url() ? state.resume : state.previous.url === url() ? state.previous : null;
        if (snapshot?.identity === identity()) {
            write(state.previous.url === url() ? null : {previous: state.previous});
            restore(snapshot);
        }
    }
    document.addEventListener('focusin', event => {
        if (event.target.matches('main input[id], main select[id], main textarea[id]')) lastFocus = event.target.id;
    });
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
        if (link.closest('nav') && !link.matches('[data-workspace-shortcut], [data-previous-workspace]')) {
            write(null);
            const root = main();
            if (root) {
                root.querySelector('[data-previous-workspace]').hidden = true;
                root.querySelector('[data-workspace-restored]').hidden = true;
            }
            return;
        }
        // In-place filters and chart windows stay within the current workspace.
        const target = link.closest('[hx-target]')?.getAttribute('hx-target');
        if (window.htmx && link.hasAttribute('hx-get') && target && target !== 'body') return;
        const destination = new URL(link.href, location.href);
        if (destination.pathname === location.pathname && !link.matches('[data-previous-workspace]')) return;
        if (destination.origin === location.origin && !destination.hash) prepare(destination.pathname + destination.search);
    }, true);
    document.addEventListener('submit', event => {
        if (event.target.closest('main') || event.target.action.includes('/logout')) write(null);
    }, true);
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0));
    document.addEventListener('htmx:afterSettle', () => setTimeout(init, 0));
    document.addEventListener('htmx:historyRestore', () => setTimeout(init, 0));
    window.addEventListener('pageshow', () => setTimeout(init, 0));
})();
