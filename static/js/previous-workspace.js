/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoPreviousWorkspace) return;
    window.TuxedoPreviousWorkspace = true;
    const key = 'tuxedo.history-workspace.v2';
    let lastFocus = '';
    let restoring = false;
    let currentUrl = location.pathname + location.search;
    let baseline = '';
    let pendingHistory = '';
    let cancelHistoryReturn = false;
    let submitting = false;
    let approvedDestination = '';
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
    function formState() {
        const snapshot = capture();
        return snapshot && JSON.stringify({forms: snapshot.forms, rows: snapshot.rows, yieldRows: snapshot.yieldRows});
    }
    function simulationResult() {
        return Boolean(main()?.querySelector('#scenario-result-title, #simulation-result .panel-heading'));
    }
    function changed() {
        return Boolean(main() && (formState() !== baseline || simulationResult()));
    }
    function remember(source = currentUrl) {
        const snapshot = capture();
        if (!snapshot) return;
        const state = read();
        const entries = state?.identity === identity() ? state.entries || {} : {};
        const order = state?.identity === identity() ? state.order || [] : [];
        entries[source] = {...snapshot, url: source};
        // Keep only the current and immediately previous history context in
        // this tab, so an older unsent form does not linger in storage.
        const recent = [...order.filter(item => item !== source), source].slice(-2);
        Object.keys(entries).forEach(item => { if (!recent.includes(item)) delete entries[item]; });
        write({identity: identity(), entries, order: recent});
    }
    function saved(destination) {
        const state = read();
        if (state && state.identity !== identity()) { write(null); return null; }
        return state?.entries?.[destination] || null;
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
    function restoreHistory(destination) {
        if (!main() || destination !== url()) return;
        const snapshot = saved(destination);
        if (snapshot) restore(snapshot);
        pendingHistory = '';
        currentUrl = destination;
    }
    function settled() {
        if (!main()) { currentUrl = url(); return; }
        baseline = formState();
        if (pendingHistory === url()) restoreHistory(pendingHistory);
        else currentUrl = url();
        submitting = false;
        approvedDestination = '';
    }
    function confirmDeparture(destination, historyTraversal = false) {
        // Applying a filter on the same screen is not a departure. Browser
        // Back still asks because it may replace unsent work on that screen.
        if (!historyTraversal && destination.split('?')[0] === currentUrl.split('?')[0]) {
            approvedDestination = destination;
            return true;
        }
        if (!changed() || approvedDestination === destination) return true;
        if (!window.confirm(main().dataset.leaveConfirm)) return false;
        approvedDestination = destination;
        return true;
    }
    function destinationFor(link) {
        if (!link || link.target || link.hasAttribute('download')) return null;
        const destination = new URL(link.href, location.href);
        return destination.origin === location.origin && !destination.hash ? destination.pathname + destination.search : null;
    }
    document.addEventListener('focusin', event => {
        if (event.target.matches('main input[id], main select[id], main textarea[id]')) lastFocus = event.target.id;
    });
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const destination = destinationFor(link);
        if (!destination || destination === currentUrl) return;
        if (!confirmDeparture(destination)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
        }
        remember();
    }, true);
    document.addEventListener('htmx:beforeRequest', event => {
        if (event.detail.target !== document.body || !main()) return;
        const path = event.detail.requestConfig?.path;
        if (!path) return;
        const destination = new URL(path, location.href);
        const next = destination.pathname + destination.search;
        if (next !== currentUrl && !confirmDeparture(next)) event.preventDefault();
    }, true);
    document.addEventListener('htmx:beforeSwap', event => {
        if (event.detail.target !== document.body || !event.detail.shouldSwap || event.detail.isError) return;
        if (!submitting && new URL(event.detail.xhr.responseURL, location.href).pathname !== location.pathname) remember();
    });
    document.addEventListener('submit', event => {
        if (event.target.closest('main') || event.target.action.includes('/logout')) {
            submitting = true;
            // A submitted POST is owned by the server, not an unsent draft to
            // resurrect with Back. An invalid response renders its own errors.
            if (event.target.method.toUpperCase() === 'POST') write(null);
        }
    }, true);
    window.addEventListener('beforeunload', event => {
        if (submitting || approvedDestination) return;
        if (!changed()) return;
        event.preventDefault();
        event.returnValue = '';
    });
    window.addEventListener('pagehide', () => { if (!submitting) remember(); });
    // Capture-phase traversal runs before HTMX's popstate handler. If the user
    // cancels, return the URL to its entry without replacing the current DOM.
    window.addEventListener('popstate', event => {
        if (cancelHistoryReturn) {
            cancelHistoryReturn = false;
            event.stopImmediatePropagation();
            return;
        }
        const destination = url();
        if (destination === currentUrl) return;
        if (!confirmDeparture(destination, true)) {
            event.stopImmediatePropagation();
            cancelHistoryReturn = true;
            history.go(1);
            return;
        }
        remember();
        pendingHistory = destination;
    }, true);
    document.addEventListener('htmx:afterSettle', event => {
        if (event.detail.target === document.body || pendingHistory) settled();
        else approvedDestination = '';
    });
    document.addEventListener('htmx:historyRestore', () => requestAnimationFrame(settled));
    document.addEventListener('DOMContentLoaded', () => {
        currentUrl = url();
        baseline = formState();
        saved(currentUrl);
    });
    window.addEventListener('pageshow', event => {
        currentUrl = url();
        baseline = formState();
        if (!event.persisted && performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
            setTimeout(() => restoreHistory(url()), 0);
        }
    });
    if (document.readyState !== 'loading') {
        currentUrl = url();
        baseline = formState();
    }
})();
