(function () {
    'use strict';

    var root = document.documentElement;
    var themeButton = document.querySelector('[data-theme-toggle]');
    var dialog = document.getElementById('image-dialog');
    var dialogImage = document.getElementById('dialog-image');
    var dialogClose = dialog && dialog.querySelector('[data-dialog-close]');
    var activeTrigger = null;
    var views = Array.from(document.querySelectorAll('[data-workspace-view]'));
    var workspaceLinks = Array.from(document.querySelectorAll('[data-workspace-link]'));

    function targetForHash() {
        var id;
        try { id = decodeURIComponent(window.location.hash.slice(1)); } catch (error) { id = ''; }
        var target = id && document.getElementById(id);
        var view = target && target.closest('[data-workspace-view]');
        return { target: target, view: view || document.getElementById('dashboard') };
    }

    function showWorkspace(navigated) {
        var destination = targetForHash();
        if (!destination.view || !views.includes(destination.view)) return;
        var focused = document.activeElement;
        var focusOwner = focused && focused.closest('[data-workspace-view]');
        var moveFocus = focusOwner && focusOwner !== destination.view;
        if (dialog && dialog.open) {
            dialog.close();
            moveFocus = true;
        }
        views.forEach(function (view) { view.hidden = view !== destination.view; });
        var current = destination.view.id;
        workspaceLinks.forEach(function (link) {
            // Secondary areas keep their parent selected in primary navigation.
            var parent = { reports: 'dashboard', 'new-entry': 'transactions' };
            var owner = link.closest('[data-primary-navigation]') ? (parent[current] || current) : current;
            if (link.dataset.workspaceLink === owner) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        });
        document.querySelectorAll('.language-switch a').forEach(function (link) {
            if (!link.dataset.baseHref) link.dataset.baseHref = link.getAttribute('href').split('#')[0];
            link.href = link.dataset.baseHref + (window.location.hash && destination.target
                ? window.location.hash : '');
        });
        root.dataset.workspace = current;
        if (moveFocus) {
            var heading = destination.view.querySelector('h1, h2');
            if (heading) {
                heading.tabIndex = -1;
                heading.focus({ preventScroll: true });
            }
        }
        if (navigated) {
            window.requestAnimationFrame(function () {
                if (destination.target && destination.target !== destination.view) {
                    destination.target.scrollIntoView({ block: 'start', behavior: 'instant' });
                } else window.scrollTo({ top: 0, behavior: 'instant' });
            });
        }
    }

    if (views.length) {
        // Native anchors and complete sections remain the no-JavaScript tour.
        // Enhancement changes only visibility; Back/Forward keeps native hashes.
        root.classList.add('workspace-preview');
        showWorkspace(false);
        window.addEventListener('hashchange', function () { showWorkspace(true); });
    }

    var skipLink = document.querySelector('.skip-link');
    var main = document.getElementById('main');
    if (skipLink && main) {
        skipLink.addEventListener('click', function (event) {
            // Move keyboard focus without replacing the selected workspace hash.
            event.preventDefault();
            main.focus({ preventScroll: true });
            main.scrollIntoView({ block: 'start', behavior: 'instant' });
        });
    }

    function updateThemeButton() {
        if (!themeButton) return;
        var isDark = root.dataset.theme === 'dark';
        themeButton.setAttribute('aria-pressed', String(isDark));
    }

    if (themeButton) {
        updateThemeButton();
        themeButton.addEventListener('click', function () {
            var nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
            root.dataset.theme = nextTheme;
            try {
                localStorage.setItem('tuxedo-preview-theme', nextTheme);
            } catch (error) {
                /* The selected theme still applies for this page view. */
            }
            updateThemeButton();
        });
    }

    document.querySelectorAll('[data-lightbox]').forEach(function (trigger) {
        trigger.addEventListener('click', function (event) {
            if (!dialog || typeof dialog.showModal !== 'function') return;
            event.preventDefault();
            activeTrigger = trigger;
            var thumbnail = trigger.querySelector('img');
            dialogImage.src = trigger.href;
            dialogImage.alt = thumbnail ? thumbnail.alt : '';
            dialog.showModal();
            if (dialogClose) dialogClose.focus();
        });
    });

    if (dialog) {
        if (dialogClose) {
            dialogClose.addEventListener('click', function () {
                dialog.close();
            });
        }
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) dialog.close();
        });
        dialog.addEventListener('close', function () {
            dialogImage.removeAttribute('src');
            if (activeTrigger && activeTrigger.getClientRects().length) activeTrigger.focus();
            activeTrigger = null;
        });
    }
    root.dataset.previewReady = 'true';
})();
