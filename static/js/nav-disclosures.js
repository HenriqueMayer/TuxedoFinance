/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoNavigationMenus) return;
    // Deliberately exclude content accordions and nested roadmap/help details.
    const selector = 'details[data-nav-menu], details.secondary-actions, details[data-project-menu], details[data-export-menu]';
    const states = new WeakMap();
    let pointerType = 'mouse';
    let pointerDownTarget = null;

    function state(menu) {
        if (!states.has(menu)) states.set(menu, { timer: null, pointer: false, hoverOnly: false });
        return states.get(menu);
    }
    function group(menu) { return menu.closest('[data-nav-item]') || menu; }
    function summary(menu) { return menu.querySelector(':scope > summary'); }
    // Option buttons open deliberately; only primary navigation links retain
    // their documented hover preview. Crossing another trigger cannot switch menus.
    function activationOnly(menu) { return menu.matches('.secondary-actions, [data-export-menu], [data-project-menu]'); }
    function helpPanels(menu) {
        return [...menu.querySelectorAll('[data-help-trigger][aria-controls]')]
            .map(trigger => document.getElementById(trigger.getAttribute('aria-controls')))
            .filter(panel => panel && !panel.hidden);
    }
    function contains(menu, target) {
        return target instanceof Node && (group(menu).contains(target)
            || helpPanels(menu).some(panel => panel.contains(target)));
    }
    function menuFor(target) {
        if (!(target instanceof Element)) return null;
        const item = target.closest('[data-nav-item]');
        if (item) return item.querySelector('details[data-nav-menu]');
        const direct = target.closest(selector);
        if (direct) return direct;
        // Shared help lives under body while open; keep its owning menu open.
        const panel = target.closest('[data-help-content]');
        if (!panel) return null;
        return [...document.querySelectorAll(selector)].find(menu => helpPanels(menu).includes(panel)) || null;
    }
    function close(menu, restoreFocus = false) {
        clearTimeout(state(menu).timer);
        if (!menu.open) return;
        if (helpPanels(menu).length) window.TuxedoHelp?.close();
        menu.open = false;
        state(menu).hoverOnly = false;
        summary(menu)?.setAttribute('aria-expanded', 'false');
        if (menu.matches('[data-project-menu]')) {
            menu.querySelectorAll('details[open]').forEach(nested => { nested.open = false; });
        }
        if (restoreFocus) summary(menu)?.focus({ preventScroll: true });
    }
    function open(menu, hover = false) {
        clearTimeout(state(menu).timer);
        if (!menu.open) state(menu).hoverOnly = hover;
        document.querySelectorAll(selector).forEach(other => {
            // Hover must not conceal another menu's focused interactive field.
            if (other !== menu && !contains(other, document.activeElement)) close(other);
        });
        menu.open = true;
        summary(menu)?.setAttribute('aria-expanded', 'true');
    }
    function scheduleClose(menu) {
        const current = state(menu);
        clearTimeout(current.timer);
        current.timer = setTimeout(() => {
            if (!current.pointer && !contains(menu, document.activeElement)) close(menu);
        }, 160);
    }
    function initialize() {
        document.querySelectorAll(selector).forEach(menu => {
            summary(menu)?.setAttribute('aria-expanded', String(menu.open));
            menu.dataset.navReady = 'true';
        });
    }
    function closeAll() { document.querySelectorAll(selector).forEach(menu => close(menu)); }

    document.addEventListener('pointerover', event => {
        if (event.pointerType === 'touch') return;
        const menu = menuFor(event.target);
        if (!menu) return;
        const linkPreview = menu.matches('[data-nav-menu]') && !menu.open
            && group(menu).querySelector(':scope > a')?.contains(event.target);
        if (contains(menu, event.relatedTarget) && !linkPreview) return;
        state(menu).pointer = true;
        // The primary link may preview its submenu; its disclosure button
        // still requires activation like every other options control.
        if (activationOnly(menu) || (menu.matches('[data-nav-menu]') && event.target.closest('summary'))) return;
        open(menu, true);
    });
    document.addEventListener('pointerout', event => {
        if (event.pointerType === 'touch') return;
        const menu = menuFor(event.target);
        if (!menu || contains(menu, event.relatedTarget)) return;
        state(menu).pointer = false;
        // A clicked row menu stays available while the pointer crosses gaps.
        // Its summary, outside interaction, Tab away or Escape will close it.
        if (activationOnly(menu)) return;
        scheduleClose(menu);
    });
    document.addEventListener('pointerdown', event => {
        pointerType = event.pointerType;
        pointerDownTarget = event.target;
        document.querySelectorAll(selector).forEach(menu => {
            if (!contains(menu, event.target)) close(menu);
        });
    });
    document.addEventListener('click', event => {
        const menu = menuFor(event.target);
        if (!menu || !summary(menu)?.contains(event.target)) return;
        // Moving the mouse onto a summary already opens it. Its first click
        // should confirm that opening, rather than immediately undoing it.
        if (event.detail > 0 && pointerType !== 'touch' && menu.open && state(menu).hoverOnly) {
            event.preventDefault();
            state(menu).hoverOnly = false;
        }
    });
    document.addEventListener('focusout', event => {
        const menu = menuFor(event.target);
        if (!menu || !event.target.matches('[data-help-trigger]')) return;
        // Touch focuses the help button. Tapping its non-focusable portal then
        // focuses body, but is not Tab away: keep the shared help visible too.
        if (helpPanels(menu).some(panel => panel.contains(pointerDownTarget))) {
            event.stopPropagation();
        }
    }, true);
    document.addEventListener('focusout', event => {
        const menu = menuFor(event.target);
        if (!menu) return;
        if (contains(menu, event.relatedTarget)) return;
        // focusout runs before the browser assigns the next active element.
        // Use its destination immediately; a null destination needs one task.
        if (event.relatedTarget) { close(menu); return; }
        const pointerDestination = pointerDownTarget;
        setTimeout(() => {
            // Selecting non-focusable portal text focuses body. It is still
            // inside this menu for mouse and touch; outside taps and Tab close.
            if (!contains(menu, document.activeElement) && !state(menu).pointer
                && !contains(menu, pointerDestination)) close(menu);
        }, 0);
    });
    document.addEventListener('toggle', event => {
        if (event.target.matches?.(selector)) {
            summary(event.target)?.setAttribute('aria-expanded', String(event.target.open));
        }
    }, true);
    document.addEventListener('keydown', event => {
        pointerDownTarget = null;
        const menu = menuFor(event.target);
        if (event.key === 'Escape') {
            const target = menu?.open ? menu : [...document.querySelectorAll(selector)].find(item => item.open);
            if (!target) return;
            // Keyboard help can retain focus while the pointer opens a menu
            // elsewhere. Let the shared help handler dismiss that tooltip first.
            if (document.querySelector('[data-help-content]:not([hidden])')) return;
            event.preventDefault();
            event.stopPropagation();
            close(target, contains(target, document.activeElement));
            return;
        }
        if (!menu || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
        const mainLink = group(menu).querySelector(':scope > a');
        if (event.target !== summary(menu) && event.target !== mainLink) return;
        event.preventDefault();
        open(menu);
        const links = [...menu.querySelectorAll('a[href], button:not([disabled]), select:not([disabled])')]
            .filter(control => control.getClientRects().length && !control.closest('[hidden]'));
        (event.key === 'ArrowUp' ? links.at(-1) : links[0])?.focus({ preventScroll: true });
    }, true);
    document.addEventListener('DOMContentLoaded', initialize);
    document.addEventListener('htmx:load', initialize);
    document.addEventListener('htmx:historyRestore', initialize);
    document.addEventListener('htmx:beforeSwap', closeAll);
    document.addEventListener('htmx:beforeHistorySave', closeAll);
    if (document.readyState !== 'loading') initialize();
    window.TuxedoNavigationMenus = { initialize, closeAll };
}());
