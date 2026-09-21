/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoCategories) {
        window.TuxedoCategories.init();
        return;
    }

    function setExpanded(button, expanded) {
        const children = document.getElementById(button.getAttribute('aria-controls'));
        if (!children || !button.closest('[data-category-tree]').contains(children)) return;
        children.hidden = !expanded;
        button.setAttribute('aria-expanded', String(expanded));
    }

    function init() {
        document.querySelectorAll('[data-category-tree]').forEach(tree => {
            tree.querySelectorAll('[data-category-toggle]').forEach(button => {
                button.hidden = false;
                button.parentElement.querySelector('[data-category-label]').hidden = true;
                // Preserve disclosure state from an HTMX history snapshot.
                setExpanded(button, button.getAttribute('aria-expanded') !== 'false');
            });
            tree.querySelectorAll('[data-category-actions]').forEach(actions => { actions.hidden = false; });
        });
    }

    document.addEventListener('click', event => {
        const button = event.target.closest('[data-category-toggle], [data-category-action]');
        const tree = button?.closest('[data-category-tree]');
        if (!tree) return;
        if (button.hasAttribute('data-category-toggle')) {
            setExpanded(button, button.getAttribute('aria-expanded') !== 'true');
        } else {
            const expanded = button.dataset.categoryAction === 'expand';
            tree.querySelectorAll('[data-category-toggle]').forEach(toggle => setExpanded(toggle, expanded));
        }
    });
    window.TuxedoCategories = { init };
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:historyRestore', init);
    init();
}());
