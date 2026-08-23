// Mobile fullscreen overlay menu (Final Design System §0/§8).
//
// The overlay lives in partials/navbar_app.html: #mobile-menu starts
// translated off-screen (`translate-x-full`) and slides in over 500ms when
// toggled. Every element that should close the overlay carries one of the
// hooks below:
//   * #menu-btn       — hamburger in the navbar (opens)
//   * #close-menu-btn — X button inside the overlay (closes)
//   * .mobile-link    — any navigation link (closes after navigating)
//
// While the overlay is open, the body scroll and background focus are locked.
// `aria-expanded` is kept in sync and Tab stays inside the modal dialog.
(function () {
    function setBackgroundInert(mobileMenu, inert) {
        Array.prototype.forEach.call(document.body.children, function (element) {
            if (element === mobileMenu || element.tagName === 'SCRIPT') return;
            if (inert) {
                if (!element.hasAttribute('inert')) {
                    element.setAttribute('data-mobile-menu-inert', '');
                    element.setAttribute('inert', '');
                }
            } else if (element.hasAttribute('data-mobile-menu-inert')) {
                element.removeAttribute('inert');
                element.removeAttribute('data-mobile-menu-inert');
            }
        });
    }

    function focusableElements(mobileMenu) {
        return Array.prototype.filter.call(
            mobileMenu.querySelectorAll('a[href], button:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'),
            function (element) {
                return !element.hasAttribute('inert') && element.getAttribute('aria-hidden') !== 'true';
            }
        );
    }

    function setMenu(open, restoreFocus) {
        var menuBtn = document.getElementById('menu-btn');
        var closeMenuBtn = document.getElementById('close-menu-btn');
        var mobileMenu = document.getElementById('mobile-menu');
        if (!mobileMenu) return;

        mobileMenu.classList.toggle('translate-x-full', !open);
        mobileMenu.toggleAttribute('inert', !open);
        mobileMenu.setAttribute('aria-hidden', String(!open));
        setBackgroundInert(mobileMenu, open);
        document.body.style.overflow = open ? 'hidden' : '';
        [menuBtn, closeMenuBtn].forEach(function (btn) {
            if (btn) btn.setAttribute('aria-expanded', String(open));
        });
        if (open && closeMenuBtn) closeMenuBtn.focus();
        if (!open && restoreFocus && menuBtn) menuBtn.focus();
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('#menu-btn')) {
            setMenu(true, false);
        } else if (event.target.closest('#close-menu-btn')) {
            setMenu(false, true);
        } else if (event.target.closest('.mobile-link')) {
            setMenu(false, false);
        }
    });

    document.addEventListener('keydown', function (event) {
        var mobileMenu = document.getElementById('mobile-menu');
        if (!mobileMenu) return;
        if (mobileMenu.classList.contains('translate-x-full')) return;

        if (event.key === 'Escape') {
            event.preventDefault();
            setMenu(false, true);
            return;
        }

        if (event.key !== 'Tab') return;
        var focusable = focusableElements(mobileMenu);
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
})();
