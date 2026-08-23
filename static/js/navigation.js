/* Tuxedo Finance — HTMX navigation and chart-swap continuity. */
(function () {
    'use strict';

    var preservedChartView = null;

    function isChartTarget(target) {
        return target && (
            target.id === 'reports-charts' ||
            target.id === 'investments-charts'
        );
    }

    function scrollToAnchor(id) {
        var element = document.getElementById(id);
        if (element) element.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    function finishNavigation() {
        document.body.removeAttribute('aria-busy');
    }

    document.addEventListener('htmx:beforeRequest', function (event) {
        if (event.detail.target === document.body) {
            document.body.setAttribute('aria-busy', 'true');
            return;
        }
        if (!isChartTarget(event.detail.target)) return;

        var active = document.activeElement;
        var trigger = event.detail.elt;
        preservedChartView = {
            top: window.scrollY,
            focusId: active && active.id ? active.id : null,
            scrollTarget: trigger && trigger.dataset
                ? trigger.dataset.scrollTarget
                : null,
        };
    });

    document.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target === document.body) {
            finishNavigation();
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
        if (!isChartTarget(event.detail.target) || !preservedChartView) return;

        var view = preservedChartView;
        preservedChartView = null;
        window.requestAnimationFrame(function () {
            if (view.scrollTarget) {
                scrollToAnchor(view.scrollTarget);
            } else {
                window.scrollTo(0, view.top);
            }
            if (view.focusId) {
                var field = document.getElementById(view.focusId);
                if (field) field.focus({preventScroll: true});
            }
        });
    });

    ['htmx:responseError', 'htmx:sendError', 'htmx:timeout'].forEach(function (name) {
        document.addEventListener(name, finishNavigation);
    });

    document.addEventListener('htmx:beforeHistorySave', finishNavigation);
})();
