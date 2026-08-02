/* CashFlow — light/dark theme toggle (PRD §9 — Design System).
 *
 * The matching FOUC snippet in `templates/base.html` reads `localStorage`
 * and the OS `prefers-color-scheme` *before* the stylesheet paints and
 * toggles the `dark` class on <html> so the first render is already in the
 * right theme. This file owns the only piece that needs the DOM: wiring the
 * navbar's `#theme-toggle` button so a click flips that class and persists
 * the choice. ~15 lines of vanilla JS — the only JavaScript in the project
 * beside the (browser-only) Tailwind Play CDN dev script. */
(function () {
    'use strict';

    function toggle() {
        var isDark = document.documentElement.classList.toggle('dark');
        try {
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        } catch (e) {
            /* Private-mode storage may throw; the class is already flipped,
             * so the session just does not remember the choice. */
        }
    }

    function init() {
        var btn = document.getElementById('theme-toggle');
        if (btn) {
            btn.addEventListener('click', toggle);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();