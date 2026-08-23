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
// While the overlay is open the body scroll is locked so the page behind
// does not move. `aria-expanded` on both buttons is kept in sync for
// screen readers.
(function () {
    function setMenu(open, restoreFocus) {
        var menuBtn = document.getElementById('menu-btn');
        var closeMenuBtn = document.getElementById('close-menu-btn');
        var mobileMenu = document.getElementById('mobile-menu');
        if (!mobileMenu) return;

        mobileMenu.classList.toggle('translate-x-full', !open);
        mobileMenu.toggleAttribute('inert', !open);
        mobileMenu.setAttribute('aria-hidden', String(!open));
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

    // Safety net: Escape closes the overlay and restores scrolling.
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        var mobileMenu = document.getElementById('mobile-menu');
        if (!mobileMenu) return;
        if (mobileMenu.classList.contains('translate-x-full')) return;
        setMenu(false, true);
    });
})();
