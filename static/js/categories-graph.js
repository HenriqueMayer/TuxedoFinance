/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoCategoryGraph) { window.TuxedoCategoryGraph.init(); return; }
    const initialized = new WeakSet();
    const resources = new Map();
    const origins = new WeakMap();
    const ns = 'http://www.w3.org/2000/svg';
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    function element(tag, attributes = {}, text = '') {
        const node = document.createElementNS(ns, tag);
        Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
        if (text) node.textContent = text;
        return node;
    }
    function hash(value) {
        let result = 2166136261;
        for (const char of value) result = Math.imul(result ^ char.charCodeAt(0), 16777619);
        return result >>> 0;
    }
    function titleLines(name) {
        const chars = Array.from(name);
        if (chars.length <= 24) return [name];
        let split = chars.slice(0, 24).lastIndexOf(' ');
        if (split < 10) split = 24;
        const rest = chars.slice(split).join('').trim();
        return [chars.slice(0, split).join('').trim(),
            Array.from(rest).slice(0, 23).join('') + (Array.from(rest).length > 23 ? '…' : '')];
    }
    function initialize(root) {
        if (initialized.has(root)) return;
        const data = root.querySelector('#category-graph-data');
        const svg = root.querySelector('[data-graph-canvas]');
        if (!data || !svg) return;
        let nodes;
        try { nodes = JSON.parse(data.textContent); } catch (_) { return; }
        if (!nodes.length) return;
        initialized.add(root);
        const layer = svg.querySelector('[data-graph-layer]');
        const byId = new Map(nodes.map(node => [node.id, {...node, edges: []}]));
        const renderedUrl = new URL(root.dataset.graphOrigin || location.href, location.origin);
        const searchActive = Boolean(renderedUrl.searchParams.get('q')?.trim());
        const matches = nodes.filter(node => !node.context);
        const parentIds = new Set(nodes.map(node => node.parent).filter(Boolean));
        const initialNode = byId.get(((searchActive ? matches[0] : nodes.find(node => parentIds.has(node.id))) || nodes[0]).id);
        const clusters = new Map();
        for (const node of byId.values()) {
            let ancestor = node;
            const visited = new Set([node.id]);
            while (byId.has(ancestor.parent) && !visited.has(ancestor.parent)) {
                ancestor = byId.get(ancestor.parent); visited.add(ancestor.id);
            }
            node.cluster = ancestor.id;
            if (!clusters.has(ancestor.id)) clusters.set(ancestor.id, []);
            clusters.get(ancestor.id).push(node);
        }
        // Real roots form independent clusters; no central or cross-category
        // links are manufactured to make an otherwise disconnected map fuller.
        const groups = [...clusters.values()].sort((a, b) => b.length - a.length);
        const spread = 210 + Math.sqrt(groups[0].length - 1) * 85;
        groups.forEach((group, index) => {
            // A seeded sunflower distribution keeps layout work linear in the
            // number of roots, including catalogues with many unrelated roots.
            const distance = spread * Math.sqrt(index), angle = index * goldenAngle;
            const anchor = {x: Math.cos(angle) * distance, y: Math.sin(angle) * distance};
            group.forEach((node, offset) => {
                const angle = offset * goldenAngle + (hash(node.cluster) % 30) / 30;
                const distance = offset ? 125 * Math.sqrt(offset) : 0;
                node.x = anchor.x + Math.cos(angle) * distance;
                node.y = anchor.y + Math.sin(angle) * distance;
                node.homeX = node.x; node.homeY = node.y;
                node.color = String(index % 4);
            });
        });
        let scale = 1, tx = 0, ty = 0, selected = null, adjusted = false, overview = false;
        let frame = null, disposed = false;
        const pointers = new Map();
        const edges = [];
        let gesture = null;
        const motion = matchMedia('(prefers-reduced-motion: reduce)');
        const animateLayout = !motion.matches && nodes.length <= 400;
        root.hidden = false;
        const fallback = root.parentElement.querySelector('[data-category-graph-fallback]');
        if (fallback) fallback.open = false;
        function size() { return {width: svg.clientWidth, height: svg.clientHeight}; }
        function drawEdge(edge) {
            edge.element.setAttribute('x1', edge.parent.x); edge.element.setAttribute('y1', edge.parent.y);
            edge.element.setAttribute('x2', edge.child.x); edge.element.setAttribute('y2', edge.child.y);
        }
        function drawNode(node) { node.element.setAttribute('transform', `translate(${node.x} ${node.y})`); }
        function draw() { byId.forEach(drawNode); edges.forEach(drawEdge); }
        function transform() {
            layer.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`);
            // Nodes, labels and 44px hit areas stay in screen pixels even in Fit.
            // Zoom changes the space between categories, never their text size.
            byId.forEach(node => node.display.setAttribute('transform', `scale(${1 / scale})`));
            svg.dataset.scale = String(scale);
        }
        function stopMotion(finish = false) {
            const running = frame !== null;
            if (running) cancelAnimationFrame(frame);
            frame = null;
            if (finish && running) {
                byId.forEach(node => { node.x = node.targetX; node.y = node.targetY; });
                draw();
            }
            svg.dataset.motion = 'settled';
        }
        function fit() {
            stopMotion();
            const {width, height} = size();
            const values = [...byId.values()];
            const minX = Math.min(...values.map(node => node.x)), maxX = Math.max(...values.map(node => node.x));
            const minY = Math.min(...values.map(node => node.y)), maxY = Math.max(...values.map(node => node.y));
            const left = Math.min(...values.map(node => node.bounds.x));
            const right = Math.max(...values.map(node => node.bounds.x + node.bounds.width));
            const top = Math.min(...values.map(node => node.bounds.y));
            const bottom = Math.max(...values.map(node => node.bounds.y + node.bounds.height));
            scale = Math.max(0.05, Math.min(1, (width - 32 - right + left) / Math.max(1, maxX - minX),
                (height - 32 - bottom + top) / Math.max(1, maxY - minY)));
            tx = (width - (maxX - minX) * scale - right - left) / 2 - minX * scale;
            ty = (height - (maxY - minY) * scale - bottom - top) / 2 - minY * scale;
            adjusted = false; overview = true; transform();
        }
        function placeAround(node) {
            const {width, height} = size();
            tx = width / 2 - node.x * scale - node.bounds.x - node.bounds.width / 2;
            ty = height / 2 - node.y * scale - node.bounds.y - node.bounds.height / 2;
            transform();
        }
        function initialView() {
            scale = 1; overview = false; adjusted = false; placeAround(initialNode);
        }
        function zoom(factor, point = null) {
            stopMotion();
            const {width, height} = size();
            const cx = point?.x ?? width / 2, cy = point?.y ?? height / 2;
            const next = Math.max(0.05, Math.min(3, scale * factor));
            tx = cx - (cx - tx) * next / scale; ty = cy - (cy - ty) * next / scale;
            scale = next; adjusted = true; transform();
        }
        function centerOn(node) {
            scale = Math.max(scale, 0.85); adjusted = true; placeAround(node);
        }
        function revealNode(node) {
            const bounds = node.element.getBoundingClientRect(), viewport = svg.getBoundingClientRect();
            if (bounds.left < viewport.left || bounds.right > viewport.right ||
                bounds.top < viewport.top || bounds.bottom > viewport.bottom) centerOn(node);
        }
        function select(id, focus = false, center = false) {
            const node = byId.get(id);
            if (!node) return;
            stopMotion(); selected = id;
            for (const item of byId.values()) {
                item.element.setAttribute('aria-pressed', String(item.id === id));
                item.element.setAttribute('tabindex', item.id === id ? '0' : '-1');
                item.element.dataset.related = String(item.id === id || item.parent === id || node.parent === item.id);
            }
            edges.forEach(edge => { edge.element.dataset.related = String(edge.parent.id === id || edge.child.id === id); });
            root.querySelector('[data-graph-empty]').hidden = true;
            root.querySelector('[data-graph-selection-panel]').hidden = false;
            root.querySelector('[data-graph-selected]').hidden = false;
            root.querySelector('[data-graph-name]').textContent = node.name;
            root.querySelector('[data-graph-kind]').textContent = node.kind;
            root.querySelector('[data-graph-usage]').textContent = node.usage_label;
            root.querySelector('[data-graph-context]').hidden = !node.context;
            for (const action of ['edit', 'add', 'delete']) {
                const link = root.querySelector(`[data-graph-${action}]`);
                link.hidden = !node[action];
                if (node[action]) { link.setAttribute('href', node[action]); window.htmx?.process(link); }
                else link.removeAttribute('href');
            }
            if (center) centerOn(node);
            if (focus) node.element.focus({preventScroll: true});
        }
        for (const node of byId.values()) {
            const parent = byId.get(node.parent);
            if (!parent) continue;
            const edge = {parent, child: node, element: element('line', {class: 'category-graph-edge',
                'data-source': parent.id, 'data-target': node.id, 'aria-hidden': 'true'})};
            parent.edges.push(edge); node.edges.push(edge); edges.push(edge); layer.append(edge.element);
        }
        for (const node of byId.values()) {
            const group = element('g', {id: `category-graph-node-${node.id}`, class: 'category-graph-node',
                role: 'button', tabindex: node.id === initialNode.id ? '0' : '-1',
                'aria-label': `${root.dataset.selectLabel}: ${node.name}`, 'aria-pressed': 'false',
                'data-node-id': node.id, 'data-context': String(node.context), 'data-cluster': node.color});
            const display = element('g', {'data-node-display': ''});
            display.append(element('title', {}, node.name),
                element('circle', {class: 'category-graph-hit', r: 22}),
                element('circle', {class: 'category-graph-focus', r: 14}),
                element('circle', {class: 'category-graph-point', r: node.parent ? 6 : 8}));
            titleLines(node.name).forEach((line, index) => display.append(element('text',
                {x: 16, y: index * 18 + 4, class: 'category-graph-node-name'}, line)));
            group.append(display); node.element = group; node.display = display; layer.append(group);
            node.bounds = display.getBBox();

        }
        // Bound work by catalogue size. Nearby-label collision checks use a
        // spatial grid instead of an all-pairs force loop on every animation frame.
        const iterations = Math.max(12, Math.min(60, Math.floor(12000 / nodes.length)));
        for (let iteration = 0; iteration < iterations; iteration++) {
            const grid = new Map();
            byId.forEach(node => {
                const key = `${Math.floor(node.x / 260)},${Math.floor(node.y / 260)}`;
                if (!grid.has(key)) grid.set(key, []);
                grid.get(key).push(node); node.dx = (node.homeX - node.x) * 0.02; node.dy = (node.homeY - node.y) * 0.02;
            });
            byId.forEach(node => {
                const cx = Math.floor(node.x / 260), cy = Math.floor(node.y / 260);
                for (let x = cx - 1; x <= cx + 1; x++) for (let y = cy - 1; y <= cy + 1; y++) {
                    for (const other of grid.get(`${x},${y}`) || []) {
                        if (node.id >= other.id) continue;
                        const dx = node.x + node.bounds.x + node.bounds.width / 2 - other.x - other.bounds.x - other.bounds.width / 2;
                        const dy = node.y + node.bounds.y + node.bounds.height / 2 - other.y - other.bounds.y - other.bounds.height / 2;
                        const overlapX = (node.bounds.width + other.bounds.width) / 2 + 30 - Math.abs(dx);
                        const overlapY = (node.bounds.height + other.bounds.height) / 2 + 36 - Math.abs(dy);
                        if (overlapX <= 0 || overlapY <= 0) continue;
                        if (overlapY < overlapX) {
                            const force = Math.sign(dy || 1) * overlapY * 0.3;
                            node.dy += force; other.dy -= force;
                        } else {
                            const force = Math.sign(dx || 1) * overlapX * 0.3;
                            node.dx += force; other.dx -= force;
                        }
                    }
                }
            });
            byId.forEach(node => { node.x += Math.max(-18, Math.min(18, node.dx)); node.y += Math.max(-18, Math.min(18, node.dy)); });
        }
        byId.forEach(node => {
            node.targetX = node.x; node.targetY = node.y;
            const angle = hash(node.id) % 628 / 100;
            node.startX = node.x + Math.cos(angle) * 20; node.startY = node.y + Math.sin(angle) * 20;
            if (animateLayout) { node.x = node.startX; node.y = node.startY; }
        });
        draw();
        function animate(start) {
            svg.dataset.motion = 'settling';
            function step(now) {
                if (disposed || !root.isConnected) { stopMotion(); return; }
                const elapsed = Math.min(1, (now - start) / 700);
                const remaining = Math.pow(1 - elapsed, 3) * Math.cos(elapsed * 4);
                byId.forEach(node => {
                    node.x = node.targetX + (node.startX - node.targetX) * remaining;
                    node.y = node.targetY + (node.startY - node.targetY) * remaining;
                });
                draw();
                if (elapsed < 1) frame = requestAnimationFrame(step);
                else { frame = null; svg.dataset.motion = 'settled'; }
            }
            frame = requestAnimationFrame(step);
        }
        if (!animateLayout) svg.dataset.motion = 'settled';
        else animate(performance.now());
        svg.addEventListener('focusin', event => {
            const target = event.target.closest('[data-node-id]');
            if (!target?.matches(':focus-visible')) return;
            stopMotion();
            revealNode(byId.get(target.dataset.nodeId));
        });
        svg.addEventListener('keydown', event => {
            const id = event.target.closest('[data-node-id]')?.dataset.nodeId;
            const node = byId.get(id || selected);
            const index = nodes.findIndex(item => item.id === node?.id);
            if (event.shiftKey && node && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault(); stopMotion();
                node.x += (event.key === 'ArrowLeft' ? -20 : event.key === 'ArrowRight' ? 20 : 0) / scale;
                node.y += (event.key === 'ArrowUp' ? -20 : event.key === 'ArrowDown' ? 20 : 0) / scale;
                node.targetX = node.x; node.targetY = node.y;
                drawNode(node); node.edges.forEach(drawEdge); adjusted = true;
                select(node.id, true, false);
                // An already-focused node emits no new focusin. Reveal each
                // keyboard arrangement without moving DOM focus or page scroll.
                revealNode(node); return;
            }
            let target;
            if (event.key === 'ArrowDown') target = nodes[Math.min(nodes.length - 1, index + 1)];
            else if (event.key === 'ArrowUp') target = nodes[Math.max(0, index - 1)];
            else if (event.key === 'ArrowLeft') target = byId.get(node?.parent) || node;
            else if (event.key === 'ArrowRight') target = nodes.find(item => item.parent === node?.id) || node;
            else if (event.key === 'Home') target = nodes[0];
            else if (event.key === 'End') target = nodes.at(-1);
            else if (['Enter', ' '].includes(event.key)) target = node || nodes[0];
            else if (['+', '='].includes(event.key)) { event.preventDefault(); zoom(1.25); return; }
            else if (event.key === '-') { event.preventDefault(); zoom(0.8); return; }
            if (target) { event.preventDefault(); select(target.id, true, true); }
        });
        root.querySelectorAll('[data-graph-action]').forEach(button => button.addEventListener('click', () => {
            if (button.dataset.graphAction === 'fit') fit();
            else zoom(button.dataset.graphAction === 'in' ? 1.25 : 0.8);
        }));
        function point(event) {
            const box = svg.getBoundingClientRect();
            return {x: event.clientX - box.left, y: event.clientY - box.top};
        }
        function startGesture() {
            const values = [...pointers.values()];
            if (values.length === 1) {
                const node = byId.get(values[0].node);
                gesture = {point: values[0], tx, ty, node, x: node?.x, y: node?.y, moved: gesture?.moved || false};
            } else if (values.length >= 2) {
                const center = {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2};
                pointers.forEach(pointer => { pointer.node = null; });
                gesture = {distance: Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y),
                    scale, world: {x: (center.x - tx) / scale, y: (center.y - ty) / scale}, moved: true};
                svg.classList.remove('is-node-dragging');
            }
        }
        svg.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            stopMotion();
            pointers.set(event.pointerId, {...point(event), node: event.target.closest('[data-node-id]')?.dataset.nodeId});
            svg.setPointerCapture(event.pointerId); startGesture();
        });
        svg.addEventListener('pointermove', event => {
            if (!pointers.has(event.pointerId) || !gesture) return;
            pointers.set(event.pointerId, {...pointers.get(event.pointerId), ...point(event)});
            const values = [...pointers.values()];
            if (values.length >= 2 && gesture.distance) {
                const center = {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2};
                const distance = Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
                scale = Math.max(0.05, Math.min(3, gesture.scale * distance / gesture.distance));
                tx = center.x - gesture.world.x * scale; ty = center.y - gesture.world.y * scale;
                transform();
            } else {
                const dx = values[0].x - gesture.point.x, dy = values[0].y - gesture.point.y;
                gesture.moved ||= Math.hypot(dx, dy) > 6;
                if (!gesture.moved) return;
                if (gesture.node) {
                    const node = gesture.node;
                    node.x = gesture.x + dx / scale; node.y = gesture.y + dy / scale;
                    node.targetX = node.x; node.targetY = node.y;
                    drawNode(node); node.edges.forEach(drawEdge);
                    svg.classList.add('is-node-dragging');
                } else { tx = gesture.tx + dx; ty = gesture.ty + dy; transform(); svg.classList.add('is-panning'); }
            }
            adjusted = true;
        });
        function endGesture(event) {
            const pointer = pointers.get(event.pointerId);
            if (!pointer) return;
            const activate = event.type === 'pointerup' && pointers.size === 1 && pointer.node;
            pointers.delete(event.pointerId);
            if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
            if (activate) select(pointer.node, true, false);
            if (pointers.size) startGesture();
            else { gesture = null; svg.classList.remove('is-panning', 'is-node-dragging'); }
        }
        svg.addEventListener('pointerup', endGesture);
        svg.addEventListener('pointercancel', endGesture);
        const observer = new ResizeObserver(() => {
            if (root.isConnected && !adjusted) { if (overview) fit(); else initialView(); }
        });
        observer.observe(svg);
        const reduceMotion = () => { if (motion.matches) stopMotion(true); };
        motion.addEventListener('change', reduceMotion);
        resources.set(root, () => { disposed = true; observer.disconnect(); stopMotion(); motion.removeEventListener('change', reduceMotion); });
        function reconcileOrigin(url) {
            const prefix = '#category-graph-node-';
            const origin = url.hash.startsWith(prefix) ? url.hash.slice(prefix.length) : null;
            if (origin && byId.has(origin)) select(origin, false, true);
            else if (searchActive && matches.length === 1) select(matches[0].id, false, true);
            else {
                selected = null;
                byId.forEach(node => {
                    node.element.setAttribute('aria-pressed', 'false');
                    node.element.setAttribute('tabindex', node.id === initialNode.id ? '0' : '-1');
                });
                root.querySelector('[data-graph-empty]').hidden = false;
                root.querySelector('[data-graph-selection-panel]').hidden = true;
                root.querySelector('[data-graph-selected]').hidden = true;
                initialView();
            }
        }
        origins.set(root, reconcileOrigin);
        initialView();
        // Live islands mount before history commits. Native GET/Cancel hashes
        // restore immediately; live origins use the applied-URL event below.
        if (renderedUrl.pathname === location.pathname && renderedUrl.search === location.search) reconcileOrigin(new URL(location.href));
    }
    function init() {
        for (const [root, dispose] of resources) {
            if (!root.isConnected) { dispose(); resources.delete(root); }
        }
        document.querySelectorAll('[data-category-graph]').forEach(initialize);
    }
    window.TuxedoCategoryGraph = {init};
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:historyRestore', init);
    document.addEventListener('tuxedo:live-filters-updated', event => {
        if (event.detail.form?.id !== 'category-filters') return;
        init();
        const url = new URL(location.href);
        event.detail.results?.querySelectorAll('[data-category-graph]').forEach(root => origins.get(root)?.(url));
    });
    document.addEventListener('htmx:beforeSwap', event => {
        if (!event.detail.shouldSwap || event.detail.isError) return;
        for (const [root, dispose] of resources) {
            if (event.detail.target?.contains(root)) { dispose(); resources.delete(root); }
        }
    });
    init();
}());
