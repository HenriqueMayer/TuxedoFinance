/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    if (window.TuxedoBankColors) return;
    function init() {
        document.querySelectorAll('[data-bank-colors]').forEach(palette => {
            if (palette.children.length) return;
            const input = document.getElementById(palette.dataset.inputId);
            document.querySelectorAll('#bank-color-palette option').forEach(option => {
                const button = document.createElement('button');
                button.type = 'button';button.className = 'bank-color-swatch';
                button.style.backgroundColor = option.value;
                button.setAttribute('aria-label', palette.dataset.colorLabel + ' ' + option.value);
                button.addEventListener('click', () => {input.value=option.value;input.dispatchEvent(new Event('input',{bubbles:true}));});
                palette.append(button);
            });
        });
    }
    window.TuxedoBankColors = {init};
    document.addEventListener('DOMContentLoaded',init);document.addEventListener('htmx:load',init);
})();
