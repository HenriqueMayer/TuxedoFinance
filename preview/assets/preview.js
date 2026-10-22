(function () {
    'use strict';

    var root = document.documentElement;
    var views = Array.from(document.querySelectorAll('[data-workspace-view]'));
    var workspaceLinks = Array.from(document.querySelectorAll('[data-workspace-link]'));
    var themeButton = document.querySelector('[data-theme-toggle]');
    var demo = document.getElementById('demo');
    var selectedWorkspace = 'dashboard';
    var aliases = { reports: 'analytics', 'dashboard-preview': 'dashboard' };
    var landingAnchors = ['top', 'demo', 'assistant', 'how-it-works'];
    var workspaceParents = { 'analytics-investments': 'analytics', 'new-entry': 'transactions' };
    var pendingNavigation = null;
    var lastFocusedWorkspace = null;

    document.addEventListener('focusin', function (event) {
        lastFocusedWorkspace = event.target.closest('[data-workspace-view]');
    });
    document.addEventListener('pointerdown', function (event) {
        if (!event.target.closest('[data-workspace-view]')) lastFocusedWorkspace = null;
    });

    function hashId() {
        try { return decodeURIComponent(window.location.hash.slice(1)); }
        catch (error) { return ''; }
    }

    function workspaceForId(id) {
        var canonical = aliases[id] || id;
        return views.find(function (view) { return view.id === canonical; });
    }

    function updateLanguageLinks() {
        var id = hashId();
        var knownHash = workspaceForId(id) || landingAnchors.includes(id);
        document.querySelectorAll('.language-switch a').forEach(function (link) {
            if (!link.dataset.baseHref) link.dataset.baseHref = link.getAttribute('href').split('#')[0];
            link.setAttribute('href', link.dataset.baseHref + (knownHash ? window.location.hash : ''));
        });
    }

    function showWorkspace(navigated, savedPosition) {
        var id = hashId();
        var requestedView = workspaceForId(id);
        // Landing anchors keep the active demo; workspace hashes select its contents.
        // Unknown fragments and a fresh entry retain the predictable Home default.
        var current = requestedView ? requestedView.id
            : landingAnchors.includes(id) ? selectedWorkspace : 'dashboard';
        var destination = workspaceForId(current);
        if (!destination) return;
        var focused = document.activeElement;
        var focusOwner = focused && focused.closest('[data-workspace-view]');
        // Native fragment navigation may clear activeElement before hashchange.
        // Retain the activated link's intent and the workspace focus for history.
        if (!focusOwner && (focused === document.body || focused === root)) focusOwner = lastFocusedWorkspace;
        var intent = pendingNavigation && pendingNavigation.hash === window.location.hash ? pendingNavigation : null;
        pendingNavigation = null;
        var moveFocus = navigated && ((intent && intent.moveFocus) || (focusOwner && focusOwner !== destination));

        views.forEach(function (view) { view.hidden = view !== destination; });
        selectedWorkspace = destination.id;
        workspaceLinks.forEach(function (link) {
            var primary = link.matches('[data-primary-navigation]') || link.closest('[data-primary-navigation]');
            var owner = primary ? (workspaceParents[selectedWorkspace] || selectedWorkspace) : selectedWorkspace;
            if (link.dataset.workspaceLink === owner) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        });
        root.dataset.workspace = selectedWorkspace;
        updateLanguageLinks();

        if (moveFocus) {
            var heading = destination.querySelector('h3');
            if (heading) {
                heading.tabIndex = -1;
                heading.focus({ preventScroll: true });
            }
        } else if (intent && intent.link.getClientRects().length) {
            intent.link.focus({ preventScroll: true });
        }
        if (savedPosition) {
            // Switching demo contents is an in-place update. Restore after layout
            // changes so shorter panels cannot move the reader through scroll anchoring.
            window.scrollTo({ left: savedPosition.left, top: savedPosition.top, behavior: 'instant' });
        } else if (requestedView && demo) {
            window.requestAnimationFrame(function () {
                if (workspaceForId(hashId())) demo.scrollIntoView({ block: 'start', behavior: 'instant' });
            });
        }
    }

    if (views.length) {
        // All sections stay readable without JavaScript. URL fragments retain
        // Back/Forward while enhanced demo switches avoid native anchor scrolling.
        root.classList.add('workspace-preview');
        showWorkspace(false);
        window.addEventListener('hashchange', function () { showWorkspace(true); });
        workspaceLinks.forEach(function (link) {
            link.addEventListener('click', function (event) {
                if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                var linkHash = link.hash;
                var source = link.closest('[data-workspace-view]');
                pendingNavigation = {
                    hash: linkHash,
                    link: link,
                    moveFocus: event.detail === 0 || Boolean(source && source.id !== link.dataset.workspaceLink),
                };
                if (demo && demo.contains(link)) {
                    // Keep native links as the fallback, but avoid their fragment scroll
                    // for enhanced workspace switches. pushState retains Back/Forward.
                    event.preventDefault();
                    var savedPosition = { left: window.scrollX, top: window.scrollY };
                    if (linkHash !== window.location.hash) window.history.pushState(null, '', linkHash);
                    showWorkspace(true, savedPosition);
                } else if (linkHash && linkHash === window.location.hash) {
                    event.preventDefault();
                    showWorkspace(true);
                }
            });
        });
    } else updateLanguageLinks();

    var skipLink = document.querySelector('.skip-link');
    var main = document.getElementById('main');
    if (skipLink && main) {
        skipLink.addEventListener('click', function (event) {
            // Keyboard entry does not replace a deep link or its selected workspace.
            event.preventDefault();
            main.tabIndex = -1;
            main.focus({ preventScroll: true });
            main.scrollIntoView({ block: 'start', behavior: 'instant' });
        });
    }

    function updateThemeButton() {
        if (themeButton) themeButton.setAttribute('aria-pressed', String(root.dataset.theme === 'dark'));
    }

    if (themeButton) {
        updateThemeButton();
        themeButton.addEventListener('click', function () {
            var nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
            root.dataset.theme = nextTheme;
            try { localStorage.setItem('tuxedo-preview-theme', nextTheme); }
            catch (error) { /* The theme remains usable when browser storage is unavailable. */ }
            updateThemeButton();
        });
    }

    var search = document.getElementById('demo-search');
    var transactionRows = Array.from(document.querySelectorAll('[data-demo-transaction]'));
    var noResults = document.getElementById('demo-no-results');
    var searchTimer;

    function normalize(value) {
        return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim();
    }

    function filterTransactions() {
        var query = normalize(search.value);
        var matches = 0;
        transactionRows.forEach(function (row) {
            var visible = normalize(row.dataset.search || row.textContent).includes(query);
            row.hidden = !visible;
            if (visible) matches += 1;
        });
        if (noResults) noResults.hidden = matches > 0;
    }

    if (search) {
        search.addEventListener('input', function () {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(filterTransactions, 150);
        });
        search.addEventListener('search', function () {
            window.clearTimeout(searchTimer);
            filterTransactions();
        });
        if (search.form) search.form.addEventListener('submit', function (event) {
            event.preventDefault();
            window.clearTimeout(searchTimer);
            filterTransactions();
        });
    }

    var chatExamples = Array.from(document.querySelectorAll('[data-chat-example]'));
    var chatViews = Array.from(document.querySelectorAll('[data-chat-view]'));
    var confirmButton = document.getElementById('demo-confirm');
    var confirmation = document.getElementById('demo-confirmation');

    function showChatExample(example) {
        if (!['overview', 'simulate', 'budget'].includes(example)) return;
        chatExamples.forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.dataset.chatExample === example));
        });
        chatViews.forEach(function (view) { view.hidden = view.id !== 'chat-' + example; });
        if (confirmation) confirmation.hidden = true;
        if (confirmButton) confirmButton.hidden = false;
    }

    if (chatViews.length) {
        showChatExample('overview');
        chatExamples.forEach(function (button) {
            button.addEventListener('click', function () { showChatExample(button.dataset.chatExample); });
        });
        if (confirmButton && confirmation) confirmButton.addEventListener('click', function () {
            // This labelled scripted review changes only this demo's visible state.
            // It never submits a financial action, persists a record or calls a model.
            confirmation.hidden = false;
            confirmButton.hidden = true;
            confirmation.tabIndex = -1;
            confirmation.focus({ preventScroll: true });
        });
    }

    root.dataset.previewReady = 'true';
})();
