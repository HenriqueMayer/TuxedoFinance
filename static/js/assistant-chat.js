/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoAssistantChat) return;
    let active = null;
    const uuid = /^[a-f0-9-]{36}$/i;
    function owner() { return document.querySelector('[data-assistant-user]')?.dataset.assistantUser || ''; }
    function valid(state) { return state.root.isConnected && owner() === state.owner; }
    function notice(state, message, failed = false) {
        if (!valid(state)) return;
        const target = state.form.querySelector('[data-assistant-send-status]');
        target.textContent = message;
        target.classList.toggle('assistant-send-status--error', failed);
    }
    function cancelRemote(state) {
        if (!state.run || !uuid.test(state.run)) return;
        const data = new FormData();
        data.set('csrfmiddlewaretoken', state.csrf);
        fetch(`/assistant/runs/${state.run}/cancel/`, {method: 'POST', body: data,
            headers: {'Accept': 'application/json'}, credentials: 'same-origin',
            cache: 'no-store', keepalive: true}).catch(() => {});
    }
    function stop() {
        if (!active) return;
        const state = active;
        state.stopped = true;
        cancelRemote(state);
        state.controller.abort();
        notice(state, state.form.dataset.cancelled);
    }
    function message(transcript, role, label, text = '') {
        const article = document.createElement('article');
        article.className = `assistant-message assistant-message--${role}`;
        const heading = document.createElement('p');
        heading.className = 'assistant-message-role'; heading.textContent = label;
        const body = document.createElement('p');
        body.className = 'assistant-message-text'; body.textContent = text;
        article.append(heading, body); transcript.append(article);
        return body;
    }
    function references(article, values) {
        if (!Array.isArray(values)) return;
        const nav = document.createElement('nav');
        nav.className = 'assistant-references';
        for (const source of values.slice(0, 20)) {
            if (typeof source.url !== 'string' || typeof source.label !== 'string') continue;
            let destination;
            try { destination = new URL(source.url, location.origin); } catch (_) { continue; }
            if (destination.origin !== location.origin || destination.username || destination.password) continue;
            const link = document.createElement('a');
            link.href = destination.href; link.textContent = source.label;
            link.setAttribute('data-assistant-source', ''); nav.append(link);
        }
        if (nav.children.length) article.append(nav);
    }
    async function refresh(state) {
        if (!state.detail || !valid(state)) return;
        const destination = new URL(state.detail, location.origin);
        if (destination.origin !== location.origin || !destination.pathname.startsWith('/assistant/')) return;
        destination.searchParams.set('model', state.model);
        if (state.root.closest('#assistant-panel')) {
            window.TuxedoAssistant?.refreshConversation(destination.pathname + destination.search, state.conversation);
            return;
        }
        const headers = {'X-Tuxedo-Assistant': 'panel'};
        const revision = window.TuxedoRuntimeAssets?.revision;
        if (revision) headers['X-Tuxedo-Assets'] = revision;
        const response = await fetch(destination, {credentials: 'same-origin', cache: 'no-store', headers});
        if (!response.ok || !valid(state) || response.headers.get('HX-Redirect')) return;
        const result = new DOMParser().parseFromString(await response.text(), 'text/html');
        const next = result.querySelector('[data-assistant-content]');
        if (!next || next.dataset.assistantUser !== state.owner || !valid(state)) return;
        state.root.replaceWith(document.adoptNode(next));
        window.TuxedoForms?.refresh(next);
        history.replaceState(history.state, '', destination.pathname + destination.search);
        // Only a native assistant page is rebased. Never approve an edited
        // financial form because a utility-panel request completed beside it.
        document.dispatchEvent(new CustomEvent('tuxedo:workspace-navigated'));
    }
    async function send(form) {
        const root = form.closest('[data-assistant-content]');
        if (!root || active) return;
        const controller = new AbortController(), data = new FormData(form);
        const shell = root.closest('[data-assistant-shell]');
        if (shell) {
            data.set('scope', shell.dataset.assistantScope || '');
            data.set('location', location.pathname + location.search);
        }
        const state = {root, form, owner: root.dataset.assistantUser, controller,
            csrf: data.get('csrfmiddlewaretoken'), model: data.get('model'), run: '',
            detail: '', conversation: '', stopped: false, completed: false, text: '', body: null};
        active = state;
        const transcript = root.querySelector('.assistant-transcript');
        const controls = Array.from(form.querySelectorAll('input,select,textarea,button[type="submit"]'));
        controls.forEach(control => { control.disabled = true; });
        form.querySelector('[data-assistant-stop]').hidden = false;
        form.setAttribute('aria-busy', 'true');
        notice(state, form.dataset.sending);
        const timer = setTimeout(() => { state.timedOut = true; stop(); }, 100000);
        function consume(event) {
            if (!valid(state)) { stop(); return; }
            const lines = event.split('\n'), name = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
            const raw = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
            if (!raw) return;
            const value = JSON.parse(raw);
            if (name === 'meta') {
                if (String(value.owner) !== state.owner || !uuid.test(value.run_id)
                        || !uuid.test(value.conversation_id)) throw new Error('Invalid stream owner');
                state.run = value.run_id; state.detail = value.detail_url;
                state.conversation = value.conversation_id;
                // A failed first response still owns a real local conversation.
                // A deliberate follow-up must stay in that same history.
                form.action = `/assistant/${state.conversation}/messages/`;
                root.dataset.conversationId = state.conversation;
                transcript.querySelector('.assistant-empty')?.remove();
                message(transcript, 'user', form.dataset.userLabel, data.get('content'));
                state.body = message(transcript, 'assistant', form.dataset.assistantLabel);
                return;
            }
            if (!state.run) throw new Error('Missing stream owner');
            if (name === 'text') {
                if (typeof value.delta !== 'string' || state.text.length + value.delta.length > 16000) throw new Error('Invalid stream text');
                state.text += value.delta; state.body.textContent = state.text;
            } else if (name === 'done') {
                if (value.status !== 'completed') throw new Error('Incomplete stream');
                state.completed = true;
                references(state.body.parentElement, value.references);
                notice(state, form.dataset.completed);
            } else if (name === 'error') {
                state.error = value.code || 'provider_error';
                references(state.body.parentElement, value.references);
                throw new Error('Provider error');
            }
        }
        try {
            const revision = window.TuxedoRuntimeAssets?.revision;
            const headers = {'Accept': 'text/event-stream', 'X-Tuxedo-Assistant': 'panel'};
            if (revision) headers['X-Tuxedo-Assets'] = revision;
            const response = await fetch(form.action, {method: 'POST', body: data, headers,
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
            if (!valid(state)) return;
            if (response.headers.get('HX-Redirect')) throw new Error('Asset revision changed');
            if (!(response.headers.get('Content-Type') || '').startsWith('text/event-stream')) {
                const result = new DOMParser().parseFromString(await response.text(), 'text/html');
                const next = result.querySelector('[data-assistant-content]');
                if (response.status === 400 && next?.dataset.assistantUser === state.owner) {
                    root.replaceWith(document.adoptNode(next));
                    window.TuxedoForms?.refresh(next);
                    next.querySelector('[aria-invalid="true"]')?.focus();
                    return;
                }
                throw new Error('Stream unavailable');
            }
            if (!response.body) throw new Error('Stream unavailable');
            const reader = response.body.getReader(), decoder = new TextDecoder();
            let buffer = '';
            try {
                while (!state.completed) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    if (!valid(state)) { stop(); return; }
                    buffer = (buffer + decoder.decode(value, {stream: true})).replace(/\r\n/g, '\n');
                    if (buffer.length > 524288) throw new Error('Stream event too large');
                    let end;
                    while ((end = buffer.indexOf('\n\n')) >= 0) {
                        consume(buffer.slice(0, end)); buffer = buffer.slice(end + 2);
                        if (state.completed) break;
                    }
                }
                if (state.completed) await reader.cancel();
            } finally { reader.releaseLock(); }
            if (!state.completed) throw new Error('Interrupted stream');
            form.elements.content.value = '';
        } catch (_) {
            controller.abort();
            if (!valid(state)) return;
            const message = state.stopped && !state.timedOut ? form.dataset.cancelled
                : ['rate_limited', 'limit_exceeded'].includes(state.error) ? form.dataset.rateError
                : state.error === 'unauthorized' ? form.dataset.sessionError : form.dataset.failed;
            notice(state, message, true);
            if (state.body && state.text) {
                state.body.parentElement.dataset.partial = 'true';
                const partial = document.createElement('p');
                partial.className = 'assistant-partial'; partial.textContent = message;
                state.body.parentElement.append(partial);
            } else state.body?.parentElement.remove();
            cancelRemote(state);
        } finally {
            clearTimeout(timer);
            if (active === state) active = null;
            if (valid(state)) {
                controls.forEach(control => { control.disabled = false; });
                form.querySelector('[data-assistant-stop]').hidden = true;
                form.removeAttribute('aria-busy');
                // Every deliberate new send gets a new key. A browser/network
                // replay of the old POST is deduplicated by the server.
                form.elements.request_id.value = crypto.randomUUID();
                if (state.completed) await refresh(state).catch(() => {});
            }
        }
    }
    window.addEventListener('submit', event => {
        if (!event.target.matches('[data-assistant-send]')) return;
        event.preventDefault(); event.stopPropagation(); send(event.target);
    }, true);
    window.addEventListener('click', event => {
        if (event.target.closest('[data-assistant-stop]')) { event.preventDefault(); stop(); }
    }, true);
    document.addEventListener('htmx:beforeSwap', event => {
        if (active && event.detail.target === document.body) stop();
    });
    window.addEventListener('pagehide', stop);
    window.TuxedoAssistantChat = {stop, cancelWithin(root) { if (active && root?.contains(active.root)) stop(); }};
})();
