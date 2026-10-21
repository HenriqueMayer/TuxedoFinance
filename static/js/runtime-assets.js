/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoRuntimeAssets) return;
    function discardDomHistory() {
        // Older releases cached private HTML by URL, without a user identity.
        // Purge it before HTMX handles history, including entries left by an
        // older document in this tab.
        try { sessionStorage.removeItem('htmx-history-cache'); } catch (_) { /* Storage may be unavailable. */ }
    }
    discardDomHistory();
    window.addEventListener('popstate', discardDomHistory, true);
    const revision = document.head.querySelector('meta[name="tuxedo-assets"]')?.content;
    let pendingHistory = null;
    function abortPendingHistory() {
        const previous = pendingHistory;
        pendingHistory = null;
        if (previous) previous.abort();
    }
    document.addEventListener('htmx:beforeSend', event => {
        // A confirmed body request supersedes the pending history response.
        // beforeRequest/popstate can still be cancelled by departure checks.
        if (event.detail.target === document.body) abortPendingHistory();
        if (!revision) return;
        const path = event.detail.requestConfig?.path;
        if (path && new URL(path, window.location.href).origin !== window.location.origin) return;
        // beforeSend occurs after xhr.open and HTMX's noHeaders processing.
        // Keep the current document's version through body-only swaps.
        event.detail.xhr.setRequestHeader('X-Tuxedo-Assets', revision);
    });
    document.addEventListener('htmx:historyCacheMiss', event => {
        if (event.defaultPrevented) return;
        const xhr = event.detail.xhr;
        // History requests bypass HTMX's ordinary request synchronization.
        // Keep only the latest authorized GET, without caching private HTML.
        abortPendingHistory();
        pendingHistory = xhr;
        xhr.addEventListener('loadend', () => {
            if (pendingHistory === xhr) pendingHistory = null;
        }, {once: true});
        // HTMX's history GET bypasses beforeSend and must request full HTML.
        if (revision) xhr.setRequestHeader('X-Tuxedo-Assets', revision);
    });
    document.addEventListener('htmx:historyCacheMissLoad', event => {
        const {xhr, path} = event.detail;
        const redirect = xhr.getResponseHeader('HX-Redirect');
        const destination = new URL(redirect || xhr.responseURL, location.href);
        // The history loader does not follow HX-Redirect or update its URL
        // after a login redirect. Finish either recovery with a native GET so
        // login forms post to their own URL and changed assets reach the head.
        if (destination.origin === location.origin &&
                (redirect || destination.href !== new URL(path, location.href).href)) {
            location.replace(destination.href);
        }
    });
    window.TuxedoRuntimeAssets = { revision };
}());
