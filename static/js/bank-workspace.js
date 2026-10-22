/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoBankWorkspace) return;
    window.TuxedoBankWorkspace = true;
    let navigation = null;
    let overviewReturn = null;
    const owner = () => document.querySelector('main[data-workspace-user]')?.dataset.workspaceUser;

    document.addEventListener('click', event => {
        const link = event.target.closest?.('[data-bank-minimize], [data-bank-open]');
        if (!link) return;
        const user = owner();
        if (overviewReturn?.user !== user) overviewReturn = null;
        if (link.hasAttribute('data-bank-open')) {
            overviewReturn = {user, id: link.dataset.bankOpen, top: scrollY, left: scrollX};
        }
        navigation = {user, id: link.dataset.bankMinimize || link.dataset.bankOpen,
            minimize: link.hasAttribute('data-bank-minimize')};
    });
    document.addEventListener('htmx:afterSwap', event => {
        const target = event.detail?.target || event.target;
        if (target?.id !== 'banking-workspace') return;
        // This is an authorized GET navigation, rather than a background POST
        // fragment or filter change. Shared history owns its new draft baseline.
        document.dispatchEvent(new CustomEvent('tuxedo:workspace-navigated'));
        const destination = navigation;
        navigation = null;
        if (!destination || destination.user !== owner()) return;
        if (destination.minimize) {
            const link = document.getElementById(`bank-${destination.id}`);
            if (!link) return;
            if (overviewReturn?.id === destination.id && overviewReturn.user === owner()) {
                scrollTo({top: overviewReturn.top, left: overviewReturn.left, behavior: 'instant'});
            }
            link.focus({preventScroll: true});
            link.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});
        } else {
            const title = document.getElementById(`bank-detail-title-${destination.id}`);
            title?.focus({preventScroll: true});
            document.getElementById('bank-workspace-panel')?.scrollIntoView({block: 'start', behavior: 'instant'});
        }
    });
}());
