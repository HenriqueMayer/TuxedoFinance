(function () {
    var menus = document.querySelectorAll('[data-project-menu]');

    function closeMenu(menu) {
        menu.open = false;
        menu.querySelectorAll('details[open]').forEach(function (nestedMenu) {
            nestedMenu.open = false;
        });
    }

    document.addEventListener('click', function (event) {
        menus.forEach(function (menu) {
            if (menu.open && !menu.contains(event.target)) {
                closeMenu(menu);
            }
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;

        menus.forEach(function (menu) {
            if (!menu.open) return;
            closeMenu(menu);
            menu.querySelector(':scope > summary').focus();
        });
    });
})();
