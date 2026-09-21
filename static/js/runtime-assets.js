/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoRuntimeAssets) return;
    const revision = document.head.querySelector('meta[name="tuxedo-assets"]')?.content;
    document.addEventListener('htmx:beforeSend', event => {
        if (!revision) return;
        const path = event.detail.requestConfig?.path;
        if (path && new URL(path, window.location.href).origin !== window.location.origin) return;
        // beforeSend occurs after xhr.open and HTMX's noHeaders processing.
        // Keep the current document's version through body-only swaps.
        event.detail.xhr.setRequestHeader('X-Tuxedo-Assets', revision);
    });
    window.TuxedoRuntimeAssets = { revision };
}());
