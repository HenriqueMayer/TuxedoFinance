// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
(function () {
    'use strict';

    if (window.TuxedoPaperLayers) return;
    const owners = new Map();
    const namespace = 'http://www.w3.org/2000/svg';

    function initialize(owner) {
        if (!owner || owners.has(owner)) return;
        const svg = owner.querySelector('[data-bowtie-svg]');
        const whole = owner.querySelector('[data-bowtie-whole]');
        const map = owner.querySelector('[data-bowtie-map]');
        const definitions = [
            {name: 'left', x: 142, y: 220, dx: -34, dy: -4, turn: -4.5, depth: .3},
            {name: 'ledger', x: 142, y: 220, dx: 30, dy: -40, turn: -7, depth: .9},
            {name: 'right', x: 438, y: 220, dx: 36, dy: 8, turn: 4, depth: .45},
            {name: 'rings', x: 438, y: 220, dx: -16, dy: -35, turn: 7, depth: 1.15},
            {name: 'knot', x: 288, y: 220, dx: 2, dy: -28, turn: -4, depth: 1.5},
        ];
        // Missing preview markup leaves the original, static artwork intact.
        if (!svg || !whole || !map || definitions.some(plane =>
            !svg.querySelector(`#lab-paper-${plane.name}`) || !map.querySelector(`[data-bowtie-map-link="${plane.name}"]`))) return;
        const controller = new AbortController();
        const on = (node, type, listener, options = {}) =>
            node.addEventListener(type, listener, {...options, signal: controller.signal});
        let disposed = false;
        let layoutObserver = null, visibilityObserver = null;
        function destroy() {
            if (disposed) return;
            disposed = true;
            controller.abort();
            cancelAnimationFrame(frame);
            layoutObserver?.disconnect();
            visibilityObserver?.disconnect();
            owners.delete(owner);
            group.remove(); connectors.remove(); trigger.remove();
            whole.removeAttribute('display');
            map.inert = false;
            map.removeAttribute('aria-hidden');
            svg.setAttribute('role', 'img');
            svg.setAttribute('aria-label', originalLabel);
            for (const name of ['tabindex', 'aria-controls', 'aria-pressed', 'aria-expanded']) svg.removeAttribute(name);
            delete owner.dataset.paperEnhanced;
        }
        const originalLabel = svg.getAttribute('aria-label') || '';
        owners.set(owner, destroy);
        owner.dataset.paperEnhanced = 'true';
        // The original SVG stays a static image without enhancement. With
        // JavaScript, its painted form is the single control for the map.
        svg.setAttribute('role', 'button');
        svg.setAttribute('tabindex', '0');
        svg.setAttribute('aria-label', owner.dataset.bowtieLabel || 'Explore workspaces');
        svg.setAttribute('aria-controls', map.id);

        const preference = matchMedia('(prefers-reduced-motion: reduce)');
        const compact = matchMedia('(max-width: 1099px)');
        const connectors = document.createElementNS(namespace, 'g');
        connectors.setAttribute('data-bowtie-map-connectors', '');
        connectors.setAttribute('aria-hidden', 'true');
        connectors.setAttribute('pointer-events', 'none');
        svg.append(connectors);
        const group = document.createElementNS(namespace, 'g');
        group.setAttribute('data-bowtie-layers', '');
        group.setAttribute('aria-hidden', 'true');
        group.setAttribute('pointer-events', 'visiblePainted');
        svg.append(group);
        // Keep the painted closed silhouette as a stable hover target while
        // rotation moves the visible planes away from the entering pointer.
        const trigger = document.createElementNS(namespace, 'g');
        trigger.setAttribute('data-bowtie-trigger', '');
        trigger.setAttribute('aria-hidden', 'true');
        trigger.setAttribute('opacity', '0');
        trigger.setAttribute('pointer-events', 'visiblePainted');
        const triggerDrawing = document.createElementNS(namespace, 'use');
        triggerDrawing.setAttribute('href', '#lab-bowtie-drawing');
        trigger.append(triggerDrawing);
        svg.append(trigger);
        const planes = definitions.map(plane => {
            const node = document.createElementNS(namespace, 'g');
            node.setAttribute('data-bowtie-layer', plane.name);
            // Keep the fine printed lines out of the filled-paper shadow pass.
            if (['left', 'right', 'knot'].includes(plane.name)) node.setAttribute('class', 'lab-paper-plane');
            node.setAttribute('transform', 'translate(0 0)');
            const use = document.createElementNS(namespace, 'use');
            use.setAttribute('href', `#lab-paper-${plane.name}`);
            node.append(use);
            group.append(node);
            const connector = document.createElementNS(namespace, 'path');
            connector.setAttribute('data-bowtie-connector', plane.name);
            connector.setAttribute('fill', 'none');
            connector.setAttribute('stroke', 'currentColor');
            connector.setAttribute('stroke-width', '.9');
            connector.setAttribute('vector-effect', 'non-scaling-stroke');
            connector.setAttribute('opacity', '0');
            connectors.append(connector);
            return {...plane, node, connector, end: null, link: map.querySelector(`[data-bowtie-map-link="${plane.name}"]`)};
        });
        whole.setAttribute('display', 'none');

        const motion = {amount: 0, x: 0, y: 0};
        const velocity = {amount: 0, x: 0, y: 0};
        const target = {amount: 0, x: 0, y: 0};
        const pointerTarget = {amount: 0, x: 0, y: 0};
        let frame = 0, previous = 0;
        let pinned = false, visible = true, mouseActive = false, spacePressed = false;
        let origin = null, lastClient = null;
        let lastMouse = null, blockedAt = null;
        let hoveredLink = null, focusedLink = null;
        const closedScale = .88, openScale = .64;
        let openCenterX = compact.matches ? 290 : 125;
        let inverse = null, layoutScrollX = 0, layoutScrollY = 0;

        function clamp(value, minimum, maximum) {
            return Math.max(minimum, Math.min(maximum, value));
        }
        function smooth(start, end, value) {
            const unit = clamp((value - start) / (end - start), 0, 1);
            return unit * unit * (3 - 2 * unit);
        }
        function spring(value, speed, goal, delta, frequency) {
            const distance = value - goal;
            const step = (speed + distance * frequency) * delta;
            const decay = Math.exp(-frequency * delta);
            return [goal + (distance + step) * decay, (speed - frequency * step) * decay];
        }
        function controlState() {
            svg.setAttribute('aria-pressed', String(pinned));
            svg.setAttribute('aria-expanded', String(map.getAttribute('aria-hidden') !== 'true'));
        }
        function reveal(open) {
            owner.dataset.bowtieMapOpen = String(open);
            map.inert = !open;
            map.setAttribute('aria-hidden', String(!open));
            controlState();
        }
        function restore(returnFocus = false) {
            // Visible layout/preference resets must not strand keyboard focus
            // in the hidden index. Offscreen navigation resets leave focus
            // alone so native fragment scrolling keeps its destination.
            if (returnFocus && map.contains(document.activeElement)) svg.focus({preventScroll: true});
            cancelAnimationFrame(frame);
            frame = 0; previous = 0; pinned = false; mouseActive = false; spacePressed = false;
            for (const key of Object.keys(motion)) motion[key] = velocity[key] = target[key] = 0;
            // Reduced motion retains a useful, fully unfolded diagram without
            // requesting a frame. Normal resets return to the closed object.
            if (preference.matches) motion.amount = target.amount = 1;
            pointerTarget.amount = pointerTarget.x = pointerTarget.y = 0;
            origin = null; lastClient = null;
            hoveredLink = focusedLink = null;
            delete owner.dataset.bowtieHighlight;
            reveal(false);
            paint();
            owner.dataset.bowtieState = 'resting';
            controlState();
        }
        function run() {
            if (!disposed && !frame && visible && !document.hidden && !preference.matches) frame = requestAnimationFrame(draw);
        }
        function paint() {
            const angle = -9 + 99 * motion.amount;
            // The full-size resting object owns the illustration column;
            // opening scales and shifts it aside using the same spring as rotation.
            const centerX = 290 + (openCenterX - 290) * motion.amount;
            const scale = closedScale + (openScale - closedScale) * motion.amount;
            const radians = angle * Math.PI / 180;
            const cosine = Math.cos(radians), sine = Math.sin(radians);
            group.setAttribute('transform', `translate(${centerX} 220) rotate(${angle.toFixed(3)}) scale(${scale.toFixed(4)}) translate(-290 -220)`);
            trigger.setAttribute('transform', `translate(290 220) rotate(-9) scale(${closedScale}) translate(-290 -220)`);
            // Reduced motion uses the visible final pose for hit testing;
            // its invisible closed silhouette must not activate empty space.
            trigger.setAttribute('pointer-events', preference.matches ? 'none' : 'visiblePainted');
            planes.forEach(plane => {
                const dx = plane.dx * motion.amount + motion.x * plane.depth;
                const dy = plane.dy * motion.amount + motion.y * plane.depth;
                const turn = plane.turn * motion.amount + motion.x * plane.depth * .035;
                plane.node.setAttribute('transform', `translate(${dx.toFixed(3)} ${dy.toFixed(3)}) translate(${plane.x} ${plane.y}) rotate(${turn.toFixed(3)}) translate(${-plane.x} ${-plane.y})`);
                if (!plane.end) return;
                // The plane rotates about its own center, so only its local
                // translation precedes this shared outer-group projection.
                const localX = plane.x + dx - 290, localY = plane.y + dy - 220;
                const startX = centerX + scale * (localX * cosine - localY * sine);
                const startY = 220 + scale * (localX * sine + localY * cosine);
                const bend = clamp((plane.end.x - startX) * .3, 12, 48);
                plane.connector.setAttribute('d', `M${startX.toFixed(3)} ${startY.toFixed(3)} C${(startX + bend).toFixed(3)} ${startY.toFixed(3)} ${(plane.end.x - bend).toFixed(3)} ${plane.end.y.toFixed(3)} ${plane.end.x.toFixed(3)} ${plane.end.y.toFixed(3)}`);
                plane.connector.setAttribute('opacity', smooth(.08, .8, motion.amount).toFixed(3));
            });
        }
        function draw(time) {
            if (disposed) return;
            frame = 0;
            const delta = Math.min(.032, previous ? (time - previous) / 1000 : 1 / 60);
            previous = time;
            const active = pinned || target.amount > 0;
            const frequency = active ? 22 : 30;
            let unsettled = false;
            for (const key of Object.keys(motion)) {
                [motion[key], velocity[key]] = spring(motion[key], velocity[key], target[key], delta, frequency);
                const positionLimit = key === 'amount' ? .0008 : .015;
                const speedLimit = key === 'amount' ? .015 : .12;
                if (Math.abs(motion[key] - target[key]) > positionLimit || Math.abs(velocity[key]) > speedLimit) unsettled = true;
                else { motion[key] = target[key]; velocity[key] = 0; }
            }
            paint();
            owner.dataset.bowtieState = active ? 'active' : 'settling';
            if (unsettled) run();
            else if (!active) restore();
            else previous = 0;
        }
        function setTarget(amount, x, y) {
            if (target.amount === amount && target.x === x && target.y === y) return;
            target.amount = amount; target.x = x; target.y = y;
            owner.dataset.bowtieState = amount > 0 ? 'active' : 'settling';
            run();
        }
        function highlight() {
            // A parked mouse must not override the part selected with Tab.
            // Pointer feedback still wins when focus is not visibly keyboard-owned.
            const keyboardFocus = focusedLink && planes.some(plane =>
                plane.name === focusedLink && plane.link.matches(':focus-visible'));
            const name = keyboardFocus ? focusedLink : hoveredLink || focusedLink;
            if (name) owner.dataset.bowtieHighlight = name;
            else delete owner.dataset.bowtieHighlight;
            reveal(pinned || mouseActive || !!focusedLink);
            if (preference.matches) return;
            if (pinned) setTarget(1, 0, 0);
            else if (name) setTarget(1, 0, 0);
            else setTarget(pointerTarget.amount, pointerTarget.x, pointerTarget.y);
        }
        function closeMap(returnFocus = false) {
            if (returnFocus) svg.focus({preventScroll: true});
            pinned = mouseActive = false;
            spacePressed = false;
            hoveredLink = focusedLink = null;
            origin = lastClient = null;
            pointerTarget.amount = pointerTarget.x = pointerTarget.y = 0;
            // Folding may move ink back under a stationary pointer. Only a
            // fresh physical movement may reopen a deliberately closed map.
            blockedAt = lastMouse && {...lastMouse};
            highlight();
        }
        function refreshLayout() {
            if (disposed) return;
            if (!owner.isConnected) { destroy(); return; }
            openCenterX = compact.matches ? 290 : 125;
            const matrix = svg.getScreenCTM();
            if (!matrix) return;
            inverse = matrix.inverse();
            layoutScrollX = scrollX; layoutScrollY = scrollY;
            planes.forEach(plane => {
                const bounds = plane.link.getBoundingClientRect();
                plane.end = bounds.width && bounds.height
                    ? new DOMPoint(bounds.left - 12, bounds.top + bounds.height / 2).matrixTransform(inverse) : null;
                if (!plane.end) plane.connector.setAttribute('opacity', '0');
            });
            paint();
        }
        function point(event) {
            // SVG and index share document scrolling. The cached layout matrix
            // needs only the window scroll delta between resize observations.
            return inverse ? new DOMPoint(event.clientX + scrollX - layoutScrollX,
                event.clientY + scrollY - layoutScrollY).matrixTransform(inverse) : null;
        }
        function enter(event) {
            if (event.pointerType !== 'mouse' || pinned || mouseActive) return;
            if (blockedAt && Math.hypot(event.clientX - blockedAt.x, event.clientY - blockedAt.y) < 2) return;
            blockedAt = null;
            lastMouse = {x: event.clientX, y: event.clientY};
            mouseActive = true;
            origin = point(event);
            lastClient = {x: event.clientX, y: event.clientY};
            pointerTarget.amount = 1;
            highlight();
        }
        function move(event) {
            if (event.pointerType !== 'mouse') return;
            lastMouse = {x: event.clientX, y: event.clientY};
            if (blockedAt && Math.hypot(event.clientX - blockedAt.x, event.clientY - blockedAt.y) >= 2) blockedAt = null;
            if (!mouseActive && event.target.closest?.('[data-bowtie-trigger], [data-bowtie-layers]')) enter(event);
            if (preference.matches || pinned || !mouseActive || !origin || !lastClient) return;
            if (!event.target.closest?.('[data-bowtie-svg]')) return;
            if (Math.hypot(event.clientX - lastClient.x, event.clientY - lastClient.y) < 2) return;
            const current = point(event);
            if (!current) return;
            const dx = current.x - origin.x, dy = current.y - origin.y;
            lastClient = {x: event.clientX, y: event.clientY};
            pointerTarget.amount = 1;
            pointerTarget.x = clamp(dx * .12, -18, 18);
            pointerTarget.y = clamp(dy * .1, -18, 18);
            highlight();
        }
        function release() {
            origin = null; lastClient = null;
            mouseActive = false; hoveredLink = null; blockedAt = null;
            pointerTarget.amount = pointerTarget.x = pointerTarget.y = 0;
            // The shared region bridges the drawing and its links. Crossing
            // that gap must not hide an option on the way to clicking it.
            highlight();
        }
        function setPreference() {
            restore(true);
            owner.dataset.bowtieMotion = preference.matches ? 'reduced' : 'full';
        }

        function activate() {
            // Hover can already expose the map. Its first deliberate
            // activation pins it; only a later activation folds it again.
            if (pinned) { closeMap(true); return; }
            pinned = true;
            origin = null; lastClient = null;
            pointerTarget.amount = pointerTarget.x = pointerTarget.y = 0;
            hoveredLink = focusedLink = null;
            delete owner.dataset.bowtieHighlight;
            highlight();
        }

        on(group, 'pointerenter', enter);
        on(trigger, 'pointerenter', enter);
        on(owner, 'pointermove', move);
        on(owner, 'pointerleave', release);
        on(owner, 'pointercancel', release);
        on(svg, 'click', event => {
            if (event.button !== 0) return;
            // Physical clicks/taps target the silhouette or visible paper,
            // never the empty SVG frame. Assistive activation has no hit point.
            if (event.detail && !event.target.closest?.('[data-bowtie-trigger], [data-bowtie-layers]')) return;
            activate();
        });
        on(svg, 'keydown', event => {
            if (event.target !== svg || !['Enter', ' ', 'Spacebar'].includes(event.key)) return;
            // A custom SVG button supplies native-button keyboard semantics;
            // preventing Space's key scroll does not intercept touch scrolling.
            event.preventDefault();
            if (event.repeat) return;
            if (event.key === 'Enter') activate();
            else spacePressed = true;
        });
        on(svg, 'keyup', event => {
            if (event.target !== svg || ![' ', 'Spacebar'].includes(event.key)) return;
            event.preventDefault();
            if (!spacePressed) return;
            spacePressed = false;
            activate();
        });
        on(svg, 'blur', () => { spacePressed = false; });
        planes.forEach(plane => {
            on(plane.link, 'pointerenter', event => {
                if (event.pointerType !== 'mouse') return;
                hoveredLink = plane.name; highlight();
            });
            on(plane.link, 'pointerleave', event => {
                if (event.pointerType !== 'mouse') return;
                if (hoveredLink === plane.name) hoveredLink = null;
                highlight();
            });
            on(plane.link, 'focus', () => { focusedLink = plane.name; highlight(); });
            on(plane.link, 'blur', event => {
                const next = event.relatedTarget?.closest?.('[data-bowtie-map-link]');
                if (focusedLink === plane.name) focusedLink = next && map.contains(next) ? next.dataset.bowtieMapLink : null;
                highlight();
            });
        });
        on(document, 'keydown', event => {
            if (event.key === 'Escape' && !map.inert) closeMap(true);
        });
        on(owner, 'focusout', event => {
            if (!owner.contains(event.relatedTarget)) { pinned = false; focusedLink = null; highlight(); }
        });
        on(window, 'blur', () => restore());
        on(window, 'resize', () => { restore(true); refreshLayout(); }, {passive: true});
        on(document, 'visibilitychange', () => { if (document.hidden) restore(); });
        visibilityObserver = new IntersectionObserver(entries => {
            if (disposed) return;
            visible = entries[0].isIntersecting;
            if (!visible) restore();
        });
        visibilityObserver.observe(owner);
        // One observer caches all link endpoints. Animation frames perform no
        // layout reads and never transform text or navigation hit areas.
        layoutObserver = new ResizeObserver(refreshLayout);
        layoutObserver.observe(svg);
        layoutObserver.observe(map);
        on(compact, 'change', () => { restore(true); refreshLayout(); });
        on(preference, 'change', setPreference);
        refreshLayout();
        setPreference();
        // Font loading can shift this illustration without resizing its own
        // box; refresh the cached page coordinates once text metrics settle.
        document.fonts?.ready.then(refreshLayout);
    }

    function initializeAll(root = document) {
        for (const [owner, cleanup] of owners) if (!owner.isConnected) cleanup();
        if (root.matches?.('[data-paper-bowtie], [data-lab-bowtie]')) initialize(root);
        root.querySelectorAll?.('[data-paper-bowtie], [data-lab-bowtie]').forEach(initialize);
    }

    window.TuxedoPaperLayers = {initialize, initializeAll,
        destroy: owner => owners.get(owner)?.()};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initializeAll());
    else initializeAll();
    document.addEventListener('htmx:load', event => initializeAll(event.detail?.elt || document));
    // HTMX removes the owner before inserting another server-rendered document.
    // Abort its window/media listeners and observers rather than retaining it.
    document.addEventListener('htmx:beforeCleanupElement', event => {
        const removed = event.detail?.elt || event.target;
        for (const [owner, cleanup] of owners) if (removed === owner || removed.contains?.(owner)) cleanup();
    });
}());
