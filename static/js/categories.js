/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoCategories) { window.TuxedoCategories.init(); return; }
    const initialized = new WeakSet();
    function synchronize(branch) {
        branch.querySelector(':scope > summary[data-category-toggle]')?.setAttribute('aria-expanded', String(branch.open));
    }
    function init() {
        document.querySelectorAll('[data-category-tree]').forEach(tree => {
            tree.querySelectorAll('[data-category-branch]').forEach(branch => {
                synchronize(branch);
                if (initialized.has(branch)) return;
                initialized.add(branch);
                branch.addEventListener('toggle', () => synchronize(branch));
            });
            tree.querySelectorAll('[data-category-actions]').forEach(actions => { actions.hidden = false; });
        });
    }
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-category-action]');
        const tree = button?.closest('[data-category-tree]');
        if (!tree) return;
        tree.querySelectorAll('[data-category-branch]').forEach(branch => {
            branch.open = button.dataset.categoryAction === 'expand';
            synchronize(branch);
        });
    });
    window.TuxedoCategories = {init};
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:historyRestore', init);
    init();
}());
