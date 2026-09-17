/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoHelp) return;
    const initialized = new WeakSet();
    let active = null;
    let dismissed = null;
    let closeTimer;
    let pointerType = 'mouse';

    function inside(target) {
        return active && target instanceof Node
            && (active.root.contains(target) || active.content.contains(target));
    }
    function rootFor(target) {
        if (!(target instanceof Element)) return null;
        return target.closest('[data-help-popover]')
            || (active && active.content.contains(target) ? active.root : null);
    }
    function close() {
        clearTimeout(closeTimer);
        if (!active) return;
        active.content.hidden = true;
        active.trigger.setAttribute('aria-expanded', 'false');
        // Return the floating content before HTMX stores or replaces its owner.
        active.root.append(active.content);
        active = null;
    }
    function position() {
        if (!active) return;
        if (!active.root.isConnected) { close(); return; }
        const viewport = window.visualViewport;
        const leftEdge = (viewport?.offsetLeft || 0) + 12;
        const topEdge = (viewport?.offsetTop || 0) + 12;
        const width = (viewport?.width || window.innerWidth) - 24;
        const height = (viewport?.height || window.innerHeight) - 24;
        const trigger = active.trigger.getBoundingClientRect();
        if (trigger.bottom < topEdge || trigger.top > topEdge + height) { close(); return; }
        active.content.style.width = `${Math.min(352, width)}px`;
        active.content.style.maxHeight = `${height}px`;
        const content = active.content.getBoundingClientRect();
        const left = Math.max(leftEdge, Math.min(trigger.left + trigger.width / 2 - content.width / 2,
            leftEdge + width - content.width));
        let top = trigger.bottom + 8;
        if (top + content.height > topEdge + height) top = trigger.top - content.height - 8;
        top = Math.max(topEdge, Math.min(top, topEdge + height - content.height));
        active.content.style.left = `${Math.round(left)}px`;
        active.content.style.top = `${Math.round(top)}px`;
    }
    function open(root, mode) {
        if (!root || dismissed === root) return;
        clearTimeout(closeTimer);
        if (active?.root === root) {
            if (mode !== 'mouse') active.mode = mode;
            return;
        }
        close();
        const trigger = root.querySelector('[data-help-trigger]');
        const content = root.querySelector('[data-help-content]');
        if (!trigger || !content) return;
        active = { root, trigger, content, mode };
        // Floating help must not inherit the icon's width or a card's clipping.
        document.body.append(content);
        content.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        position();
    }
    function init() {
        document.querySelectorAll('[data-help-popover]').forEach(root => {
            // Fragment parsers can materialize noscript children during HTMX swaps.
            root.querySelector('noscript')?.remove();
            if (initialized.has(root)) return;
            initialized.add(root);
            const trigger = root.querySelector('[data-help-trigger]');
            const content = root.querySelector('[data-help-content]');
            if (trigger && content) {
                trigger.hidden = false;
                trigger.setAttribute('aria-expanded', 'false');
                content.hidden = true;
            }
        });
    }
    document.addEventListener('pointerover', event => {
        if (event.pointerType === 'touch') return;
        open(rootFor(event.target), 'mouse');
    });
    document.addEventListener('pointerout', event => {
        const root = rootFor(event.target);
        if (dismissed === root && !root?.contains(event.relatedTarget)) dismissed = null;
        if (!active || active.root !== root || inside(event.relatedTarget)) return;
        if (active.mode === 'touch' || (active.mode === 'keyboard' && document.activeElement === active.trigger)) return;
        clearTimeout(closeTimer);
        // Allow the pointer to cross the small gap and read the tooltip itself.
        closeTimer = setTimeout(close, 120);
    });
    document.addEventListener('pointerdown', event => {
        pointerType = event.pointerType;
        if (active && !inside(event.target)) { dismissed = active.root; close(); }
    });
    document.addEventListener('focusin', event => {
        if (event.target.matches('[data-help-trigger]:focus-visible')) {
            dismissed = null;
            open(rootFor(event.target), 'keyboard');
        }
    });
    document.addEventListener('focusout', event => {
        if (active?.trigger === event.target) close();
    });
    document.addEventListener('click', event => {
        const trigger = event.target.closest('[data-help-trigger]');
        if (!trigger) {
            if (active && !inside(event.target)) { dismissed = active.root; close(); }
            return;
        }
        if (event.detail === 0) {
            dismissed = null;
            open(rootFor(trigger), 'keyboard');
        } else if (pointerType === 'touch') {
            dismissed = null;
            if (active?.root === rootFor(trigger)) close();
            else open(rootFor(trigger), 'touch');
        }
        // Mouse clicks never pin help open; hover alone controls its lifetime.
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && active) {
            event.preventDefault();
            dismissed = active.root;
            close();
        }
    });
    window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position);
    document.addEventListener('scroll', position, true);
    document.addEventListener('DOMContentLoaded', init);
    document.addEventListener('htmx:load', init);
    document.addEventListener('htmx:historyRestore', init);
    document.addEventListener('htmx:beforeSwap', close);
    document.addEventListener('htmx:beforeHistorySave', close);
    window.TuxedoHelp = { init, close };
}());
