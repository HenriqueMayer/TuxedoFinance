/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoLiveFilters) return;
    const states = new WeakMap();

    function controls(form) {
        return Array.from(form.elements).filter(field => field.name &&
            ['INPUT', 'SELECT', 'TEXTAREA'].includes(field.tagName) &&
            !['submit', 'button', 'reset', 'file', 'password'].includes(field.type));
    }
    function formUrl(form) {
        const url = new URL(form.action, location.href);
        url.search = '';
        for (const [key, value] of new FormData(form)) {
            const field = controls(form).find(item => item.name === key);
            if (typeof value === 'string' && value.trim() && value !== field?.dataset.liveDefault) {
                url.searchParams.append(key, value);
            }
        }
        return url;
    }
    function cancel(state) {
        clearTimeout(state.timer);
        state.controller?.abort();
        state.generation++;
    }
    function resetControls(form, url) {
        // Clear is an immediate deliberate edit. A new keystroke can supersede
        // its pending GET, but must compose with these reset values already.
        controls(form).forEach(field => {
            const values = url.searchParams.getAll(field.name);
            if (['checkbox', 'radio'].includes(field.type)) {
                // Empty-value radio choices represent “All” when a filter is
                // absent from the URL. Clear must restore that native choice.
                field.checked = values.includes(field.value) || (field.type === 'radio' &&
                    !values.length && field.value === (field.dataset.liveDefault ?? ''));
            } else if (field.tagName === 'SELECT' && field.multiple) {
                Array.from(field.options).forEach(option => { option.selected = values.includes(option.value); });
            } else {
                const fallback = field.dataset.liveDefault ?? (field.tagName === 'SELECT' ? field.options[0]?.value || '' : '');
                field.value = values[0] ?? fallback;
            }
            // Preferred dates own a nameless native picker. Notify only the
            // field's local synchronizer, never a bubbling filter listener.
            if (field.closest('[data-preferred-date-field]')) field.dispatchEvent(new Event('input'));
        });
        window.TuxedoForms?.refresh(form);
    }
    function refreshOrigins(sources, destination) {
        function origin(value) {
            if (!value?.startsWith('/') || value.startsWith('//')) return null;
            const parsed = new URL(value, location.origin);
            if (parsed.origin !== location.origin || !sources.some(source =>
                source.pathname === parsed.pathname && source.search === parsed.search)) return null;
            return destination.pathname + destination.search + parsed.hash;
        }
        // Controls and heading actions stay mounted. Their explicit return
        // contexts must nevertheless follow the newly displayed GET state.
        document.querySelectorAll('a[href]').forEach(link => {
            const target = new URL(link.href, location.href);
            if (target.origin !== location.origin) return;
            const previous = target.searchParams.get('next');
            const next = origin(previous);
            if (next !== null && next !== previous) {
                target.searchParams.set('next', next);
                link.setAttribute('href', target.pathname + target.search + target.hash);
                // Boosted anchors capture href during HTMX initialization.
                // Reprocess this anchor so activation follows its new context.
                window.htmx?.process(link);
            }
        });
        document.querySelectorAll('input[type="hidden"][name="next"]').forEach(field => {
            const next = origin(field.value);
            if (next !== null) field.value = next;
        });
    }
    function synchronize(form, incoming, restore) {
        const source = controls(incoming);
        controls(form).forEach(field => {
            const choice = ['checkbox', 'radio'].includes(field.type);
            // A choice group shares its name/type; its individual values remain
            // stable while fresh GETs restore only the selected/checked state.
            const other = source.find(item => item.name === field.name && item.type === field.type &&
                (!choice || item.value === field.value));
            if (!other) return;
            if (field.matches('select[data-live-options]')) field.replaceChildren(...Array.from(other.children, node => node.cloneNode(true)));
            if (restore || field.type === 'hidden' || field.hasAttribute('data-live-options')) {
                if (choice) field.checked = other.checked;
                else if (field.multiple) Array.from(field.options).forEach(option => { option.selected = Array.from(other.selectedOptions).some(item => item.value === option.value); });
                else field.value = other.value;
            }
            ['aria-invalid', 'aria-describedby'].forEach(name => {
                if (other.hasAttribute(name)) field.setAttribute(name, other.getAttribute(name));
                else field.removeAttribute(name);
            });
        });
        // Render server date errors beside the existing field, never replace a
        // partially typed date or its caret to display a validation response.
        form.querySelectorAll('[data-field-error]').forEach(node => node.remove());
        incoming.querySelectorAll('[data-field-error]').forEach(error => {
            const field = document.getElementById(error.id.split('-error-')[0]);
            const group = field?.closest('[data-preferred-date-field]') || field?.parentElement;
            if (group && form.contains(group)) {
                group.append(error.cloneNode(true));
                // A newly returned error must remain discoverable even if the
                // user folded the optional filters while the GET was pending.
                const disclosure = group.closest('details.filter-disclosure');
                if (disclosure) disclosure.open = true;
            }
        });
        window.TuxedoForms?.refresh(form);
    }
    function commitUrl(form, state, url, mode) {
        if (mode === 'history') return;
        const destination = url.pathname + url.search;
        if (destination === location.pathname + location.search) return;
        document.dispatchEvent(new CustomEvent('tuxedo:live-filters-before-history', {detail: {form, mode}}));
        const entry = {...history.state, htmx: true, tuxedoLiveFilters: form.id};
        const replacing = mode === 'text' && state.textPushed;
        if (replacing) history.replaceState(entry, '', destination);
        else history.pushState(entry, '', destination);
        document.dispatchEvent(new CustomEvent('tuxedo:history-entry', {detail: {replace: replacing}}));
        state.textPushed = mode === 'text';
    }
    async function update(form, url, mode) {
        const state = states.get(form);
        if (!state || url.origin !== location.origin || url.pathname !== new URL(form.action).pathname) return;
        cancel(state);
        const generation = state.generation;
        state.controller = new AbortController();
        const results = document.getElementById(form.dataset.liveResults);
        if (!results) return;
        results.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url.href, {
                signal: state.controller.signal,
                headers: {'X-Tuxedo-Assets': window.TuxedoRuntimeAssets?.revision || ''},
                credentials: 'same-origin',
            });
            const html = await response.text();
            if (generation !== state.generation || !form.isConnected) return;
            let finalUrl = new URL(response.url);
            const redirect = response.headers.get('HX-Redirect');
            if (redirect || finalUrl.pathname !== url.pathname) {
                const destination = redirect ? new URL(redirect, finalUrl) : finalUrl;
                if (destination.origin !== location.origin) throw new Error('Non-local filter redirect');
                location.assign(destination.href);
                return;
            }
            if (!response.ok) throw new Error('Filter request failed');
            const page = new DOMParser().parseFromString(html, 'text/html');
            const incomingForm = page.getElementById(form.id);
            const incomingResults = page.getElementById(results.id);
            if (!incomingForm || !incomingResults) throw new Error('Filter results missing');
            if (incomingForm.dataset.liveUrl && !incomingForm.querySelector('[data-field-error]')) {
                finalUrl = new URL(incomingForm.dataset.liveUrl, finalUrl);
            }
            controls(incomingForm).forEach(field => {
                if (finalUrl.searchParams.get(field.name) === '' ||
                    finalUrl.searchParams.get(field.name) === field.dataset.liveDefault) finalUrl.searchParams.delete(field.name);
            });
            const fragments = Array.from(document.querySelectorAll('[data-live-fragment]'))
                .filter(node => node.dataset.liveFragment === form.id && node.id);
            if (fragments.some(node => !page.getElementById(node.id))) throw new Error('Filter metadata missing');
            const active = document.activeElement;
            const focusId = active?.id;
            const top = scrollY, left = scrollX;
            synchronize(form, incomingForm, mode === 'history' || mode === 'link');
            const replacements = Array.from(new Set([results, ...fragments])).filter((node, index, nodes) =>
                !nodes.some((parent, parentIndex) => parentIndex !== index && parent.contains(node)));
            const disclosures = new Map();
            replacements.forEach(node => {
                const details = [...node.querySelectorAll('details[id]')];
                if (node.matches('details[id]')) details.unshift(node);
                details.filter(item => !item.matches('.compact-menu, [data-category-branch]'))
                    .forEach(item => disclosures.set(item.id, item.open));
            });
            replacements.forEach(node => {
                const replacement = page.getElementById(node.id);
                const details = [...replacement.querySelectorAll('details[id]')];
                if (replacement.matches('details[id]')) details.unshift(replacement);
                details.forEach(item => { if (disclosures.has(item.id)) item.open = disclosures.get(item.id); });
                node.replaceWith(replacement);
                window.htmx?.process(replacement);
                window.htmx?.trigger(replacement, 'htmx:load', {elt: replacement});
            });
            state.failed = false;
            form.querySelectorAll('[data-live-submit]').forEach(button => { button.hidden = true; });
            refreshOrigins([state.url, new URL(response.url)], finalUrl);
            commitUrl(form, state, finalUrl, mode);
            state.url = finalUrl;
            document.title = page.title;
            if (active && !active.isConnected) {
                const replacement = focusId && document.getElementById(focusId);
                (replacement || form.querySelector('[data-live-search]'))?.focus({preventScroll: true});
            }
            window.scrollTo({top, left, behavior: 'instant'});
            document.dispatchEvent(new CustomEvent('tuxedo:live-filters-updated', {
                detail: {form, url: finalUrl, results: document.getElementById(results.id), mode},
            }));
        } catch (error) {
            if (error.name !== 'AbortError' && generation === state.generation && form.isConnected) {
                // Native GET remains a complete recovery path on network/server
                // failure; the helper never retries an operation or a POST.
                form.querySelectorAll('[data-live-submit]').forEach(button => { button.hidden = false; });
                state.failed = true;
            }
        } finally {
            if (generation === state.generation) document.getElementById(results.id)?.removeAttribute('aria-busy');
        }
    }
    function initialize(root = document) {
        const forms = Array.from(root.querySelectorAll('form[data-live-filters]'));
        if (root.matches?.('form[data-live-filters]')) forms.unshift(root);
        forms.forEach(form => {
            if (states.has(form) || form.method.toLowerCase() !== 'get' || !form.id ||
                !document.getElementById(form.dataset.liveResults) || new URL(form.action).origin !== location.origin) return;
            states.set(form, {generation: 0, textPushed: false, failed: false, url: new URL(location.href)});
            form.querySelectorAll('[data-live-submit]').forEach(button => { button.hidden = true; });
            // HTMX's private history path is updated only by its own requests.
            // These pages deliberately use fresh GET restoration instead of
            // caching a live-filter DOM under HTMX's preceding URL.
            form.setAttribute('hx-history', 'false');
            history.replaceState({...history.state, htmx: true, tuxedoLiveFilters: form.id}, '', location.href);
        });
    }
    document.addEventListener('input', event => {
        const field = event.target.closest('[data-live-search]');
        const form = field?.form;
        const state = states.get(form);
        if (!state || !field.name) return;
        cancel(state);
        if (event.isComposing) return;
        state.timer = setTimeout(() => update(form, formUrl(form), 'text'), 300);
    });
    document.addEventListener('compositionend', event => {
        if (event.target.matches('[data-live-search]')) event.target.dispatchEvent(new Event('input', {bubbles: true}));
    });
    document.addEventListener('keydown', event => {
        const field = event.target;
        const state = states.get(field.form);
        if (!state || state.failed || !field.matches('[data-live-search]') ||
            event.key !== 'Enter' || event.isComposing) return;
        event.preventDefault();
        state.textPushed = false;
        update(field.form, formUrl(field.form), 'submit');
    });
    document.addEventListener('change', event => {
        const field = event.target;
        const form = field.form;
        const state = states.get(form);
        if (!state || !field.name || field.matches('[data-live-search]') ||
            !field.closest('[data-live-change]')) return;
        state.textPushed = false;
        update(form, formUrl(form), 'change');
    });
    document.addEventListener('focusout', event => {
        const form = event.target.form;
        if (event.target.matches('[data-live-search]') && states.has(form)) states.get(form).textPushed = false;
    });
    document.addEventListener('submit', event => {
        const form = event.target;
        const state = states.get(form);
        if (!state || state.failed) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        state.textPushed = false;
        update(form, formUrl(form), 'submit');
    }, true);
    document.addEventListener('click', event => {
        const link = event.target.closest('a[data-live-link]');
        if (!link || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target) return;
        const form = document.getElementById(link.dataset.liveLink);
        const state = states.get(form);
        if (!state) return;
        let url = new URL(link.href, location.href);
        if (url.origin !== location.origin || url.pathname !== new URL(form.action).pathname) return;
        let mode = 'link';
        if (link.hasAttribute('data-live-set')) {
            const value = link.hasAttribute('data-live-value') ? link.dataset.liveValue : url.searchParams.get(link.dataset.liveSet);
            url = formUrl(form);
            if (value) url.searchParams.set(link.dataset.liveSet, value);
            else url.searchParams.delete(link.dataset.liveSet);
            (link.dataset.liveClear || '').split(' ').filter(Boolean).forEach(key => url.searchParams.delete(key));
            mode = 'link';
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        state.textPushed = false;
        if (link.hasAttribute('data-live-reset')) resetControls(form, url);
        update(form, url, mode);
    }, true);
    window.addEventListener('popstate', event => {
        const form = Array.from(document.querySelectorAll('form[data-live-filters]')).find(node =>
            states.has(node) && new URL(node.action).pathname === location.pathname);
        if (!form || !event.state?.tuxedoLiveFilters) return;
        event.stopImmediatePropagation();
        states.get(form).textPushed = false;
        update(form, new URL(location.href), 'history');
    }, true);
    window.TuxedoLiveFilters = {initialize};
    document.addEventListener('DOMContentLoaded', () => initialize());
    // Swapped controls are usable before HTMX's settle delay and htmx:load.
    // Initialize now so the first committed choice is never dropped.
    document.addEventListener('htmx:afterSwap', event => initialize(event.detail.target));
    document.addEventListener('htmx:load', event => initialize(event.detail.elt));
    document.addEventListener('htmx:historyRestore', () => initialize());
    if (document.readyState !== 'loading') initialize();
})();
