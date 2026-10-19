/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoAssistantChat) return;
    let active = null;
    const uuid = /^[a-f0-9-]{36}$/i;
    const transcriptStates = new WeakMap();
    const preferenceSaves = new Map();
    const transcriptResize = window.ResizeObserver ? new ResizeObserver(entries => {
        for (const {target} of entries) {
            if (!target.isConnected) transcriptResize.unobserve(target);
            else if (transcriptStates.get(target)?.follow) tail(target);
        }
    }) : null;
    const transcriptFor = root => root?.querySelector('[data-assistant-transcript], .assistant-transcript');
    const nearTail = transcript => !transcript || transcript.scrollHeight - transcript.clientHeight - transcript.scrollTop <= 64;
    function tail(transcript) {
        if (!transcript?.isConnected) return;
        transcript.scrollTop = transcript.scrollHeight;
        const state = transcriptStates.get(transcript);
        if (state) state.follow = true;
    }
    function resizeMessage(textarea) {
        if (!textarea?.isConnected) return;
        textarea.rows = 1;
        textarea.style.height = 'auto';
        const style = getComputedStyle(textarea);
        const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
        const maximum = parseFloat(style.maxHeight);
        const limit = Number.isFinite(maximum) ? Math.min(120, maximum) : 120;
        const height = Math.min(limit, textarea.scrollHeight + border);
        textarea.style.height = `${height}px`;
        textarea.style.overflowY = textarea.scrollHeight > height - border ? 'auto' : 'hidden';
    }
    function focusToken(root) {
        const element = document.activeElement;
        if (!root?.contains(element)) return null;
        if (element.matches('[data-assistant-send] button[type="submit"]')) return {submit: true};
        if (!element.matches('input[name], select[name], textarea[name]')) return null;
        return {name: element.name, selectionStart: element.selectionStart, selectionEnd: element.selectionEnd};
    }
    function capture(root) {
        const transcript = transcriptFor(root);
        return {follow: nearTail(transcript), scrollTop: transcript?.scrollTop || 0, focus: focusToken(root)};
    }
    function dismissMenu(root, focus = true) {
        const menus = Array.from(root?.querySelectorAll('[data-assistant-menu][open]') || []);
        const menu = menus.find(item => item.contains(document.activeElement)) || menus.at(-1);
        if (!menu) return false;
        menu.open = false;
        if (focus) menu.querySelector('summary')?.focus({preventScroll: true});
        return true;
    }
    function sizeSettings(settings) {
        const frame = settings.closest('.assistant-composer-frame');
        const content = settings.closest('[data-assistant-content]');
        if (!frame || !content) return;
        const top = Math.max(0, content.getBoundingClientRect().top);
        frame.style.setProperty('--assistant-settings-max-height', `${Math.max(44, frame.getBoundingClientRect().top - top - 12)}px`);
    }
    function settingsChoices(form, {changed = false} = {}) {
        const settings = form.querySelector('[data-assistant-settings]');
        if (!settings) return;
        const model = form.elements.model, effort = form.elements.reasoning_effort;
        if (!model || !effort) return;
        const selected = (settings._models || []).find(item => item.slug === model.value);
        const allowed = selected?.reasoning_efforts || [];
        const previous = effort.value;
        // Keep the server's translated labels; capabilities only narrow the
        // choices. Unknown models never gain guessed effort levels.
        for (const option of settings._efforts || []) {
            option.hidden = !!option.value && !allowed.includes(option.value);
            option.disabled = option.hidden;
        }
        if (changed && previous && !allowed.includes(previous)) {
            effort.value = '';
            const notice = settings.querySelector('[data-assistant-settings-notice]');
            notice.textContent = notice.dataset.reset;
        } else if (changed) settings.querySelector('[data-assistant-settings-notice]').textContent = '';
        const caption = form.querySelector('[data-assistant-model-caption]');
        if (caption) {
            caption.textContent = model.selectedOptions[0]?.textContent || '';
            caption.parentElement.title = caption.textContent;
        }
        const level = form.querySelector('[data-assistant-effort-caption]');
        if (level) level.textContent = model.value ? effort.selectedOptions[0]?.textContent || '' : '';
    }
    function preferenceStatus(item, state) {
        if (!item.form.isConnected) return;
        const message = item.form.querySelector('[data-assistant-preferences-status]');
        const retry = item.form.querySelector('[data-assistant-preferences-retry]');
        if (message) {
            message.textContent = item.form.dataset[`preferences${state}`] || '';
            message.classList.toggle('assistant-send-status--error', state === 'Failed');
        }
        if (retry) retry.hidden = state !== 'Failed';
    }
    async function drainPreferences(key, entry) {
        // Serialize deliberate changes so a slower earlier response cannot
        // overwrite the final model/effort pair. Only these settings are sent.
        try {
            while (entry.pending) {
                const item = entry.pending;
                entry.pending = null;
                const data = new FormData();
                for (const [name, value] of Object.entries(item.values)) data.set(name, value);
                data.set('csrfmiddlewaretoken', item.csrf);
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 8000);
                try {
                    const response = await fetch(item.url, {method: 'POST', body: data,
                        headers: {'Accept': 'application/json'}, credentials: 'same-origin',
                        cache: 'no-store', keepalive: true, signal: controller.signal});
                    const result = await response.json();
                    if (!response.ok || Object.entries(item.values).some(([name, value]) => result[name] !== value)) {
                        throw new Error('Chat settings were not saved');
                    }
                    if (!entry.pending) preferenceStatus(item, 'Saved');
                } catch (_) {
                    if (!entry.pending) preferenceStatus(item, 'Failed');
                } finally { clearTimeout(timer); }
            }
        } finally {
            if (preferenceSaves.get(key) === entry) preferenceSaves.delete(key);
        }
    }
    function savePreferences(form) {
        const root = form?.closest('[data-assistant-content]');
        if (!root || !form.dataset.assistantPreferencesUrl) return;
        const values = {connection_id: form.elements.connection_id.value,
            model: form.elements.model.value, reasoning_effort: form.elements.reasoning_effort.value};
        const key = `${root.dataset.assistantUser}:${root.dataset.assistantSession}:${values.connection_id}`;
        const item = {form, values, url: form.dataset.assistantPreferencesUrl,
            csrf: form.elements.csrfmiddlewaretoken.value};
        preferenceStatus(item, 'Saving');
        let entry = preferenceSaves.get(key);
        if (entry) { entry.pending = item; return; }
        entry = {owner: root.dataset.assistantUser, pending: item};
        preferenceSaves.set(key, entry);
        entry.promise = drainPreferences(key, entry);
    }
    async function flushPreferences(root) {
        const user = root?.dataset.assistantUser || owner();
        await Promise.all([...preferenceSaves.values()].filter(entry => entry.owner === user).map(entry => entry.promise));
    }
    function initializeSettings(form) {
        const settings = form.querySelector('[data-assistant-settings]');
        if (!settings || settings._models) return;
        try {
            const data = form.querySelector(`script[id="${CSS.escape(settings.dataset.modelsId)}"]`);
            const models = JSON.parse(data?.textContent || '[]');
            settings._models = Array.isArray(models) ? models : [];
        } catch (_) { settings._models = []; }
        settings._efforts = Array.from(form.elements.reasoning_effort?.options || []);
        settings.addEventListener('toggle', () => { if (settings.open) sizeSettings(settings); });
        // Server-invalid selections remain visible for recovery. The next
        // deliberate model change applies that model's supported choices.
        if (!settings.querySelector('[aria-invalid="true"]')) settingsChoices(form);
        sizeSettings(settings);
    }
    function initialize(root = document, {view} = {}) {
        const roots = root.matches?.('[data-assistant-content]') ? [root] : root.querySelectorAll('[data-assistant-content]');
        roots.forEach(content => {
            const transcript = transcriptFor(content);
            if (!transcript) return;
            const first = !transcriptStates.has(transcript);
            if (first) {
                const state = {follow: true};
                transcriptStates.set(transcript, state);
                transcript.addEventListener('scroll', () => { state.follow = nearTail(transcript); }, {passive: true});
                // Composer growth and a mobile keyboard change the transcript's
                // height. Follow only while the reader is already at its tail.
                transcriptResize?.observe(transcript);
            }
            content.querySelectorAll('[data-assistant-send]').forEach(initializeSettings);
            content.querySelectorAll('[data-assistant-send] textarea').forEach(resizeMessage);
            if (view?.follow === false) {
                transcriptStates.get(transcript).follow = false;
                transcript.scrollTop = view.scrollTop;
            } else if (first || view?.follow) tail(transcript);
            if (view?.focus) {
                const selector = view.focus.submit ? '[data-assistant-send] button[type="submit"]'
                    : `[data-assistant-send] [name="${CSS.escape(view.focus.name)}"]`;
                const element = content.querySelector(selector);
                if (element && !element.disabled) {
                    const settings = element.closest('[data-assistant-settings]');
                    if (settings) { settings.open = true; sizeSettings(settings); }
                    element.focus({preventScroll: true});
                    if (element instanceof HTMLTextAreaElement && Number.isInteger(view.focus.selectionStart)) {
                        const start = Math.min(element.value.length, view.focus.selectionStart);
                        const end = Math.min(element.value.length, view.focus.selectionEnd);
                        element.setSelectionRange(start, end);
                    }
                }
            }
        });
    }
    function updateTranscript(transcript, update, force = false) {
        const follow = force || nearTail(transcript);
        update();
        if (follow) tail(transcript);
        else {
            const state = transcriptStates.get(transcript);
            if (state) state.follow = false;
        }
    }
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
        const view = capture(state.root);
        // Disabled controls can temporarily yield focus to body while sending.
        // Never steal it from another workspace or an intentionally chosen item.
        if (!view.focus && document.activeElement === document.body) view.focus = state.focusBefore;
        const destination = new URL(state.detail, location.origin);
        if (destination.origin !== location.origin || !destination.pathname.startsWith('/assistant/')) return;
        destination.searchParams.delete('model');
        destination.searchParams.delete('reasoning_effort');
        if (state.root.closest('#assistant-panel')) {
            await window.TuxedoAssistant?.refreshConversation(destination.pathname + destination.search, state.conversation, view);
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
        const currentView = capture(state.root);
        if (!currentView.focus && document.activeElement === document.body) currentView.focus = view.focus;
        state.root.replaceWith(document.adoptNode(next));
        window.TuxedoForms?.refresh(next);
        initialize(next, {view: currentView});
        history.replaceState(history.state, '', destination.pathname + destination.search);
        // Only a native assistant page is rebased. Never approve an edited
        // financial form because a utility-panel request completed beside it.
        document.dispatchEvent(new CustomEvent('tuxedo:workspace-navigated'));
    }
    async function send(form) {
        const root = form.closest('[data-assistant-content]');
        if (!root || active || form.getAttribute('aria-busy') === 'true') return;
        const controller = new AbortController(), data = new FormData(form);
        const shell = root.closest('[data-assistant-shell]');
        if (shell) {
            data.set('scope', shell.dataset.assistantScope || '');
            data.set('location', location.pathname + location.search);
        }
        const state = {root, form, owner: root.dataset.assistantUser, controller,
            csrf: data.get('csrfmiddlewaretoken'), model: data.get('model'), effort: data.get('reasoning_effort'), run: '',
            detail: '', conversation: '', stopped: false, completed: false, text: '', body: null,
            focusBefore: focusToken(root)};
        active = state;
        const transcript = transcriptFor(root);
        const controls = Array.from(form.querySelectorAll('input,select,textarea,button[type="submit"]'));
        controls.forEach(control => { control.disabled = true; });
        const settings = form.querySelector('[data-assistant-settings]');
        if (settings) settings.open = false;
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
                updateTranscript(transcript, () => {
                    transcript.querySelector('.assistant-empty')?.remove();
                    message(transcript, 'user', form.dataset.userLabel, data.get('content'));
                    state.body = message(transcript, 'assistant', form.dataset.assistantLabel);
                }, true);
                return;
            }
            if (!state.run) throw new Error('Missing stream owner');
            if (name === 'text') {
                if (typeof value.delta !== 'string' || state.text.length + value.delta.length > 16000) throw new Error('Invalid stream text');
                updateTranscript(transcript, () => {
                    state.text += value.delta; state.body.textContent = state.text;
                });
            } else if (name === 'done') {
                if (value.status !== 'completed') throw new Error('Incomplete stream');
                state.completed = true;
                updateTranscript(transcript, () => references(state.body.parentElement, value.references));
                notice(state, form.dataset.completed);
            } else if (name === 'error') {
                state.error = value.code || 'provider_error';
                updateTranscript(transcript, () => references(state.body.parentElement, value.references));
                throw new Error('Provider error');
            }
        }
        try {
            await flushPreferences(root);
            if (!valid(state) || controller.signal.aborted) return;
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
                    const view = capture(root);
                    root.replaceWith(document.adoptNode(next));
                    window.TuxedoForms?.refresh(next);
                    initialize(next, {view});
                    next.querySelector('[aria-invalid="true"]')?.focus({preventScroll: true});
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
            resizeMessage(form.elements.content);
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
                updateTranscript(transcript, () => state.body.parentElement.append(partial));
            } else state.body?.parentElement.remove();
            cancelRemote(state);
        } finally {
            clearTimeout(timer);
            if (active === state) active = null;
            if (valid(state) && state.completed) {
                // Keep the old composer locked until its authorized replacement
                // arrives: a follow-up typed during this GET would be discarded.
                form.querySelector('[data-assistant-stop]').hidden = true;
                await refresh(state).catch(() => {});
            }
            if (valid(state)) {
                controls.forEach(control => { control.disabled = false; });
                settingsChoices(form);
                form.querySelector('[data-assistant-stop]').hidden = true;
                form.removeAttribute('aria-busy');
                // Every deliberate new send gets a new key. A browser/network
                // replay of the old POST is deduplicated by the server.
                form.elements.request_id.value = crypto.randomUUID();
            }
        }
    }
    window.addEventListener('submit', event => {
        if (!event.target.matches('[data-assistant-send]')) return;
        event.preventDefault(); event.stopPropagation(); send(event.target);
    }, true);
    window.addEventListener('click', event => {
        if (event.target.closest('[data-assistant-stop]')) { event.preventDefault(); stop(); }
        const retry = event.target.closest('[data-assistant-preferences-retry]');
        if (retry) { event.preventDefault(); savePreferences(retry.closest('[data-assistant-send]')); }
        document.querySelectorAll('[data-assistant-settings][open]').forEach(settings => {
            if (!settings.contains(event.target)) settings.open = false;
        });
        const region = event.target.closest?.('#assistant-panel, [data-assistant-content]');
        if (!region) return;
        region.querySelectorAll('[data-assistant-menu][open]').forEach(menu => {
            if (!menu.contains(event.target)) menu.open = false;
        });
    }, true);
    document.addEventListener('keydown', event => {
        if (event.defaultPrevented) return;
        if (event.key === 'Escape' && !document.querySelector('dialog[open]')) {
            const region = event.target.closest?.('[data-assistant-content]');
            if (region && dismissMenu(region)) { event.preventDefault(); return; }
        }
        const textarea = event.target;
        if (!textarea.matches?.('[data-assistant-send] textarea') || event.key !== 'Enter'
                || event.shiftKey || event.altKey || event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        if (event.repeat || textarea.disabled || active || textarea.form?.getAttribute('aria-busy') === 'true') return;
        if (!textarea.value.trim()) return;
        textarea.form?.requestSubmit();
    });
    document.addEventListener('input', event => {
        if (event.target.matches?.('[data-assistant-send] textarea')) {
            resizeMessage(event.target);
            const settings = event.target.form.querySelector('[data-assistant-settings]');
            if (settings) sizeSettings(settings);
        }
    });
    document.addEventListener('change', event => {
        if (event.target.matches?.('[data-assistant-send] select[name="model"], [data-assistant-send] select[name="reasoning_effort"]')) {
            settingsChoices(event.target.form, {changed: event.target.name === 'model'});
            if (event.target.name === 'reasoning_effort') {
                event.target.form.querySelector('[data-assistant-settings-notice]').textContent = '';
            }
            savePreferences(event.target.form);
        }
    });
    document.addEventListener('focusin', event => {
        document.querySelectorAll('[data-assistant-settings][open]').forEach(settings => {
            if (!settings.contains(event.target)) settings.open = false;
        });
    });
    function resizeSettings() { document.querySelectorAll('[data-assistant-settings][open]').forEach(sizeSettings); }
    window.addEventListener('resize', resizeSettings);
    window.visualViewport?.addEventListener('resize', resizeSettings);
    document.addEventListener('htmx:beforeSwap', event => {
        if (active && event.detail.target === document.body) stop();
    });
    window.addEventListener('pagehide', stop);
    document.addEventListener('DOMContentLoaded', () => initialize());
    document.addEventListener('htmx:afterSwap', event => initialize(event.detail.target));
    if (document.readyState !== 'loading') initialize();
    window.TuxedoAssistantChat = {stop, initialize, capture, dismissMenu, flushPreferences,
        refreshSettings(form) { settingsChoices(form, {changed: true}); },
        isStreamingWithin(root) { return !!(active && !active.completed && root?.contains(active.root)); },
        cancelWithin(root) { if (active && root?.contains(active.root)) stop(); }};
})();
