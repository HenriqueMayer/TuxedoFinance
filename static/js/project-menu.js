(function () {
    function closeMenu(menu) {
        menu.open = false;
        menu.querySelectorAll('details[open]').forEach(function (nestedMenu) {
            nestedMenu.open = false;
        });
    }

    document.addEventListener('click', function (event) {
        document.querySelectorAll('[data-project-menu]').forEach(function (menu) {
            if (menu.open && !menu.contains(event.target)) {
                closeMenu(menu);
            }
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;

        document.querySelectorAll('[data-project-menu]').forEach(function (menu) {
            if (!menu.open) return;
            closeMenu(menu);
            menu.querySelector(':scope > summary').focus();
        });
    });
})();
