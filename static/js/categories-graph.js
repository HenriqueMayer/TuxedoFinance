/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoCategoryGraph) { window.TuxedoCategoryGraph.init(); return; }
    const initialized = new WeakSet();
    const observers = new Map();
    const origins = new WeakMap();
    const ns = 'http://www.w3.org/2000/svg';
    function element(tag, attributes = {}, text = '') {
        const node = document.createElementNS(ns, tag);
        Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
        if (text) node.textContent = text;
        return node;
    }
    function titleLines(name) {
        const chars = Array.from(name);
        if (chars.length <= 28) return [name];
        let split = chars.slice(0, 28).lastIndexOf(' ');
        if (split < 12) split = 28;
        const first = chars.slice(0, split).join('').trim();
        const rest = chars.slice(split).join('').trim();
        return [first, Array.from(rest).slice(0, 27).join('') + (Array.from(rest).length > 27 ? '…' : '')];
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
        const byId = new Map(nodes.map((node, index) => [node.id, {...node, x: node.depth * 260 + 24, y: index * 100 + 24}]));
        const parentIds = new Set(nodes.map(node => node.parent).filter(Boolean));
        const renderedUrl = new URL(root.dataset.graphOrigin || location.href, location.origin);
        const searchActive = Boolean(renderedUrl.searchParams.get('q')?.trim());
        const matches = nodes.filter(node => !node.context);
        const initialNode = (searchActive ? matches[0] : nodes.find(node => parentIds.has(node.id))) || nodes[0];
        const totalWidth = Math.max(...nodes.map(node => node.depth)) * 260 + 268;
        const totalHeight = nodes.length * 100 + 24;
        let scale = 1, tx = 0, ty = 0, selected = null, adjusted = false, overview = false;
        const pointers = new Map();
        let gesture = null;
        root.hidden = false;
        const fallback = root.parentElement.querySelector('[data-category-graph-fallback]');
        if (fallback) fallback.open = false;
        function size() { return {width: svg.clientWidth, height: svg.clientHeight}; }
        function transform() {
            layer.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`);
            svg.dataset.scale = String(scale);
        }
        function fit() {
            const {width, height} = size();
            scale = Math.min(1, (width - 24) / totalWidth, (height - 24) / totalHeight);
            scale = Math.max(0.05, scale);
            tx = (width - totalWidth * scale) / 2;
            ty = (height - totalHeight * scale) / 2;
            adjusted = false; overview = true;
            transform();
        }
        function initialView() {
            const {width} = size();
            // Fit-all becomes unreadable as a lifelong catalogue grows. Start
            // with readable labels at the first match or connected branch; Fit remains
            // a deliberate overview, while pan/keyboard reach every other node.
            scale = Math.max(0.85, Math.min(1, (width - 24) / totalWidth));
            const start = byId.get(initialNode.id);
            tx = totalWidth * scale <= width ? (width - totalWidth * scale) / 2 : 12 - start.x * scale;
            ty = 12 - start.y * scale;
            adjusted = false; overview = false; transform();
        }
        function zoom(factor, point = null) {
            const {width, height} = size();
            const cx = point?.x ?? width / 2, cy = point?.y ?? height / 2;
            const next = Math.max(0.05, Math.min(3, scale * factor));
            tx = cx - (cx - tx) * next / scale;
            ty = cy - (cy - ty) * next / scale;
            scale = next; adjusted = true; transform();
        }
        function centerOn(node) {
            const {width, height} = size();
            scale = Math.max(scale, Math.min(1, (width - 32) / 220));
            tx = width / 2 - (node.x + 110) * scale;
            ty = height / 2 - (node.y + 38) * scale;
            adjusted = true; transform();
        }
        function select(id, focus = false, center = false) {
            const node = byId.get(id);
            if (!node) return;
            selected = id;
            for (const item of byId.values()) {
                item.element.setAttribute('aria-pressed', String(item.id === id));
                item.element.setAttribute('tabindex', item.id === id ? '0' : '-1');
            }
            root.querySelector('[data-graph-empty]').hidden = true;
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
            if (parent) {
                const x1 = parent.x + 220, y1 = parent.y + 38, x2 = node.x, y2 = node.y + 38;
                layer.append(element('path', {d: `M ${x1} ${y1} C ${x1 + 20} ${y1} ${x2 - 20} ${y2} ${x2} ${y2}`,
                    class: 'category-graph-edge', 'aria-hidden': 'true'}));
            }
        }
        for (const node of byId.values()) {
            const group = element('g', {id: `category-graph-node-${node.id}`, class: 'category-graph-node',
                transform: `translate(${node.x} ${node.y})`, role: 'button', tabindex: node.id === initialNode.id ? '0' : '-1',
                'aria-label': `${root.dataset.selectLabel}: ${node.name}`, 'aria-pressed': 'false',
                'data-node-id': node.id, 'data-context': String(node.context)});
            group.append(element('title', {}, node.name), element('rect', {width: 220, height: 76, rx: 12}));
            const lines = titleLines(node.name);
            lines.forEach((line, index) => group.append(element('text', {x: 12, y: index * 18 + 25, class: 'category-graph-node-name'}, line)));
            group.append(element('text', {x: 12, y: 63, class: 'category-graph-node-meta'}, `${node.kind} · ${node.usage_label}`));
            node.element = group; layer.append(group);
        }
        svg.addEventListener('focusin', event => {
            const target = event.target.closest('[data-node-id]');
            if (!target?.matches(':focus-visible')) return;
            const bounds = target.getBoundingClientRect(), viewport = svg.getBoundingClientRect();
            // Tab may revisit a selected node after panning. Reveal its focus
            // inside the graph, without moving focus or scrolling the page.
            if (bounds.left < viewport.left || bounds.right > viewport.right ||
                bounds.top < viewport.top || bounds.bottom > viewport.bottom) centerOn(byId.get(target.dataset.nodeId));
        });
        svg.addEventListener('keydown', event => {
            const id = event.target.closest('[data-node-id]')?.dataset.nodeId;
            const node = byId.get(id || selected);
            const index = nodes.findIndex(item => item.id === node?.id);
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
            if (values.length === 1) gesture = {point: values[0], tx, ty, moved: gesture?.moved || false};
            else if (values.length >= 2) {
                const center = {x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2};
                gesture = {distance: Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y),
                    scale, world: {x: (center.x - tx) / scale, y: (center.y - ty) / scale}, moved: true};
            }
        }
        svg.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
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
            } else {
                const dx = values[0].x - gesture.point.x, dy = values[0].y - gesture.point.y;
                gesture.moved ||= Math.hypot(dx, dy) > 6;
                if (!gesture.moved) return;
                tx = gesture.tx + dx; ty = gesture.ty + dy;
            }
            svg.classList.add('is-panning'); adjusted = true; transform();
        });
        function endGesture(event) {
            const pointer = pointers.get(event.pointerId);
            if (!pointer) return;
            const activate = event.type === 'pointerup' && pointers.size === 1 && !gesture?.moved && pointer.node;
            pointers.delete(event.pointerId);
            if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
            if (activate) select(pointer.node, true, false);
            if (pointers.size) startGesture();
            else { gesture = null; svg.classList.remove('is-panning'); }
        }
        svg.addEventListener('pointerup', endGesture);
        svg.addEventListener('pointercancel', endGesture);
        // Rendering and gestures own only this SVG transform and selection.
        // There is deliberately no persistence, POST, or hierarchy mutation.
        const observer = new ResizeObserver(() => {
            if (root.isConnected && !adjusted) { if (overview) fit(); else initialView(); }
        });
        observer.observe(svg);
        observers.set(root, observer);
        function reconcileOrigin(url) {
            const prefix = '#category-graph-node-';
            const origin = url.hash.startsWith(prefix) ? url.hash.slice(prefix.length) : null;
            // A deliberate editor/GET origin wins, even when it names an
            // ancestor retained as context rather than the unique search match.
            if (origin && byId.has(origin)) select(origin, false, true);
            else if (searchActive && matches.length === 1) select(matches[0].id, false, true);
            else {
                selected = null;
                for (const node of byId.values()) {
                    node.element.setAttribute('aria-pressed', 'false');
                    node.element.setAttribute('tabindex', node.id === initialNode.id ? '0' : '-1');
                }
                root.querySelector('[data-graph-empty]').hidden = false;
                root.querySelector('[data-graph-selected]').hidden = true;
                initialView();
            }
        }
        origins.set(root, reconcileOrigin);
        initialView();
        // Live filters mount their new island before committing its URL. Do
        // not restore an old hash into that island; the applied-URL event below
        // reconciles it after history, focus and page scroll have been restored.
        if (renderedUrl.pathname === location.pathname && renderedUrl.search === location.search) {
            reconcileOrigin(new URL(location.href));
        }
    }
    function init() {
        // Live result replacement is not an HTMX swap. Release detached SVGs
        // here as well, without retaining their observers or user-owned data.
        for (const [root, observer] of observers) {
            if (!root.isConnected) { observer.disconnect(); observers.delete(root); }
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
        // History restoration can retain a legitimate fragment that response.url
        // omits. Reconcile the actual applied location without moving DOM focus.
        const url = new URL(location.href);
        event.detail.results?.querySelectorAll('[data-category-graph]').forEach(root => origins.get(root)?.(url));
    });
    document.addEventListener('htmx:beforeSwap', event => {
        if (!event.detail.shouldSwap || event.detail.isError) return;
        for (const [root, observer] of observers) {
            if (event.detail.target?.contains(root)) { observer.disconnect(); observers.delete(root); }
        }
    });
    init();
}());
