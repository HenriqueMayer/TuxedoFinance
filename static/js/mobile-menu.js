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
    var menuBtn = document.getElementById('menu-btn');
    var closeMenuBtn = document.getElementById('close-menu-btn');
    var mobileMenu = document.getElementById('mobile-menu');

    if (!mobileMenu) return;

    function toggleMenu() {
        var isClosed = mobileMenu.classList.contains('translate-x-full');
        mobileMenu.classList.toggle('translate-x-full', !isClosed);
        document.body.style.overflow = isClosed ? 'hidden' : '';
        [menuBtn, closeMenuBtn].forEach(function (btn) {
            if (btn) btn.setAttribute('aria-expanded', String(isClosed));
        });
    }

    if (menuBtn) menuBtn.addEventListener('click', toggleMenu);
    if (closeMenuBtn) closeMenuBtn.addEventListener('click', toggleMenu);
    document.querySelectorAll('.mobile-link').forEach(function (link) {
        link.addEventListener('click', toggleMenu);
    });

    // Safety net: Escape closes the overlay and restores scrolling.
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        if (mobileMenu.classList.contains('translate-x-full')) return;
        toggleMenu();
        if (menuBtn) menuBtn.focus();
    });
})();
