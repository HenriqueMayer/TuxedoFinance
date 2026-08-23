(function () {
    'use strict';

    var root = document.documentElement;
    var themeButton = document.querySelector('[data-theme-toggle]');
    var dialog = document.getElementById('image-dialog');
    var dialogImage = document.getElementById('dialog-image');
    var dialogClose = dialog && dialog.querySelector('[data-dialog-close]');
    var activeTrigger = null;

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
            if (activeTrigger) activeTrigger.focus();
            activeTrigger = null;
        });
    }
})();
