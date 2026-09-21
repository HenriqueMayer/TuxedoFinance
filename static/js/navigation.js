/* Tuxedo Finance — HTMX navigation and focused island-swap continuity. */
(function () {
    'use strict';

    var preservedIslandViews = new WeakMap();
    var preservedPageViews = new WeakMap();

    // A query/filter change is an update to the current page. Only navigation
    // to a different path should inherit the shell's show:window:top behavior.
    document.addEventListener('htmx:beforeSwap', function (event) {
        var detail = event.detail;
        if (detail.target !== document.body || !detail.shouldSwap || detail.isError) return;
        var destination = new URL(detail.xhr.responseURL, window.location.href);
        if (destination.origin !== window.location.origin ||
            destination.pathname !== window.location.pathname) return;

        var active = document.activeElement;
        preservedPageViews.set(detail.xhr, {
            top: window.scrollY,
            left: window.scrollX,
            path: window.location.pathname,
            focusId: active && active.id ? active.id : null,
        });
        detail.swapOverride = 'innerHTML show:none';
    });

    function isPreservedIsland(target) {
        return target && (
            target.id === 'reports-charts' ||
            target.id === 'investments-charts' ||
            target.id === 'investment-movements' ||
            target.hasAttribute('data-preserve-view')
        );
    }

    function scrollToAnchor(id) {
        var element = document.getElementById(id);
        if (element) element.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    function finishNavigation() {
        document.body.removeAttribute('aria-busy');
    }

    function restorePageView(view) {
        window.requestAnimationFrame(function () {
            if (view.cancelled || window.location.pathname !== view.path) return;
            var active = document.activeElement;
            if (view.focusId && (active === document.body || active.id === view.focusId)) {
                var control = document.getElementById(view.focusId);
                if (control) control.focus({preventScroll: true});
            }
            // The browser clamps this only if the new document is shorter.
            window.scrollTo({left: view.left, top: view.top, behavior: 'instant'});
        });
    }

    function restoreIslandView(view) {
        window.requestAnimationFrame(function () {
            var target = document.getElementById(view.targetId);
            if (view.cancelled || window.location.pathname !== view.path ||
                !view.parent.isConnected || !target || target.parentElement !== view.parent) return;
            if (view.scrollTarget) {
                scrollToAnchor(view.scrollTarget);
            } else {
                window.scrollTo({left: view.left, top: view.top, behavior: 'instant'});
            }
            var active = document.activeElement;
            if (view.focusId && (active === document.body || active.id === view.focusId)) {
                var field = document.getElementById(view.focusId);
                if (field) field.focus({preventScroll: true});
            }
        });
    }

    document.addEventListener('htmx:beforeRequest', function (event) {
        if (event.detail.target === document.body) {
            document.body.setAttribute('aria-busy', 'true');
            return;
        }
        if (!isPreservedIsland(event.detail.target)) return;

        var active = document.activeElement;
        var trigger = event.detail.elt;
        preservedIslandViews.set(event.detail.xhr, {
            top: window.scrollY,
            left: window.scrollX,
            path: window.location.pathname,
            targetId: event.detail.target.id,
            parent: event.detail.target.parentElement,
            focusId: active && active.id ? active.id : null,
            scrollTarget: trigger && trigger.dataset
                ? trigger.dataset.scrollTarget
                : null,
        });
    });

    document.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target === document.body) {
            finishNavigation();
            var pageView = preservedPageViews.get(event.detail.xhr);
            if (pageView) {
                restorePageView(pageView);
                return;
            }
            window.requestAnimationFrame(function () {
                var heading = document.querySelector('main h1');
                if (!heading) return;
                heading.setAttribute('tabindex', '-1');
                heading.focus({preventScroll: true});
                heading.addEventListener('blur', function () {
                    heading.removeAttribute('tabindex');
                }, {once: true});
            });
            return;
        }
        var view = preservedIslandViews.get(event.detail.xhr);
        if (view) restoreIslandView(view);
    });

    document.addEventListener('htmx:afterSettle', function (event) {
        var pageView = preservedPageViews.get(event.detail.xhr);
        if (pageView) {
            // Body swaps settle attributes too; their reflow can anchor the
            // viewport away from the position restored immediately after swap.
            preservedPageViews.delete(event.detail.xhr);
            restorePageView(pageView);
            return;
        }
        var view = preservedIslandViews.get(event.detail.xhr);
        if (!view) return;
        // HTMX settles class/style attributes after swapping. That last reflow
        // can trigger browser scroll anchoring even after the early restore.
        preservedIslandViews.delete(event.detail.xhr);
        restoreIslandView(view);
    });

    ['htmx:responseError', 'htmx:sendError', 'htmx:timeout', 'htmx:sendAbort'].forEach(function (name) {
        document.addEventListener(name, function (event) {
            var view = preservedIslandViews.get(event.detail.xhr);
            if (view) view.cancelled = true;
            var pageView = preservedPageViews.get(event.detail.xhr);
            if (pageView) pageView.cancelled = true;
            preservedIslandViews.delete(event.detail.xhr);
            preservedPageViews.delete(event.detail.xhr);
            finishNavigation();
        });
    });

    document.addEventListener('htmx:beforeHistorySave', finishNavigation);
})();
