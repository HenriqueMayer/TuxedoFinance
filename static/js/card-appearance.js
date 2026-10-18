/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoCardAppearance) {
        window.TuxedoCardAppearance.initialize();
        return;
    }
    const initialized = new WeakSet();
    const color = (value, fallback = '#253330') => /^#[0-9a-f]{6}$/i.test(value || '') ? value.toUpperCase() : fallback;
    const rotation = value => /^\d+$/.test(value || '') && Number(value) <= 359 ? Number(value) : null;
    const wrap = value => ((Math.round(value) % 360) + 360) % 360;

    function angleControl(input, owner) {
        // An invalid bound value keeps its ordinary field and server error for recovery.
        if (!input || !owner || rotation(input.value) === null) return null;
        const label = owner.querySelector(`label[for="${input.id}"]`);
        if (!label) return null;
        const control = document.createElement('div');
        control.className = 'card-angle-adjustment';
        const dial = document.createElement('button');
        dial.type = 'button';
        dial.id = `${input.id}-dial`;
        dial.className = 'card-angle-dial';
        dial.dataset.cardAngleDial = '';
        dial.setAttribute('role', 'slider');
        dial.setAttribute('aria-valuemin', '0');
        dial.setAttribute('aria-valuemax', '359');
        if (!label.id) label.id = `${input.id}-label`;
        dial.setAttribute('aria-labelledby', label.id);
        label.htmlFor = dial.id;
        const scale = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        scale.setAttribute('viewBox', '0 0 100 100');
        scale.setAttribute('aria-hidden', 'true');
        scale.classList.add('card-angle-scale');
        for (let tick = 0; tick < 12; tick += 1) {
            const radians = tick * Math.PI / 6;
            const line = document.createElementNS(scale.namespaceURI, 'line');
            const inner = tick % 3 === 0 ? 35 : 38;
            line.setAttribute('x1', 50 + Math.sin(radians) * inner);
            line.setAttribute('y1', 50 - Math.cos(radians) * inner);
            line.setAttribute('x2', 50 + Math.sin(radians) * 42);
            line.setAttribute('y2', 50 - Math.cos(radians) * 42);
            scale.append(line);
        }
        const hand = document.createElement('span');
        hand.className = 'card-angle-hand';
        hand.setAttribute('aria-hidden', 'true');
        const handle = document.createElement('span');
        hand.append(handle);
        dial.append(scale, hand);
        const value = document.createElement('span');
        value.className = 'card-angle-value';
        value.setAttribute('aria-hidden', 'true');
        control.append(dial, value);
        input.insertAdjacentElement('afterend', control);
        input.hidden = true;
        let pointer = null;

        function release() {
            const activePointer = pointer;
            pointer = null;
            delete dial.dataset.dragging;
            if (activePointer !== null && dial.hasPointerCapture(activePointer)) dial.releasePointerCapture(activePointer);
        }

        function sync() {
            const degrees = rotation(input.value);
            // Authorized draft restoration can also bring back an invalid
            // number. Reveal it for recovery without hiding a focused editor.
            const nativeRecovery = degrees === null || (!input.hidden && document.activeElement === input);
            input.hidden = !nativeRecovery;
            control.hidden = nativeRecovery;
            label.htmlFor = nativeRecovery ? input.id : dial.id;
            if (degrees !== null) {
                dial.style.setProperty('--card-dial-angle', `${degrees}deg`);
                dial.setAttribute('aria-valuenow', String(degrees));
                dial.setAttribute('aria-valuetext', `${degrees}°`);
                value.textContent = `${degrees}°`;
            }
            ['aria-describedby', 'aria-invalid'].forEach(attribute => {
                if (input.hasAttribute(attribute)) dial.setAttribute(attribute, input.getAttribute(attribute));
                else dial.removeAttribute(attribute);
            });
            dial.disabled = input.disabled || nativeRecovery;
            if (dial.disabled) release();
        }

        function commit(degrees) {
            const next = String(wrap(degrees));
            if (input.disabled || input.value === next) return;
            input.value = next;
            sync();
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }

        function point(event) {
            const bounds = dial.getBoundingClientRect();
            const x = event.clientX - bounds.left - bounds.width / 2;
            const y = event.clientY - bounds.top - bounds.height / 2;
            // At the axle the angle is undefined; retaining it avoids sudden flips.
            if (Math.hypot(x, y) < 12) return false;
            commit(Math.atan2(x, -y) * 180 / Math.PI);
            return true;
        }

        dial.addEventListener('keydown', event => {
            if (event.altKey || event.ctrlKey || event.metaKey || dial.disabled) return;
            const current = rotation(input.value) ?? 135;
            const step = event.shiftKey ? 15 : 1;
            const moves = {
                ArrowRight: current + step, ArrowUp: current + step,
                ArrowLeft: current - step, ArrowDown: current - step,
                PageUp: current + 15, PageDown: current - 15, Home: 0, End: 359,
            };
            if (Object.hasOwn(moves, event.key)) {
                event.preventDefault();
                commit(Math.max(0, Math.min(359, moves[event.key])));
            } else if (event.key === ' ') event.preventDefault();
        });
        dial.addEventListener('pointerdown', event => {
            if (dial.disabled || pointer !== null || !event.isPrimary || event.button !== 0) return;
            event.preventDefault();
            dial.focus({preventScroll: true});
            if (!point(event)) return;
            pointer = event.pointerId;
            dial.dataset.dragging = '';
            dial.setPointerCapture(pointer);
        });
        dial.addEventListener('pointermove', event => {
            if (event.pointerId === pointer) point(event);
        });
        dial.addEventListener('pointerup', event => {
            if (event.pointerId !== pointer) return;
            point(event);
            release();
        });
        dial.addEventListener('pointercancel', release);
        dial.addEventListener('lostpointercapture', release);
        input.form.addEventListener('reset', release);
        input.form.addEventListener('tuxedo:restore', release);
        sync();
        return {sync};
    }

    function initialize(root = document) {
        root.querySelectorAll('[data-card-appearance-form]').forEach(form => {
            if (initialized.has(form)) return;
            initialized.add(form);
            const preview = form.querySelector('[data-card-appearance-preview]');
            const name = form.querySelector('[name="name"]');
            const namePreview = form.querySelector('[data-card-preview-name]');
            const fallbackName = preview.dataset.cardEmptyName;
            const toggle = form.querySelector('[name="use_gradient"]');
            const end = form.querySelector('[name="gradient_end"]');
            const angle = form.querySelector('[name="gradient_angle"]');
            const group = form.querySelector('[data-card-gradient-fields]');
            const dial = angleControl(angle, form.querySelector('[data-card-angle-control]'));

            function update() {
                dial?.sync();
                const start = color(new FormData(form).get('color'));
                preview.style.setProperty('--card-start', start);
                preview.style.setProperty('--card-end', toggle?.checked ? color(end.value, start) : start);
                const rotation = Number.parseInt(angle?.value, 10);
                preview.style.setProperty('--card-angle', `${Number.isInteger(rotation) && rotation >= 0 && rotation <= 359 ? rotation : 135}deg`);
                namePreview.textContent = name.value.trim() || fallbackName;
            }

            function updateGradient(deliberate) {
                if (!group || !toggle) return;
                window.TuxedoForms.setHidden(group, !toggle.checked, !deliberate);
                const inactive = group.hidden;
                if (deliberate && !toggle.checked) {
                    end.value = color(new FormData(form).get('color'));
                    angle.value = '135';
                }
                [end, angle].forEach(input => { input.disabled = inactive; });
                update();
            }

            form.addEventListener('input', update);
            form.addEventListener('change', event => {
                if (event.target === toggle) updateGradient(true);
                else update();
            });
            form.addEventListener('tuxedo:restore', () => updateGradient(false));
            form.addEventListener('reset', () => requestAnimationFrame(() => updateGradient(false)));
            updateGradient(false);
            update();
        });
    }
    window.TuxedoCardAppearance = {initialize};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initialize());
    else initialize();
    document.addEventListener('htmx:afterSwap', () => initialize());
})();
