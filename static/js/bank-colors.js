/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoBankColors) return;
    const initialized = new WeakSet();
    function init(root = document) {
        root.querySelectorAll('[data-color-picker]').forEach(owner => {
            if (initialized.has(owner)) return;
            const input = owner.querySelector('input[type="color"]');
            const palette = owner.querySelector('[data-color-presets]');
            if (!input || !palette) return;
            initialized.add(owner);
            owner.querySelectorAll('[data-color-palette] option').forEach(option => {
                if (!/^#[0-9a-f]{6}$/i.test(option.value)) return;
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'color-picker-preset';
                button.dataset.colorValue = option.value;
                button.setAttribute('aria-label', option.label);
                button.title = `${option.label} (${option.value})`;
                const swatch = document.createElement('span');
                swatch.style.setProperty('--color-preset', option.value);
                swatch.setAttribute('aria-hidden', 'true');
                button.append(swatch);
                button.addEventListener('click', () => {
                    input.value = option.value;
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                });
                palette.append(button);
            });
            function sync() {
                palette.querySelectorAll('button').forEach(button => {
                    button.setAttribute('aria-pressed', String(button.dataset.colorValue.toLowerCase() === input.value.toLowerCase()));
                    button.disabled = input.disabled;
                });
            }
            input.addEventListener('input', sync);
            input.addEventListener('change', sync);
            input.form?.addEventListener('reset', () => requestAnimationFrame(sync));
            input.form?.addEventListener('tuxedo:restore', sync);
            sync();
            palette.hidden = false;
        });
    }
    window.TuxedoBankColors = {init};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
    else init();
    document.addEventListener('htmx:load', () => init());
})();
