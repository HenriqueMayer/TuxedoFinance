/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoDatePicker) return;
    const instances = new Map();

    // One calendar engine serves the catalogue and explicitly opted-in fields.
    // Preferred-date text remains the submitted field; ISO is used internally.
    function createPicker(options) {
        const initialized = new WeakSet();
        const namespace = options.namespace || 'date-picker';
        const selector = options.selector || '[data-date-picker]';
        const locale = options.locale || document.documentElement.lang || 'en-US';
        const copy = (key, fallback) => document.querySelector('[data-form-ui-strings]')?.dataset[key] || fallback;
        const messages = {
            choose: copy('calendarChooseDate', 'Choose date'),
            previous: copy('calendarPreviousMonth', 'Previous month'),
            next: copy('calendarNextMonth', 'Next month'),
            month: copy('calendarMonth', 'Month'),
            year: copy('calendarYear', 'Year'),
            today: copy('calendarToday', 'Today'),
            clear: copy('calendarClear', 'Clear'),
            close: copy('calendarClose', 'Close'),
        };
        const supported = typeof HTMLDialogElement !== 'undefined' && typeof HTMLDialogElement.prototype.showModal === 'function';
        const monthFormat = new Intl.DateTimeFormat(locale, {month: 'long', year: 'numeric', timeZone: 'UTC'});
        const dayFormat = new Intl.DateTimeFormat(locale, {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC'});
        let dialog, month, year, heading, grid, previous, next, todayButton;
        let owner = null, active = null, view = null, observer = null, resizeObserver = null;
        const adapters = new WeakMap();

        function element(tag, className, text) {
            const node = document.createElement(tag);
            if (className) node.className = className;
            if (text !== undefined) node.textContent = text;
            return node;
        }
        function date(yearValue, monthValue, dayValue) {
            // UTC is used only for calendar arithmetic, never converted to local
            // midnight. setUTCFullYear also avoids Date's special treatment of 0–99.
            const value = new Date(0);
            value.setUTCHours(12, 0, 0, 0);
            value.setUTCFullYear(yearValue, monthValue - 1, dayValue);
            return value;
        }
        function parts(value) { return {year: value.getUTCFullYear(), month: value.getUTCMonth() + 1, day: value.getUTCDate()}; }
        function iso(value) { return `${String(value.year).padStart(4, '0')}-${String(value.month).padStart(2, '0')}-${String(value.day).padStart(2, '0')}`; }
        function parse(value) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
            const [yearValue, monthValue, dayValue] = value.split('-').map(Number);
            const result = parts(date(yearValue, monthValue, dayValue));
            return result.year >= 1 && result.year <= 9999 && iso(result) === value ? result : null;
        }
        function today() { const value = new Date(); return {year: value.getFullYear(), month: value.getMonth() + 1, day: value.getDate()}; }
        function bounds() {
            const adapter = owner && adapters.get(owner);
            return {
                min: parse(owner?.getAttribute('min') || adapter?.picker?.min) || {year: 1, month: 1, day: 1},
                max: parse(owner?.getAttribute('max') || adapter?.picker?.max) || {year: 9999, month: 12, day: 31},
            };
        }
        function read(input) {
            const raw = input.value.trim();
            const canonical = parse(raw);
            if (canonical || input.type === 'date') return canonical;
            const adapter = adapters.get(input);
            const matched = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
                || raw.match(/^(\d{2})(\d{2})(\d{4})$/);
            if (!matched) return null;
            const [, first, second, yearValue] = matched;
            const monthValue = adapter?.order === 'MDY' ? first : second;
            const dayValue = adapter?.order === 'MDY' ? second : first;
            return parse(`${yearValue}-${monthValue.padStart(2, '0')}-${dayValue.padStart(2, '0')}`);
        }
        function write(input, value) {
            const adapter = adapters.get(input);
            const canonical = value ? iso(value) : '';
            if (input.type === 'date' || !value) input.value = canonical;
            else {
                const [yearValue, monthValue, dayValue] = canonical.split('-');
                input.value = adapter?.order === 'MDY' ? `${monthValue}/${dayValue}/${yearValue}` : `${dayValue}/${monthValue}/${yearValue}`;
            }
            if (adapter?.picker) adapter.picker.value = canonical;
        }
        function dayKey(value) { return value.year * 10000 + value.month * 100 + value.day; }
        function allowed(value) { const range = bounds(), key = dayKey(value); return value.year >= 1 && value.year <= 9999 && key >= dayKey(range.min) && key <= dayKey(range.max); }
        function clamp(value) { const range = bounds(); return dayKey(value) < dayKey(range.min) ? range.min : dayKey(value) > dayKey(range.max) ? range.max : value; }
        function addDays(value, amount) { return parts(date(value.year, value.month, value.day + amount)); }
        function addMonths(value, amount) {
            const first = parts(date(value.year, value.month + amount, 1));
            const last = parts(date(first.year, first.month + 1, 0)).day;
            return {year: first.year, month: first.month, day: Math.min(value.day, last)};
        }
        function usable(input) {
            if (!input?.isConnected || input.matches(':disabled') || input.readOnly
                || !input.getClientRects().length || getComputedStyle(input).visibility !== 'visible') return false;
            // Closed details may retain descendant layout boxes. Do not leave a
            // modal attached to a date field that its disclosure no longer shows.
            for (let parent = input.parentElement; parent; parent = parent.parentElement) {
                if (parent.tagName === 'DETAILS' && !parent.open && !parent.querySelector(':scope > summary')?.contains(input)) return false;
            }
            return true;
        }
        function button(text, action) {
            const control = element('button', '', text);
            control.type = 'button';
            control.dataset.calendarAction = action;
            return control;
        }
        function close(returnFocus = true) {
            if (!owner) return;
            const input = owner;
            owner = null;
            observer?.disconnect();
            resizeObserver?.disconnect();
            input.setAttribute('aria-expanded', 'false');
            adapters.get(input)?.trigger?.setAttribute('aria-expanded', 'false');
            const x = window.scrollX, y = window.scrollY;
            if (dialog.open) dialog.close();
            active = view = null;
            grid.replaceChildren();
            heading.textContent = '';
            year.value = '';
            if (returnFocus && usable(input)) input.focus({preventScroll: true});
            if (window.scrollX !== x || window.scrollY !== y) window.scrollTo({left: x, top: y, behavior: 'instant'});
        }
        function position() {
            if (!owner || !dialog.open) return;
            if (!usable(owner)) { close(false); return; }
            const viewport = window.visualViewport;
            const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
            const width = viewport?.width || window.innerWidth, height = viewport?.height || window.innerHeight;
            const anchor = owner.getBoundingClientRect();
            dialog.style.position = 'fixed';
            dialog.style.margin = '0';
            dialog.style.width = `${Math.max(0, Math.min(344, width - 16))}px`;
            dialog.style.maxHeight = `${Math.max(0, height - 16)}px`;
            const box = dialog.getBoundingClientRect();
            const targetLeft = Math.max(left + 8, Math.min(anchor.left, left + width - box.width - 8));
            const below = top + height - anchor.bottom - 8;
            const targetTop = below >= box.height ? anchor.bottom + 8
                : anchor.top - top - 8 >= box.height ? anchor.top - box.height - 8 : top + 8;
            dialog.style.left = `${targetLeft}px`;
            dialog.style.top = `${Math.max(top + 8, Math.min(targetTop, top + height - box.height - 8))}px`;
        }
        function focusDay() { grid.querySelector('[tabindex="0"]')?.focus({preventScroll: true}); }
        function render() {
            if (!owner) return;
            const range = bounds(), selected = read(owner), now = iso(today());
            const monthLabel = monthFormat.format(date(view.year, view.month, 1));
            // Announce a changed month, not the same heading on every day move.
            if (heading.textContent !== monthLabel) heading.textContent = monthLabel;
            grid.setAttribute('aria-labelledby', heading.id);
            month.value = String(view.month);
            year.min = String(range.min.year);
            year.max = String(range.max.year);
            year.value = String(view.year);
            Array.from(month.options).forEach(option => {
                const first = {year: view.year, month: Number(option.value), day: 1};
                const last = parts(date(first.year, first.month + 1, 0));
                option.disabled = dayKey(last) < dayKey(range.min) || dayKey(first) > dayKey(range.max);
            });
            previous.disabled = dayKey(parts(date(view.year, view.month, 0))) < dayKey(range.min);
            next.disabled = dayKey(parts(date(view.year, view.month + 1, 1))) > dayKey(range.max);
            todayButton.disabled = !allowed(today());
            grid.replaceChildren();
            const first = date(view.year, view.month, 1);
            const offset = (first.getUTCDay() + 6) % 7;
            const beginning = addDays(parts(first), -offset);
            for (let week = 0; week < 6; week++) {
                const row = element('div', `${namespace}-week`);
                row.setAttribute('role', 'row');
                for (let day = 0; day < 7; day++) {
                    const value = addDays(beginning, week * 7 + day), key = iso(value);
                    const control = element('button', `${namespace}-day`, String(value.day));
                    control.type = 'button';
                    control.dataset.date = key;
                    control.setAttribute('role', 'gridcell');
                    control.setAttribute('aria-label', dayFormat.format(date(value.year, value.month, value.day)));
                    control.setAttribute('aria-selected', String(Boolean(selected && key === iso(selected))));
                    if (key === now) control.setAttribute('aria-current', 'date');
                    control.tabIndex = key === iso(active) && allowed(value) ? 0 : -1;
                    control.disabled = !allowed(value);
                    control.classList.toggle('is-outside', value.month !== view.month);
                    control.classList.toggle('is-selected', Boolean(selected && key === iso(selected)));
                    row.append(control);
                }
                grid.append(row);
            }
            position();
        }
        function move(value, focus = true) {
            active = clamp(value);
            view = {year: active.year, month: active.month};
            render();
            if (focus) focusDay();
        }
        function commit(value) {
            if (!owner || (value && !allowed(value))) return;
            const input = owner;
            write(input, value);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            close();
        }
        function createDialog() {
            dialog = element('dialog', namespace);
            dialog.id = namespace;
            dialog.setAttribute('aria-labelledby', `${namespace}-title`);
            const head = element('div', `${namespace}-head`);
            const title = element('h3', `${namespace}-title`, messages.choose);
            title.id = `${namespace}-title`;
            heading = element('p', `${namespace}-month-label`);
            heading.id = `${namespace}-month-label`;
            heading.setAttribute('aria-live', 'polite');
            heading.setAttribute('aria-atomic', 'true');
            head.append(title, heading);
            const controls = element('div', `${namespace}-controls`);
            previous = button('‹', 'prev'); previous.setAttribute('aria-label', messages.previous);
            next = button('›', 'next'); next.setAttribute('aria-label', messages.next);
            month = element('select'); month.id = `${namespace}-month`; month.setAttribute('aria-label', messages.month);
            for (let number = 1; number <= 12; number++) {
                const option = element('option', '', new Intl.DateTimeFormat(locale, {month: 'long', timeZone: 'UTC'}).format(date(2026, number, 1)));
                option.value = String(number); month.append(option);
            }
            year = element('input'); year.id = `${namespace}-year`; year.type = 'number'; year.inputMode = 'numeric'; year.step = '1'; year.setAttribute('aria-label', messages.year);
            controls.append(previous, month, year, next);
            const weekdays = element('div', `${namespace}-weekdays`);
            weekdays.setAttribute('aria-hidden', 'true');
            const weekdayFormat = new Intl.DateTimeFormat(locale, {weekday: 'short', timeZone: 'UTC'});
            for (let number = 1; number <= 7; number++) {
                weekdays.append(element('span', '', weekdayFormat.format(date(2026, 6, number))));
            }
            grid = element('div', `${namespace}-grid`); grid.setAttribute('role', 'grid');
            const footer = element('div', `${namespace}-footer`);
            todayButton = button(messages.today, 'today');
            const clear = button(messages.clear, 'clear'), dismiss = button(messages.close, 'close');
            dismiss.className = `${namespace}-close`;
            footer.append(todayButton, clear, dismiss);
            dialog.append(head, controls, weekdays, grid, footer);
            document.body.append(dialog);
            previous.addEventListener('click', () => move(addMonths(active, -1), false));
            next.addEventListener('click', () => move(addMonths(active, 1), false));
            month.addEventListener('change', () => {
                const target = {year: view.year, month: Number(month.value), day: Math.min(active.day, parts(date(view.year, Number(month.value) + 1, 0)).day)};
                move(target, false);
            });
            function changeYear(focus = false) {
                const range = bounds();
                const number = Number(year.value);
                if (!year.value.trim() || !Number.isInteger(number)) { year.value = String(view.year); return; }
                const targetYear = Math.max(range.min.year, Math.min(range.max.year, number));
                const day = Math.min(active.day, parts(date(targetYear, view.month + 1, 0)).day);
                move({year: targetYear, month: view.month, day}, focus);
            }
            year.addEventListener('change', () => changeYear());
            year.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); changeYear(true); } });
            todayButton.addEventListener('click', () => commit(today()));
            clear.addEventListener('click', () => commit(null));
            dismiss.addEventListener('click', () => close());
            grid.addEventListener('click', event => { const day = event.target.closest('button[data-date]'); if (day && !day.disabled) commit(parse(day.dataset.date)); });
            grid.addEventListener('keydown', event => {
                if (!event.target.closest('button[data-date]') || event.altKey || event.ctrlKey || event.metaKey) return;
                let target;
                if (event.key === 'ArrowLeft') target = addDays(active, -1);
                if (event.key === 'ArrowRight') target = addDays(active, 1);
                if (event.key === 'ArrowUp') target = addDays(active, -7);
                if (event.key === 'ArrowDown') target = addDays(active, 7);
                const weekday = (date(active.year, active.month, active.day).getUTCDay() + 6) % 7;
                if (event.key === 'Home') target = addDays(active, -weekday);
                if (event.key === 'End') target = addDays(active, 6 - weekday);
                if (event.key === 'PageUp') target = addMonths(active, event.shiftKey ? -12 : -1);
                if (event.key === 'PageDown') target = addMonths(active, event.shiftKey ? 12 : 1);
                if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); commit(active); return; }
                if (target) { event.preventDefault(); move(target); }
            });
            dialog.addEventListener('keydown', event => {
                if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey) return;
                const controls = Array.from(dialog.querySelectorAll('button, input, select, textarea, a[href], [tabindex]'))
                    .filter(control => control.tabIndex >= 0 && !control.matches(':disabled') && control.getClientRects().length);
                const first = controls[0], last = controls[controls.length - 1];
                // Native modal inertness can still cycle focus through body. Keep
                // both keyboard boundaries inside, preserving the one day Tab stop.
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus({preventScroll: true});
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus({preventScroll: true});
                }
            });
            dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
            dialog.addEventListener('click', event => {
                if (event.target !== dialog) return;
                const box = dialog.getBoundingClientRect();
                if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
            });
            // A delayed close event from the previous owner must not dismiss a
            // dialog already reopened for another field.
            dialog.addEventListener('close', () => { if (owner && !dialog.open) close(); });
            window.addEventListener('resize', position, {passive: true});
            window.addEventListener('scroll', position, {passive: true, capture: true});
            window.visualViewport?.addEventListener('resize', position, {passive: true});
            window.visualViewport?.addEventListener('scroll', position, {passive: true});
            document.addEventListener('visibilitychange', () => { if (document.hidden) close(false); });
        }
        function open(input) {
            if (!usable(input)) return;
            if (!dialog) createDialog();
            else if (!dialog.isConnected) document.body.append(dialog);
            if (owner === input && dialog.open) return;
            if (owner) close(false);
            owner = input;
            active = clamp(read(input) || today());
            view = {year: active.year, month: active.month};
            input.focus({preventScroll: true});
            input.setAttribute('aria-expanded', 'true');
            adapters.get(input)?.trigger?.setAttribute('aria-expanded', 'true');
            render();
            dialog.showModal();
            position();
            focusDay();
            // Observe ownership only while open, including HTMX removal and
            // conditional groups. Closed calendars retain no selected date.
            observer ||= new MutationObserver(() => { if (owner && !usable(owner)) close(false); });
            observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['disabled', 'hidden', 'open', 'class', 'style']});
            if (typeof ResizeObserver !== 'undefined') {
                resizeObserver ||= new ResizeObserver(position);
                resizeObserver.observe(input);
            }
        }
        function initialize(root = document) {
            if (!supported || !root?.querySelectorAll) return;
            const targets = [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)];
            targets.forEach(target => {
                const group = target.matches('[data-preferred-date-field]') ? target : target.closest('[data-preferred-date-field]');
                const input = target.matches('input') ? target : target.querySelector('input:not([data-native-date-picker])');
                if (!input || initialized.has(input)) return;
                initialized.add(input);
                const picker = group?.querySelector('[data-native-date-picker]');
                const trigger = group?.querySelector('[data-open-date-picker]');
                adapters.set(input, {picker, trigger, order: input.dataset.dateOrder || group?.dataset.dateOrder || 'DMY'});
                input.dataset.calendarEnhanced = 'true';
                if (group) group.dataset.calendarEnhanced = 'true';
                input.setAttribute('aria-haspopup', 'dialog');
                input.setAttribute('aria-controls', namespace);
                input.setAttribute('aria-expanded', 'false');
                input.addEventListener('click', event => { if (!usable(input)) return; event.preventDefault(); open(input); });
                input.addEventListener('keydown', event => {
                    if (event.isComposing || event.ctrlKey || event.metaKey) return;
                    if ((event.altKey && event.key === 'ArrowDown') || (!event.altKey && ['Enter', ' '].includes(event.key))) {
                        event.preventDefault(); open(input);
                    }
                });
                if (trigger) {
                    trigger.hidden = false;
                    trigger.disabled = input.matches(':disabled') || input.readOnly;
                    trigger.setAttribute('aria-haspopup', 'dialog');
                    trigger.setAttribute('aria-controls', namespace);
                    trigger.setAttribute('aria-expanded', 'false');
                    // Preferred dates still owns textual formatting and its native
                    // fallback. Capture this opt-in trigger before showPicker runs.
                    trigger.addEventListener('click', event => {
                        if (!usable(input)) return;
                        event.preventDefault();
                        event.stopImmediatePropagation();
                        open(input);
                    }, true);
                }
                input.addEventListener('change', () => { if (owner === input) move(read(input) || today(), false); });
                input.form?.addEventListener('reset', () => { if (owner === input) close(); });
            });
        }
        return {initialize, close, owns: target => Boolean(owner && target?.contains(owner))};
    }
    function initialize(root = document, options = {}) {
        const namespace = options.namespace || 'date-picker';
        if (!instances.has(namespace)) instances.set(namespace, createPicker(options));
        instances.get(namespace).initialize(root);
    }
    function closeAll(returnFocus = false) { instances.forEach(picker => picker.close(returnFocus)); }
    window.TuxedoDatePicker = {initialize, closeAll};
    document.addEventListener('DOMContentLoaded', () => initialize());
    document.addEventListener('htmx:load', event => initialize(event.detail.elt));
    document.addEventListener('htmx:historyRestore', () => initialize());
    document.addEventListener('htmx:beforeSwap', event => {
        instances.forEach(picker => { if (picker.owns(event.detail.target)) picker.close(false); });
    });
    window.addEventListener('pagehide', () => closeAll(false));
    if (document.readyState !== 'loading') initialize();
})();
