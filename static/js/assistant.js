/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoAssistant) return;
    const wide = matchMedia('(min-width: 1280px)');
    let memory = {owner: '', open: false, conversation: ''};
    let pending = null, returnFocus = null, lastURL = '', previousOverflow = null;
    const inertElements = new Map();
    const shell = () => document.querySelector('[data-assistant-shell]');
    const panel = () => shell()?.querySelector('#assistant-panel');
    const content = () => shell()?.querySelector('[data-assistant-body]');
    const currentLocation = () => location.pathname + location.search;
    function status(message = '', recovery = false) {
        const root = shell();
        if (!root) return;
        const notice = root.querySelector('[data-assistant-notice]');
        notice.textContent = message;
        notice.hidden = !message;
        root.querySelector('[data-assistant-recovery]').hidden = !recovery;
    }
    function clearInert() {
        inertElements.forEach((value, node) => { node.inert = value; });
        inertElements.clear();
        if (previousOverflow !== null) document.body.style.overflow = previousOverflow;
        previousOverflow = null;
    }
    function viewport() {
        const root = shell();
        if (!root) return;
        const view = window.visualViewport;
        root.style.setProperty('--assistant-viewport-height', `${view?.height || innerHeight}px`);
        root.style.setProperty('--assistant-viewport-top', `${view?.offsetTop || 0}px`);
        const navigation = document.querySelector('.app-bottom-navigation');
        const rect = navigation?.getBoundingClientRect();
        const bottom = rect && rect.height && rect.top < innerHeight ? innerHeight - rect.top + 16 : 20;
        root.style.setProperty('--assistant-bottom', `${bottom}px`);
        // A floating shortcut yields to an editable control instead of covering
        // its caret or action while the user is working near the screen edge.
        const launcher = root.querySelector('[data-assistant-open]');
        launcher.style.visibility = '';
        const active = document.activeElement;
        if (!memory.open && active?.matches('input, textarea, select, [contenteditable="true"]')) {
            const a = active.getBoundingClientRect(), b = launcher.getBoundingClientRect();
            if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) launcher.style.visibility = 'hidden';
        }
    }
    function mode() {
        clearInert();
        const root = shell(), box = panel();
        document.body.classList.toggle('assistant-docked', Boolean(memory.open && root && wide.matches));
        if (!box || !memory.open) return;
        box.setAttribute('aria-modal', String(!wide.matches));
        if (!wide.matches) {
            Array.from(document.body.children).forEach(node => {
                // Native dialogs are already hidden while closed. Explicitly
                // setting them inert would disable a later top-layer
                // departure confirmation triggered by browser Back/Forward.
                if (node === root || ['SCRIPT', 'STYLE', 'DIALOG'].includes(node.tagName)) return;
                inertElements.set(node, node.inert);
                node.inert = true;
            });
            previousOverflow = document.body.style.overflow;
            document.body.style.overflow = 'hidden';
            if (!box.contains(document.activeElement)) box.querySelector('[data-assistant-close]').focus({preventScroll: true});
        }
        viewport();
    }
    function abort() {
        if (pending) pending.abort();
        pending = null;
        panel()?.removeAttribute('aria-busy');
        const button = shell()?.querySelector('[data-assistant-cancel]');
        if (button) button.hidden = true;
    }
    function close(restoreFocus = true) {
        abort();
        memory.open = false;
        clearInert();
        document.body.classList.remove('assistant-docked');
        const box = panel(), root = shell();
        if (box) box.hidden = true;
        content()?.replaceChildren();
        const launcher = root?.querySelector('[data-assistant-open]');
        if (launcher) { launcher.hidden = false; launcher.setAttribute('aria-expanded', 'false'); }
        if (restoreFocus) (returnFocus?.isConnected ? returnFocus : launcher)?.focus({preventScroll: true});
        viewport();
    }
    function requestURL(path) {
        const root = shell(), url = new URL(path, location.origin);
        if (url.origin !== location.origin || !url.pathname.startsWith('/assistant/')) throw new Error('Invalid assistant destination');
        url.searchParams.set('scope', root.dataset.assistantScope);
        url.searchParams.set('location', currentLocation());
        return url;
    }
    async function load(path, form = null) {
        const root = shell();
        if (!root) return;
        abort();
        const controller = new AbortController();
        pending = controller;
        const url = requestURL(path);
        // A failed POST is never replayed by Retry. Refresh the authorized
        // history first; the original mutation may already have completed.
        lastURL = form ? root.dataset.assistantUrl : url.pathname + url.search;
        const options = {headers: {'X-Tuxedo-Assistant': 'panel'}, credentials: 'same-origin', cache: 'no-store', signal: controller.signal};
        const revision = window.TuxedoRuntimeAssets?.revision;
        if (revision) options.headers['X-Tuxedo-Assets'] = revision;
        if (form) {
            options.method = 'POST';
            options.body = new FormData(form);
            options.body.set('scope', root.dataset.assistantScope);
            options.body.set('location', currentLocation());
            form.querySelectorAll('button').forEach(button => { button.disabled = true; });
        }
        panel().setAttribute('aria-busy', 'true');
        root.querySelector('[data-assistant-cancel]').hidden = Boolean(form);
        status(root.dataset.assistantLoading);
        try {
            const response = await fetch(url, options);
            if (pending !== controller || !root.isConnected) return;
            const assetRedirect = response.headers.get('HX-Redirect');
            if (assetRedirect) {
                // Custom fetch does not implement HTMX's redirect protocol.
                // Offer a native GET through the ordinary departure guard;
                // never mix revisions or discard a financial draft by reload.
                const destination = new URL(assetRedirect, location.origin);
                if (destination.origin === location.origin && destination.pathname.startsWith('/assistant/')) {
                    root.querySelector('[data-assistant-full]').href = destination.href;
                }
                content().replaceChildren();
                status(root.dataset.assistantError, true);
                return;
            }
            const html = await response.text();
            if (pending !== controller || !root.isConnected) return;
            const documentResult = new DOMParser().parseFromString(html, 'text/html');
            const next = documentResult.querySelector('[data-assistant-content]');
            // Never render a login redirect, another session's response or an
            // unrecognized document into the existing financial workspace.
            if (!next || next.dataset.assistantUser !== memory.owner) {
                content().replaceChildren();
                memory.conversation = '';
                lastURL = root.dataset.assistantUrl;
                root.querySelector('[data-assistant-full]').href = lastURL;
                status(response.status === 404 ? root.dataset.assistantError : root.dataset.assistantSessionError, true);
                return;
            }
            // An owned 400 fragment contains recoverable context/form errors.
            // Keep those server explanations visible without broadening scope.
            if (!response.ok && response.status !== 400) throw new Error('Assistant request failed');
            const focused = panel().contains(document.activeElement);
            content().replaceChildren(document.adoptNode(next));
            memory.conversation = next.dataset.conversationId || '';
            const canonical = new URL(response.url);
            lastURL = canonical.pathname + canonical.search;
            root.querySelector('[data-assistant-full]').href = response.ok ? lastURL : root.dataset.assistantUrl;
            if (next.dataset.assistantScope) root.dataset.assistantScope = next.dataset.assistantScope;
            status(response.ok ? '' : root.dataset.assistantError, !response.ok);
            if (form || focused && document.activeElement === document.body) {
                root.querySelector('[data-assistant-close]').focus({preventScroll: true});
            }
        } catch (error) {
            if (pending !== controller || !root.isConnected) return;
            status(error.name === 'AbortError' ? root.dataset.assistantCancelled : root.dataset.assistantError, error.name !== 'AbortError');
        } finally {
            if (pending === controller) {
                pending = null;
                panel()?.removeAttribute('aria-busy');
                root.querySelector('[data-assistant-cancel]').hidden = true;
                form?.querySelectorAll('button').forEach(button => { button.disabled = false; });
            }
        }
    }
    function open() {
        const root = shell();
        if (!root) return;
        returnFocus = document.activeElement;
        // Reopening is a fresh authorization boundary. Another tab may have
        // changed the session while this panel was closed; do not flash an
        // old transcript/context before the owner-checked GET completes.
        content().replaceChildren();
        memory.open = true;
        panel().hidden = false;
        root.querySelector('[data-assistant-open]').hidden = true;
        root.querySelector('[data-assistant-open]').setAttribute('aria-expanded', 'true');
        mode();
        root.querySelector('[data-assistant-close]').focus({preventScroll: true});
        load(memory.conversation ? `${root.dataset.assistantUrl}${memory.conversation}/` : root.dataset.assistantUrl);
    }
    function init() {
        const root = shell();
        if (!root || root.dataset.assistantUser !== memory.owner) {
            abort(); clearInert();
            memory = {owner: root?.dataset.assistantUser || '', open: false, conversation: ''};
            document.body.classList.remove('assistant-docked');
        }
        if (!root) return;
        root.querySelector('[data-assistant-open]').hidden = false;
        viewport();
        if (memory.open) open();
    }
    // Panel-local history is not page navigation. Intercept before the shared
    // document capture handler asks whether to leave an edited financial form.
    window.addEventListener('click', event => {
        const root = shell(), target = event.target.closest?.('a, button');
        if (!root?.contains(target)) return;
        if (target.matches('[data-assistant-link]') && !event.button && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
            event.preventDefault(); event.stopPropagation(); load(target.href); return;
        }
        if (target.matches('[data-assistant-source], [data-assistant-full]')) { close(); return; }
        if (target.matches('[data-assistant-open]')) open();
        else if (target.matches('[data-assistant-close]')) close();
        else if (target.matches('[data-assistant-retry]')) load(lastURL || root.dataset.assistantUrl);
        else if (target.matches('[data-assistant-cancel]')) { abort(); status(root.dataset.assistantCancelled); }
    }, true);
    window.addEventListener('submit', event => {
        if (!shell()?.contains(event.target) || !event.target.matches('[data-assistant-form]')) return;
        event.preventDefault(); event.stopPropagation();
        if (!pending) load(event.target.action, event.target);
    }, true);
    document.addEventListener('keydown', event => {
        const box = panel();
        if (!memory.open || !box || event.defaultPrevented || document.querySelector('dialog[open]')) return;
        if (event.key === 'Escape' && box.contains(document.activeElement)) { event.preventDefault(); close(); }
        if (event.key !== 'Tab' || wide.matches) return;
        const controls = Array.from(box.querySelectorAll('button:not(:disabled), a[href], summary, [tabindex="0"]')).filter(node => {
            if (!node.getClientRects().length || node.closest('[hidden], [inert]')) return false;
            for (let parent = node.parentElement; parent && parent !== box; parent = parent.parentElement) {
                if (parent.tagName === 'DETAILS' && !parent.open) {
                    const summary = Array.from(parent.children).find(child => child.tagName === 'SUMMARY');
                    if (!summary?.contains(node)) return false;
                }
            }
            return true;
        });
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    document.addEventListener('htmx:beforeSwap', event => {
        if (event.detail.target === document.body && event.detail.shouldSwap) { abort(); clearInert(); }
    });
    document.addEventListener('htmx:afterSwap', event => { if (event.detail.target === document.body) init(); });
    document.addEventListener('tuxedo:live-filters-updated', () => { if (memory.open) load(lastURL || shell().dataset.assistantUrl); });
    document.addEventListener('tuxedo:workspace-navigated', () => { if (memory.open) load(lastURL || shell().dataset.assistantUrl); });
    document.addEventListener('focusin', viewport);
    document.addEventListener('scroll', viewport, {passive: true});
    window.addEventListener('resize', viewport);
    window.visualViewport?.addEventListener('resize', viewport);
    window.visualViewport?.addEventListener('scroll', viewport);
    wide.addEventListener('change', mode);
    window.addEventListener('pagehide', () => { abort(); content()?.replaceChildren(); });
    window.addEventListener('pageshow', event => { if (!event.persisted) init(); });
    document.addEventListener('DOMContentLoaded', init);
    if (document.readyState !== 'loading') init();
    window.TuxedoAssistant = {open, close, init};
})();
