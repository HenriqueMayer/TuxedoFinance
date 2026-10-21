/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoAssistant) return;
    const wide = matchMedia('(min-width: 1280px)');
    let memory = {owner: '', open: false, minimized: false, conversation: ''};
    let pending = null, restoring = null, minimizedView = null, returnFocus = null, lastURL = '', previousOverflow = null;
    const inertElements = new Map();
    const shell = () => document.querySelector('[data-assistant-shell]');
    const panel = () => shell()?.querySelector('#assistant-panel');
    const content = () => shell()?.querySelector('[data-assistant-body]');
    const currentLocation = () => location.pathname + location.search;
    function isCurrentContext(path) {
        const current = new URL(location.href), destination = new URL(path, location.origin);
        // Scope normalization omits navigation-only origins and empty filters.
        // Returning to the already-open document must never reload its draft.
        for (const url of [current, destination]) {
            url.searchParams.delete('next');
            for (const [key, value] of [...url.searchParams]) if (!value) url.searchParams.delete(key);
            url.searchParams.sort();
        }
        return current.origin === destination.origin && current.pathname === destination.pathname && current.search === destination.search;
    }
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
        const height = view?.height || innerHeight;
        const short = height < 400;
        const shortChanged = root.hasAttribute('data-assistant-short') !== short;
        root.style.setProperty('--assistant-viewport-height', `${height}px`);
        root.style.setProperty('--assistant-viewport-top', `${view?.offsetTop || 0}px`);
        root.toggleAttribute('data-assistant-short', short);
        if (shortChanged) window.TuxedoAssistantChat?.initialize(document);
        const navigation = document.querySelector('.app-bottom-navigation');
        const rect = navigation?.getBoundingClientRect();
        const bottom = rect && rect.height && rect.top < innerHeight ? innerHeight - rect.top + 16 : 20;
        root.style.setProperty('--assistant-bottom', `${bottom}px`);
        // A floating shortcut yields to an editable control instead of covering
        // its caret or action while the user is working near the screen edge.
        const launcher = root.querySelector(memory.minimized ? '[data-assistant-minimized]' : '[data-assistant-open]');
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
        // Wide panels overlay the workspace. Only the narrow modal mode
        // changes background interaction; neither mode reserves a column.
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
            if (!box.contains(document.activeElement)) box.querySelector('[data-assistant-minimize]').focus({preventScroll: true});
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
        window.TuxedoAssistantChat?.cancelWithin(panel());
        abort();
        restoring?.abort(); restoring = null;
        memory.open = false;
        memory.minimized = false;
        minimizedView = null;
        clearInert();
        const box = panel(), root = shell();
        if (box) box.hidden = true;
        if (root) root.querySelector('[data-assistant-minimized]').hidden = true;
        content()?.replaceChildren();
        const launcher = root?.querySelector('[data-assistant-open]');
        if (launcher) { launcher.hidden = false; launcher.setAttribute('aria-expanded', 'false'); }
        if (restoreFocus) (returnFocus?.isConnected ? returnFocus : launcher)?.focus({preventScroll: true});
        viewport();
    }
    function minimize() {
        if (!memory.open) return;
        abort();
        minimizedView = window.TuxedoAssistantChat?.capture(content()?.querySelector('[data-assistant-content]')) || null;
        memory.conversation = content()?.querySelector('[data-assistant-content]')?.dataset.conversationId || memory.conversation;
        memory.open = false; memory.minimized = true;
        clearInert();
        panel().hidden = true;
        const root = shell();
        root.querySelector('[data-assistant-open]').hidden = true;
        root.querySelector('[data-assistant-open]').setAttribute('aria-expanded', 'false');
        root.querySelector('[data-assistant-minimized]').hidden = false;
        root.querySelector('[data-assistant-minimized-state]').textContent = root.querySelector('[data-assistant-minimized-state]').dataset.defaultText;
        root.querySelector('[data-assistant-restore]').focus({preventScroll: true});
        viewport();
    }
    function reveal() {
        memory.open = true; memory.minimized = false;
        const root = shell();
        root.querySelector('[data-assistant-minimized]').hidden = true;
        root.querySelector('[data-assistant-open]').hidden = true;
        root.querySelector('[data-assistant-open]').setAttribute('aria-expanded', 'true');
        panel().hidden = false;
        mode();
        root.querySelector('[data-assistant-minimize]').focus({preventScroll: true});
    }
    async function restore() {
        if (!memory.minimized || restoring) return;
        const root = shell(), controller = new AbortController();
        if (!root) return;
        restoring = controller;
        const button = root.querySelector('[data-assistant-restore]');
        button.setAttribute('aria-busy', 'true');
        const current = content()?.querySelector('[data-assistant-content]');
        const conversation = current?.dataset.conversationId || memory.conversation;
        const url = requestURL(conversation ? `${root.dataset.assistantUrl}${conversation}/` : root.dataset.assistantUrl);
        const headers = {'X-Tuxedo-Assistant': 'panel'};
        const revision = window.TuxedoRuntimeAssets?.revision;
        if (revision) headers['X-Tuxedo-Assets'] = revision;
        try {
            await window.TuxedoAssistantChat?.flushPreferences();
            if (restoring !== controller || !root.isConnected || !memory.minimized) return;
            // Reauthorize before exposing a hidden draft or transcript. The
            // opaque session binding also rejects another login by the same user.
            const response = await fetch(url, {headers, credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
            const html = await response.text();
            if (restoring !== controller || !root.isConnected || !memory.minimized) return;
            const next = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-assistant-content]');
            if (!response.ok || response.headers.get('HX-Redirect') || !next || next.dataset.assistantUser !== memory.owner) {
                window.TuxedoAssistantChat?.cancelWithin(panel());
                content().replaceChildren();
                memory.conversation = '';
                status(root.dataset.assistantSessionError, true);
                reveal();
                return;
            }
            const retained = content().querySelector('[data-assistant-content]');
            const sameSession = retained?.dataset.assistantSession && retained.dataset.assistantSession === next.dataset.assistantSession;
            if (retained?.dataset.assistantSession && !sameSession) {
                window.TuxedoAssistantChat?.cancelWithin(panel());
                content().replaceChildren();
                memory.conversation = '';
                status(root.dataset.assistantSessionError, true);
                reveal();
                return;
            }
            const streaming = sameSession && next.dataset.providerState === 'ready'
                && retained.querySelector('[name="connection_id"]')?.value === next.querySelector('[name="connection_id"]')?.value
                && window.TuxedoAssistantChat?.isStreamingWithin(retained);
            // A response may finish and refresh the hidden transcript while
            // this authorization GET is travelling. Never replace that newer
            // owned document with the earlier response's incomplete history.
            const refreshedWhileRestoring = sameSession && current && retained !== current;
            let restoredForm = null;
            if (!streaming && !refreshedWhileRestoring) {
                const form = sameSession ? retained.querySelector('[data-assistant-send]') : null;
                const draft = form ? {content: form.elements.content.value, model: form.elements.model.value,
                    effort: form.elements.reasoning_effort.value, context: form.elements.include_context?.checked,
                    connection: form.elements.connection_id.value} : null;
                window.TuxedoAssistantChat?.cancelWithin(panel());
                content().replaceChildren(document.adoptNode(next));
                const nextForm = next.querySelector('[data-assistant-send]');
                if (draft && nextForm) {
                    nextForm.elements.content.value = draft.content;
                    // A same-user account switch keeps the unsent text but
                    // must use the newly authorized account's saved settings
                    // and fresh per-request context consent.
                    if (draft.connection === nextForm.elements.connection_id.value) {
                        nextForm.elements.model.value = draft.model;
                        nextForm.elements.reasoning_effort.value = draft.effort;
                        if (nextForm.elements.include_context) nextForm.elements.include_context.checked = !!draft.content && !!draft.context;
                    }
                }
                window.TuxedoForms?.refresh(next);
                if (draft && nextForm) restoredForm = nextForm;
            }
            memory.conversation = (streaming || refreshedWhileRestoring ? retained : next).dataset.conversationId || '';
            lastURL = url.pathname + url.search;
            root.querySelector('[data-assistant-full]').href = lastURL;
            status();
            reveal();
            // Hidden scroll containers report zero dimensions. Restore the
            // reading position captured before minimizing, only once visible.
            window.TuxedoAssistantChat?.initialize(content().querySelector('[data-assistant-content]'), {
                view: sameSession && minimizedView ? {...minimizedView, focus: null} : null,
            });
            if (restoredForm) window.TuxedoAssistantChat?.refreshSettings(restoredForm);
            minimizedView = null;
        } catch (_) {
            if (restoring === controller && root.isConnected) {
                root.querySelector('[data-assistant-minimized-state]').textContent = root.dataset.assistantError;
            }
        } finally {
            if (restoring === controller) restoring = null;
            button.removeAttribute('aria-busy');
        }
    }
    function requestURL(path) {
        const root = shell(), url = new URL(path, location.origin);
        if (url.origin !== location.origin || !url.pathname.startsWith('/assistant/')) throw new Error('Invalid assistant destination');
        url.searchParams.set('scope', root.dataset.assistantScope);
        url.searchParams.set('location', currentLocation());
        return url;
    }
    async function load(path, form = null, view = null) {
        window.TuxedoAssistantChat?.cancelWithin(panel());
        const root = shell();
        if (!root) return;
        abort();
        const controller = new AbortController();
        pending = controller;
        const url = requestURL(path);
        const preserveDraft = !!form?.matches('[data-assistant-action]');
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
            await window.TuxedoAssistantChat?.flushPreferences();
            if (pending !== controller || !root.isConnected) return;
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
            if (!response.ok && response.status !== 400
                    && !(preserveDraft && [409, 422, 503].includes(response.status))) throw new Error('Assistant request failed');
            const focused = panel().contains(document.activeElement);
            let restoration = view;
            if (view) {
                const current = content().querySelector('[data-assistant-content]');
                if (current) {
                    restoration = window.TuxedoAssistantChat?.capture(current) || view;
                    if (!restoration.focus && document.activeElement === document.body) restoration.focus = view.focus;
                }
            }
            const previous = preserveDraft ? content().querySelector('[data-assistant-content]') : null;
            const previousForm = previous?.querySelector('[data-assistant-send]');
            // A local confirmation refreshes only its transcript. Retain the
            // latest unsent chat draft after owner/session/account revalidation;
            // neither this request nor this snapshot reads a financial form.
            const keepDraft = previousForm && previous.dataset.assistantUser === next.dataset.assistantUser
                && previous.dataset.assistantSession === next.dataset.assistantSession
                && previousForm.elements.connection_id.value === next.querySelector('[name="connection_id"]')?.value;
            if (keepDraft) {
                const nextForm = next.querySelector('[data-assistant-send]');
                nextForm.elements.content.value = previousForm.elements.content.value;
                nextForm.elements.model.value = previousForm.elements.model.value;
                nextForm.elements.reasoning_effort.value = previousForm.elements.reasoning_effort.value;
                if (nextForm.elements.include_context) nextForm.elements.include_context.checked = previousForm.elements.include_context?.checked || false;
            }
            content().replaceChildren(document.adoptNode(next));
            window.TuxedoAssistantChat?.initialize(next, {view: restoration && memory.minimized ? {...restoration, focus: null} : restoration});
            if (keepDraft) window.TuxedoAssistantChat?.refreshSettings(next.querySelector('[data-assistant-send]'));
            memory.conversation = next.dataset.conversationId || '';
            const canonical = new URL(response.url);
            lastURL = canonical.pathname + canonical.search;
            root.querySelector('[data-assistant-full]').href = response.ok ? lastURL : root.dataset.assistantUrl;
            if (next.dataset.assistantScope) root.dataset.assistantScope = next.dataset.assistantScope;
            status(response.ok ? '' : root.dataset.assistantError, !response.ok);
            if (memory.open && !restoration?.focus && (form || focused && document.activeElement === document.body)) {
                root.querySelector('[data-assistant-minimize]').focus({preventScroll: true});
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
        if (memory.minimized) { restore(); return; }
        const root = shell();
        if (!root) return;
        returnFocus = document.activeElement;
        // Reopening is a fresh authorization boundary. Another tab may have
        // changed the session while this panel was closed; do not flash an
        // old transcript/context before the owner-checked GET completes.
        content().replaceChildren();
        reveal();
        load(memory.conversation ? `${root.dataset.assistantUrl}${memory.conversation}/` : root.dataset.assistantUrl);
    }
    function init() {
        const root = shell();
        if (!root || root.dataset.assistantUser !== memory.owner) {
            abort(); clearInert();
            restoring?.abort(); restoring = null;
            memory = {owner: root?.dataset.assistantUser || '', open: false, minimized: false, conversation: ''};
        }
        if (!root) return;
        root.querySelector('[data-assistant-open]').hidden = memory.open || memory.minimized;
        root.querySelector('[data-assistant-minimized]').hidden = !memory.minimized;
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
        if (target.matches('[data-assistant-context-link]') && !event.button && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && isCurrentContext(target.href)) {
            event.preventDefault(); event.stopPropagation(); minimize(); return;
        }
        if (target.matches('[data-assistant-source]')) { minimize(); return; }
        if (target.matches('[data-assistant-full]')) { close(); return; }
        if (target.matches('[data-assistant-open]')) open();
        else if (target.matches('[data-assistant-minimize]')) minimize();
        else if (target.matches('[data-assistant-restore]')) restore();
        else if (target.matches('[data-assistant-close]')) close();
        else if (target.matches('[data-assistant-retry]')) load(lastURL || root.dataset.assistantUrl);
        else if (target.matches('[data-assistant-cancel]')) { abort(); status(root.dataset.assistantCancelled); }
    }, true);
    window.addEventListener('submit', event => {
        if (!shell()?.contains(event.target) || !event.target.matches('[data-assistant-form]')) return;
        event.preventDefault(); event.stopPropagation();
        if (!pending) load(event.target.action, event.target, event.target.matches('[data-assistant-action]')
            ? window.TuxedoAssistantChat?.capture(content().querySelector('[data-assistant-content]')) : null);
    }, true);
    document.addEventListener('keydown', event => {
        const box = panel();
        if (!memory.open || !box || event.defaultPrevented || document.querySelector('dialog[open]')) return;
        if (event.key === 'Escape' && box.contains(document.activeElement)) {
            event.preventDefault();
            if (!window.TuxedoAssistantChat?.dismissMenu(box)) minimize();
        }
        if (event.key !== 'Tab' || wide.matches) return;
        const controls = Array.from(box.querySelectorAll('button, input, select, textarea, a[href], summary, [tabindex]')).filter(node => {
            if (node.matches(':disabled') || node.tabIndex < 0 || !node.getClientRects().length || node.closest('[hidden], [inert]')) return false;
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
        if (event.detail.target === document.body && event.detail.shouldSwap) { abort(); restoring?.abort(); restoring = null; clearInert(); }
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
    window.addEventListener('pagehide', () => { abort(); restoring?.abort(); restoring = null; content()?.replaceChildren(); });
    window.addEventListener('pageshow', event => { if (!event.persisted) init(); });
    document.addEventListener('DOMContentLoaded', init);
    if (document.readyState !== 'loading') init();
    window.TuxedoAssistant = {open, close, minimize, restore, init, refreshConversation(path, conversation, view = null) {
        if (!memory.open && !memory.minimized) return;
        memory.conversation = conversation || memory.conversation;
        return load(path, null, view);
    }};
})();
