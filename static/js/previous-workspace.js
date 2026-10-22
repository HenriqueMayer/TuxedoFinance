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
    let pendingDeparture = null;
    let replayHistory = false;
    let historyPosition = Number.isInteger(history.state?.tuxedoPosition) ? history.state.tuxedoPosition : 0;
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
        // Applied live GET state belongs to its URL and fresh history response.
        // Never restore an unsent query over the restored result island.
        if (form.method.toLowerCase() === 'get' && form.hasAttribute('data-live-filters')) return [];
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
                action: form.getAttribute('action') || '', method: form.method.toLowerCase(),
                fields: fields(form).map(field => ({name: field.name, type: field.type, value: field.value,
                    checked: field.checked, selected: field.multiple ? Array.from(field.selectedOptions, option => option.value) : null})),
            })),
            yieldRows: root.querySelector('[data-yield-rows]')?.children.length || 0,
            allocations: window.TuxedoAllocations?.capture(root) || [],
            rows: ['variable', 'deduction'].map(prefix => root.querySelectorAll(`[data-${prefix}-row]`).length),
            details: Array.from(root.querySelectorAll('details'), node => node.open),
            categories: Array.from(root.querySelectorAll('[data-category-toggle]'), node => [node.getAttribute('aria-controls'), node.getAttribute('aria-expanded')]),
        };
    }
    function formState() {
        const snapshot = capture();
        // GET filters are view state: retain them for Back/Forward, but only
        // unsent POST fields (and simulation results) need a departure warning.
        // Hidden-only actions can appear/disappear with GET results. They have
        // no editable draft and must not turn a filtered list into unsent work.
        return snapshot && JSON.stringify({forms: snapshot.forms.filter(form => form.method === 'post' && form.fields.length),
            rows: snapshot.rows, yieldRows: snapshot.yieldRows,
            allocations: snapshot.allocations.map(item => ({formId: item.formId, prefix: item.prefix, rows: item.rows}))});
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
        const next = {identity: identity(), entries, order: recent};
        // A departing document's pagehide can finish after the frozen target
        // starts reauthorization. Keep that target's pending GET restoration.
        if (state?.identity === next.identity && state.revalidate) next.revalidate = state.revalidate;
        write(next);
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
        // Recreate only formset structure before restoring individual owned
        // field values; snapshots never store private HTML or hidden IDs.
        window.TuxedoAllocations?.restore(snapshot.allocations || [], root);
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
            if (node && button) {
                if (button.matches('summary')) {
                    button.closest('details').open = expanded === 'true';
                    node.hidden = false;
                } else node.hidden = expanded === 'false';
                button.setAttribute('aria-expanded', expanded);
            }
        });
        window.TuxedoForms?.init();
        window.TuxedoForms?.refresh(root);
        window.TuxedoCategories?.init();
        root.querySelector('[data-workspace-restored]').hidden = false;
        requestAnimationFrame(() => {
            document.getElementById(snapshot.focus)?.focus({preventScroll: true});
            scrollTo({top: snapshot.top, left: snapshot.left, behavior: 'instant'});
            restoring = false;
        });
    }
    function restoreHistory(destination) {
        if (!main() || destination !== url()) return;
        const root = main();
        // Browsers can restore live control values independently of our
        // snapshots, even onto newly authorized HTML. Start from the server's
        // defaults; only an identity-checked snapshot may restore unsent data.
        root.querySelectorAll('form').forEach(form => {
            form.reset();
            form.dispatchEvent(new Event('tuxedo:restore', {bubbles: true}));
        });
        window.TuxedoForms?.refresh(root);
        baseline = formState();
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
    function needsConfirmation(destination, historyTraversal = false) {
        // Applying a filter on the same screen is not a departure. Browser
        // Back still checks for unsent work that it may replace on that screen.
        if (!historyTraversal && destination.split('?')[0] === currentUrl.split('?')[0]) {
            approvedDestination = destination;
            return false;
        }
        return changed() && approvedDestination !== destination;
    }
    function askDeparture(destination, proceed, cancel = () => {}) {
        const dialog = document.getElementById('departure-confirm');
        // An absent/unsupported enhancement must retain the existing safe
        // confirmation rather than silently discarding an edited operation.
        if (!dialog?.showModal) {
            if (window.confirm(main().dataset.leaveConfirm)) { approvedDestination = destination; proceed(); }
            else cancel();
            return;
        }
        if (pendingDeparture) return;
        const focus = document.activeElement;
        pendingDeparture = {destination, proceed, cancel, focus};
        function finish(leave) {
            const pending = pendingDeparture;
            if (!pending) return;
            pendingDeparture = null;
            dialog.close();
            dialog.removeEventListener('cancel', onCancel);
            dialog.removeEventListener('click', onClick);
            dialog.removeEventListener('keydown', onKey);
            if (leave) {
                approvedDestination = pending.destination;
                pending.proceed();
            } else {
                pending.cancel();
                if (pending.focus?.isConnected) pending.focus.focus({preventScroll: true});
            }
        }
        function onCancel(event) { event.preventDefault(); finish(false); }
        function onClick(event) {
            if (event.target.closest('[data-departure-leave]')) finish(true);
            else if (event.target.closest('[data-departure-stay]') || event.target === dialog) finish(false);
        }
        function onKey(event) {
            if (event.key !== 'Tab') return;
            const controls = Array.from(dialog.querySelectorAll('button:not([disabled])'));
            const first = controls[0], last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        dialog.addEventListener('cancel', onCancel);
        dialog.addEventListener('click', onClick);
        dialog.addEventListener('keydown', onKey);
        dialog.showModal();
        dialog.querySelector('[data-departure-stay]').focus({preventScroll: true});
    }
    function tagHistoryPosition() {
        history.replaceState({...history.state, tuxedoPosition: historyPosition}, '');
    }
    function destinationFor(link) {
        if (!link || link.target || link.hasAttribute('download')) return null;
        const destination = new URL(link.href, location.href);
        const path = destination.pathname + destination.search;
        // In-page anchors only scroll. A contextual Cancel can carry a hash
        // to another screen and must still protect the unsaved operation.
        return destination.origin === location.origin && !(destination.hash && path === currentUrl) ? path : null;
    }
    document.addEventListener('focusin', event => {
        if (event.target.matches('main input[id], main select[id], main textarea[id]')) lastFocus = event.target.id;
    });
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const destination = destinationFor(link);
        if (!destination || destination === currentUrl) return;
        if (needsConfirmation(destination)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            askDeparture(destination, () => link.click());
            return;
        }
        remember();
    }, true);
    document.addEventListener('htmx:confirm', event => {
        if (event.detail.target !== document.body || !main()) return;
        const destination = new URL(event.detail.path, location.href);
        const next = destination.pathname + destination.search;
        if (next === currentUrl || !needsConfirmation(next)) return;
        event.preventDefault();
        askDeparture(next, () => event.detail.issueRequest(true));
    }, true);
    document.addEventListener('htmx:beforeRequest', event => {
        if (event.detail.target !== document.body || !main()) return;
        const path = event.detail.requestConfig?.path;
        if (!path) return;
        const destination = new URL(path, location.href);
        const next = destination.pathname + destination.search;
        if (next !== currentUrl && needsConfirmation(next)) event.preventDefault();
    }, true);
    document.addEventListener('htmx:beforeSwap', event => {
        if (event.detail.target !== document.body || !event.detail.shouldSwap || event.detail.isError) return;
        if (!submitting && new URL(event.detail.xhr.responseURL, location.href).pathname !== location.pathname) remember();
    });
    document.addEventListener('htmx:afterSwap', event => {
        // A newly visible page can receive another click before HTMX's settle
        // delay ends. Treat it as the current workspace immediately.
        if (event.detail.target === document.body) settled();
    });
    document.addEventListener('tuxedo:workspace-navigated', () => {
        // A whole authorized workspace GET replaces its editable forms even
        // when it keeps the outer shell. Its new defaults are not a draft.
        if (main()) settled();
    });
    document.addEventListener('tuxedo:live-filters-updated', () => {
        // A live GET changes only view state. Keep the workspace URL current
        // without rebasing or approving any edited POST on the same screen.
        currentUrl = url();
        pendingHistory = '';
        submitting = false;
        approvedDestination = '';
        remember();
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
    window.addEventListener('pagehide', event => {
        if (!submitting) remember();
        // A browser can freeze private HTML independently of HTMX. Keep that
        // document hidden on restoration until a fresh GET authorizes it.
        if (event.persisted) document.documentElement.hidden = true;
    });
    // Capture-phase traversal runs before HTMX's popstate handler. If the user
    // cancels, return the URL to its entry without replacing the current DOM.
    window.addEventListener('popstate', event => {
        if (cancelHistoryReturn) {
            cancelHistoryReturn = false;
            event.stopImmediatePropagation();
            return;
        }
        if (replayHistory) { replayHistory = false; return; }
        const destination = url();
        if (destination === currentUrl) return;
        const targetPosition = event.state?.tuxedoPosition;
        if (needsConfirmation(destination, true)) {
            event.stopImmediatePropagation();
            const direction = Number.isInteger(targetPosition) ? historyPosition - targetPosition : 1;
            // Delay HTMX's authorized GET until the dialog has a decision.
            // On cancel return to the correct entry for both Back and Forward.
            askDeparture(destination, () => {
                remember();
                pendingHistory = destination;
                if (Number.isInteger(targetPosition)) historyPosition = targetPosition;
                replayHistory = true;
                window.dispatchEvent(new PopStateEvent('popstate', {state: event.state}));
            }, () => {
                cancelHistoryReturn = true;
                history.go(direction || 1);
            });
            return;
        }
        if (Number.isInteger(targetPosition)) historyPosition = targetPosition;
        remember();
        pendingHistory = destination;
    }, true);
    // HTMX replaces the departing entry's state before pushing its next URL.
    // Retain its index as well, so Forward cancellation reverses the right way.
    document.addEventListener('htmx:beforeHistoryUpdate', tagHistoryPosition);
    document.addEventListener('htmx:pushedIntoHistory', () => { historyPosition++; tagHistoryPosition(); });
    document.addEventListener('htmx:replacedInHistory', tagHistoryPosition);
    document.addEventListener('tuxedo:history-entry', event => {
        if (!event.detail.replace) historyPosition++;
        tagHistoryPosition();
    });
    document.addEventListener('htmx:afterSettle', event => {
        // The baseline belongs to afterSwap. A user may edit the new page
        // before HTMX settles; recapturing here would hide unsaved changes.
        if (event.detail.target !== document.body) approvedDestination = '';
    });
    document.addEventListener('htmx:historyRestore', () => requestAnimationFrame(() => {
        tagHistoryPosition();
        // Cached history can restore without a body settle event. Always apply
        // the tab snapshot, including live values of dynamically added rows.
        pendingHistory = url();
        settled();
    }));
    document.addEventListener('DOMContentLoaded', () => {
        tagHistoryPosition();
        currentUrl = url();
        baseline = formState();
        saved(currentUrl);
    });
    window.addEventListener('pageshow', event => {
        currentUrl = url();
        if (event.persisted) {
            const state = read();
            if (state?.identity === identity()) write({...state, revalidate: currentUrl});
            // replace issues a GET even when the frozen document came from a
            // POST response. A reload could resubmit that financial operation.
            submitting = true;
            location.replace(currentUrl);
            return;
        }
        baseline = formState();
        const state = read();
        const revalidated = state?.revalidate === currentUrl;
        if (revalidated) {
            delete state.revalidate;
            write(state);
        }
        if (revalidated || performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
            setTimeout(() => restoreHistory(url()), 0);
        }
    });
    if (document.readyState !== 'loading') {
        tagHistoryPosition();
        currentUrl = url();
        baseline = formState();
    }
})();
