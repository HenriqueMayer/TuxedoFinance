/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoAnalyticsNavigation) return;
    const queues = new WeakMap();
    const focusedResets = new WeakMap();

    function scopedLink(element) {
        if (!(element instanceof Element)) return null;
        const link = element.closest('a[data-analytics-param]');
        return link?.closest('[data-analytics-navigation]') ? link : null;
    }

    function destination(link, path) {
        const current = new URL(location.href);
        const proposed = new URL(path || link.getAttribute('href'), current);
        if (proposed.origin !== current.origin || proposed.pathname !== current.pathname) return null;
        // Each island owns one cursor. Its rendered links may predate changes
        // elsewhere, so take only that cursor from the link, never its snapshot
        // of unrelated criteria. Updating attributes preserves focus and panels.
        const parameter = link.dataset.analyticsParam;
        if (proposed.searchParams.has(parameter)) current.searchParams.set(parameter, proposed.searchParams.get(parameter));
        else current.searchParams.delete(parameter);
        current.hash = proposed.hash;
        return current.pathname + current.search + current.hash;
    }

    function refreshLinks() {
        document.querySelectorAll('[data-analytics-navigation] a[data-analytics-param]').forEach(link => {
            const path = destination(link);
            if (!path) return;
            link.setAttribute('href', path);
            if (link.hasAttribute('hx-get')) link.setAttribute('hx-get', path);
        });
    }

    function dispatchNext(root, queue) {
        if (queue.disposed || !root.isConnected || queue.pathname !== location.pathname) {
            queue.items.length = 0;
            return;
        }
        if (queue.busy) return;
        const intent = queue.items.shift();
        if (!intent) return;
        const target = document.getElementById(intent.targetId);
        const preferred = intent.sourceId ? document.getElementById(intent.sourceId) : null;
        const source = preferred?.matches(`a[data-analytics-param="${intent.parameter}"]`)
            ? preferred : target?.querySelector(`a[data-analytics-param="${intent.parameter}"]`);
        if (!source || !root.contains(source)) {
            dispatchNext(root, queue);
            return;
        }
        queue.busy = true;
        // A previous response can replace the original control. Keep cursor
        // intentions on this stable workspace, then resolve a connected source
        // before dispatch; HTMX's native queue would discard detached sources.
        Promise.resolve(window.htmx.ajax('GET', intent.path, {
            source, target, swap: 'outerHTML show:none',
            event: new Event('tuxedo:analytics-queued'),
        })).catch(() => {
            // HTMX owns request-error feedback. A failure must not block a later
            // independent choice or change the committed browser location.
        }).finally(() => {
            queue.busy = false;
            dispatchNext(root, queue);
        });
    }

    document.addEventListener('htmx:confirm', event => {
        const detail = event.detail;
        const link = scopedLink(detail.elt);
        if (!link || detail.verb !== 'get' || detail.triggeringEvent?.type === 'tuxedo:analytics-queued') return;
        event.preventDefault();
        const root = link.closest('[data-analytics-navigation]');
        let queue = queues.get(root);
        if (!queue) {
            queue = {busy: false, items: [], pathname: location.pathname};
            queues.set(root, queue);
        }
        queue.items.push({parameter: link.dataset.analyticsParam, path: detail.path,
            targetId: detail.target.id, sourceId: link.id});
        dispatchNext(root, queue);
    });

    document.addEventListener('htmx:configRequest', event => {
        const link = scopedLink(event.detail.elt);
        if (!link || event.detail.verb !== 'get') return;
        const path = destination(link, event.detail.path);
        if (path) event.detail.path = path;
        else event.preventDefault();
    });
    document.addEventListener('htmx:beforeRequest', event => {
        const link = scopedLink(event.detail.elt);
        if (link?.id === 'analytics-month-current' && document.activeElement === link) {
            focusedResets.set(event.detail.xhr, link.closest('[data-analytics-navigation]'));
        }
    });
    document.addEventListener('htmx:afterSettle', event => {
        const owner = focusedResets.get(event.detail.xhr);
        if (!owner) return;
        focusedResets.delete(event.detail.xhr);
        requestAnimationFrame(() => {
            // A completed reset disappears. Only replace its lost focus with
            // the month caption; background refreshes or deliberate focus moves
            // to another island must keep their own active control.
            if (!owner.isConnected || document.activeElement !== document.body ||
                owner.querySelector('#analytics-month-current')) return;
            const caption = owner.querySelector('#selected-period-heading');
            if (!caption) return;
            caption.setAttribute('tabindex', '-1');
            caption.focus({preventScroll: true});
            caption.addEventListener('blur', () => caption.removeAttribute('tabindex'), {once: true});
        });
    });
    document.addEventListener('htmx:beforeCleanupElement', event => {
        const root = event.target;
        if (!(root instanceof Element) || !root.matches('[data-analytics-navigation]')) return;
        const queue = queues.get(root);
        if (queue) {
            queue.disposed = true;
            queue.items.length = 0;
        }
        // HTMX removes listeners and its internal data during cleanup, but
        // does not abort this workspace's sync-owner XHR. Cancel before removal
        // so a late filter response cannot restore its URL after navigation.
        window.htmx.trigger(root, 'htmx:abort');
    });
    document.addEventListener('click', event => {
        if (scopedLink(event.target) && (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) {
            // Explicit hx-get controls do not inherit boosted-link modifier
            // handling. Preserve the browser's new-tab/window/download action.
            event.stopPropagation();
        }
    }, true);
    document.addEventListener('htmx:afterSwap', refreshLinks);
    document.addEventListener('htmx:historyRestore', refreshLinks);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refreshLinks);
    else refreshLinks();
    window.TuxedoAnalyticsNavigation = {refreshLinks};
}());
