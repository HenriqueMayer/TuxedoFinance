(function () {
    'use strict';

    var activeHelp = null;
    var closeTimer = null;

    function helpParts(popover) {
        return {
            trigger: popover && popover.querySelector('[data-help-trigger]'),
            content: popover && popover.querySelector('[data-help-content]'),
        };
    }

    function positionHelpPopover(popover) {
        var parts = helpParts(popover);
        if (!parts.trigger || !parts.content || parts.content.hidden) return;

        var gutter = 12;
        var gap = 8;
        var width = Math.min(320, window.innerWidth - gutter * 2);
        parts.content.style.width = width + 'px';
        parts.content.style.visibility = 'hidden';
        var triggerRect = parts.trigger.getBoundingClientRect();
        var contentRect = parts.content.getBoundingClientRect();
        var left = triggerRect.left + triggerRect.width / 2 - contentRect.width / 2;
        left = Math.max(gutter, Math.min(left, window.innerWidth - contentRect.width - gutter));
        var top = triggerRect.bottom + gap;
        if (top + contentRect.height > window.innerHeight - gutter) {
            top = triggerRect.top - contentRect.height - gap;
        }
        top = Math.max(gutter, Math.min(top, window.innerHeight - contentRect.height - gutter));
        parts.content.style.left = Math.round(left) + 'px';
        parts.content.style.top = Math.round(top) + 'px';
        parts.content.style.visibility = 'visible';
    }

    function closeHelpPopover(restoreFocus) {
        if (!activeHelp) return;
        var parts = helpParts(activeHelp);
        if (closeTimer) window.clearTimeout(closeTimer);
        if (parts.content) parts.content.hidden = true;
        if (parts.trigger) {
            parts.trigger.setAttribute('aria-expanded', 'false');
            if (restoreFocus) parts.trigger.focus();
        }
        activeHelp.removeAttribute('data-help-open');
        activeHelp.removeAttribute('data-help-pinned');
        activeHelp = null;
    }

    function openHelpPopover(popover, pinned) {
        if (!popover) return;
        if (activeHelp && activeHelp !== popover) closeHelpPopover(false);
        if (closeTimer) window.clearTimeout(closeTimer);
        var parts = helpParts(popover);
        if (!parts.trigger || !parts.content) return;
        activeHelp = popover;
        popover.setAttribute('data-help-open', '');
        if (pinned) popover.setAttribute('data-help-pinned', '');
        parts.trigger.setAttribute('aria-expanded', 'true');
        parts.content.hidden = false;
        positionHelpPopover(popover);
    }

    function scheduleHelpClose(popover) {
        if (!popover || popover.hasAttribute('data-help-pinned')) return;
        if (closeTimer) window.clearTimeout(closeTimer);
        closeTimer = window.setTimeout(function () {
            if (activeHelp === popover && !popover.hasAttribute('data-help-pinned')) {
                closeHelpPopover(false);
            }
        }, 120);
    }

    document.addEventListener('pointerover', function (event) {
        var trigger = event.target.closest && event.target.closest('[data-help-trigger]');
        var content = event.target.closest && event.target.closest('[data-help-content]');
        var popover = (trigger || content) && (trigger || content).closest('[data-help-popover]');
        if (popover) openHelpPopover(popover, popover.hasAttribute('data-help-pinned'));
    });

    document.addEventListener('pointerout', function (event) {
        var part = event.target.closest && event.target.closest('[data-help-trigger], [data-help-content]');
        if (!part) return;
        var popover = part.closest('[data-help-popover]');
        if (popover && !popover.contains(event.relatedTarget)) scheduleHelpClose(popover);
    });

    document.addEventListener('focusin', function (event) {
        var trigger = event.target.closest && event.target.closest('[data-help-trigger]');
        if (trigger) openHelpPopover(trigger.closest('[data-help-popover]'), false);
    });

    document.addEventListener('focusout', function (event) {
        var trigger = event.target.closest && event.target.closest('[data-help-trigger]');
        if (trigger) scheduleHelpClose(trigger.closest('[data-help-popover]'));
    });

    document.addEventListener('click', function (event) {
        var helpTrigger = event.target.closest('[data-help-trigger]');
        if (helpTrigger) {
            event.preventDefault();
            var helpPopover = helpTrigger.closest('[data-help-popover]');
            if (activeHelp === helpPopover && helpPopover.hasAttribute('data-help-pinned')) {
                closeHelpPopover(false);
            } else {
                openHelpPopover(helpPopover, true);
            }
            return;
        }
        if (activeHelp && !activeHelp.contains(event.target)) {
            closeHelpPopover(false);
        }

        var clearButton = event.target.closest('[data-clear-planning]');
        if (clearButton) {
            var form = clearButton.closest('form');
            ['fixed_cost_value', 'emergency_percent', 'investments_percent'].forEach(function (name) {
                var input = form && form.elements[name];
                if (input) input.value = '';
            });
            var rows = form && form.querySelector('[data-variable-rows]');
            if (rows) rows.replaceChildren();
            return;
        }

        var addButton = event.target.closest('[data-add-variable]');
        if (addButton) {
            var workspace = addButton.closest('#sandbox-workspace');
            var template = workspace && workspace.querySelector('#sandbox-variable-template');
            var container = workspace && workspace.querySelector('[data-variable-rows]');
            if (template && container) {
                container.insertAdjacentHTML('beforeend', template.innerHTML.trim());
                var labels = container.querySelectorAll('input[name="variable_label"]');
                labels[labels.length - 1].focus();
            }
            return;
        }

        var removeButton = event.target.closest('[data-remove-variable]');
        if (removeButton) {
            var row = removeButton.closest('[data-variable-row]');
            if (!row) return;
            row.remove();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        if (!activeHelp) return;
        event.preventDefault();
        closeHelpPopover(true);
    });

    window.addEventListener('resize', function () {
        if (activeHelp) positionHelpPopover(activeHelp);
    });

    document.addEventListener('scroll', function () {
        if (activeHelp) positionHelpPopover(activeHelp);
    }, true);

    document.addEventListener('htmx:beforeSwap', function () {
        closeHelpPopover(false);
    });
}());
