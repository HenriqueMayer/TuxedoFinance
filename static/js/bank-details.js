/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoBankDetails) return;
    window.TuxedoBankDetails = true;
    function revealAnchor() {
        if (!location.hash) return;
        let id;
        try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
        const target = document.getElementById(id);
        if (!target?.closest('.banking-workspace')) return;
        let revealed = false;
        for (let owner = target.parentElement; owner; owner = owner.parentElement) {
            if (owner.matches('details.bank-activity, details.reserve-disclosure, details.account-configuration') && !owner.open) {
                owner.open = true;
                revealed = true;
            }
        }
        // Native navigation reveals fragment ancestors; a boosted body swap
        // needs the same behavior before scrolling to the requested record.
        if (revealed) target.scrollIntoView({block: 'start', behavior: 'instant'});
    }
    document.addEventListener('DOMContentLoaded', revealAnchor);
    document.addEventListener('htmx:afterSettle', event => {
        if (event.detail.target === document.body) revealAnchor();
    });
    window.addEventListener('hashchange', revealAnchor);
    if (document.readyState !== 'loading') revealAnchor();
}());
