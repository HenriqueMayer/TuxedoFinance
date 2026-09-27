(function () {
    'use strict';
    if (window.TuxedoSandbox) return;
    window.TuxedoSandbox = true;

    function indexRows() {
        document.querySelectorAll('[data-variable-row]').forEach(function (row, index) {
            var button = row.querySelector('[data-remove-variable]');
            if (button) button.value = 'remove_variable_' + index;
        });
    }

    document.addEventListener('click', function (event) {
        var monthInput = event.target.closest('input[type="month"]');
        if (monthInput && monthInput.showPicker) {
            // Expand the native picker's click target while retaining native keyboard entry.
            try { monthInput.showPicker(); } catch (_) { /* Native input remains usable. */ }
        }
        var preset = event.target.closest('[data-months]');
        if (preset) {
            var simulation = preset.closest('form');
            simulation.elements.months.value = preset.dataset.months;
            simulation.elements.months.dispatchEvent(new Event('input', { bubbles: true }));
        }
        var addButton = event.target.closest('[data-add-variable]');
        if (addButton) {
            event.preventDefault();
            var workspace = addButton.closest('#sandbox-workspace');
            var template = workspace && workspace.querySelector('#sandbox-variable-template');
            var container = workspace && workspace.querySelector('[data-variable-rows]');
            if (template && container) {
                container.insertAdjacentHTML('beforeend', template.innerHTML.trim());
                var labels = container.querySelectorAll('input[name="variable_label"]');
                indexRows();
                labels[labels.length - 1].focus();
            }
            return;
        }

        var removeButton = event.target.closest('[data-remove-variable]');
        if (removeButton) {
            event.preventDefault();
            var row = removeButton.closest('[data-variable-row]');
            if (!row) return;
            row.remove();
            indexRows();
            return;
        }

    });

    document.addEventListener('change', function (event) {
        if (event.target.name !== 'planning_month') return;
        var form = event.target.closest('form');
        var submitter = form && form.querySelector('#budget-forecast');
        if (submitter) form.requestSubmit(submitter);
    });

    var timer;
    var controller;
    var generation = 0;
    function syncYieldRows(form) {
        var months = Number(form.elements.months.value);
        if (!Number.isInteger(months) || months < 1 || months > 120) return;
        var container = form.querySelector('[data-yield-rows]');
        var template = form.querySelector('#yield-override-template');
        while (container.children.length < months) {
            var index = container.children.length;
            container.insertAdjacentHTML('beforeend', template.innerHTML
                .replaceAll('__index__', String(index)).replaceAll('__number__', String(index + 1)));
        }
        // Temporarily shortening the duration must not erase the user's edits.
        // Inactive rows stay out of submission and keyboard navigation.
        Array.from(container.children).forEach(function (row, index) {
            row.hidden = index >= months;
            row.querySelectorAll('input').forEach(input => { input.disabled = row.hidden; });
        });
        form.querySelector('[data-update-yield-rows]').hidden = true;
    }
    function syncParameterLabels(form) {
        var rateLabel = form.elements.rate_period.value === 'annual' ? form.dataset.annualRate : form.dataset.monthlyRate;
        var rateWrapper = form.elements.rate.closest('.space-y-2');
        rateWrapper.querySelector('label').firstChild.textContent = rateLabel + ' ';
        rateWrapper.querySelectorAll('.help-title').forEach(title => { title.textContent = rateLabel; });
        // The help describes both periods; its accessible label follows the chosen period.
        rateWrapper.querySelectorAll('.help-trigger').forEach(trigger => {
            trigger.setAttribute('aria-label', form.dataset.explain + ' ' + rateLabel);
        });
        form.querySelectorAll('[data-currency-field] label').forEach(function (label) {
            if (!label.dataset.originalLabel) label.dataset.originalLabel = label.firstChild.textContent.trim();
            label.firstChild.textContent = label.dataset.originalLabel + ' (' + form.elements.currency.value + ') ';
        });
        form.querySelectorAll('[data-months]').forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.dataset.months === form.elements.months.value));
        });
        form.querySelector('[data-duration-presets]').hidden = false;
    }
    function initYieldForms() {
        document.querySelectorAll('[data-yield-simulation]').forEach(function (form) {
            syncYieldRows(form);
            syncParameterLabels(form);
        });
        var forecast = document.getElementById('budget-forecast');
        if (forecast) forecast.hidden = true;
    }
    document.addEventListener('DOMContentLoaded', initYieldForms);
    document.addEventListener('htmx:load', initYieldForms);
    document.addEventListener('tuxedo:restore', initYieldForms);
    initYieldForms();
    document.addEventListener('input', function (event) {
        var form = event.target.closest('[data-yield-simulation]');
        if (!form || event.target.name === 'draft_name') return;
        if (event.target.name === 'months') syncYieldRows(form);
        syncParameterLabels(form);
        clearTimeout(timer);
        if (controller) controller.abort();
        var current = ++generation;
        timer = setTimeout(function () {
            controller = new AbortController();
            var data = new FormData(form);
            data.set('action', 'calculate');
            data.set('response_mode', 'result');
            var message = form.querySelector('[data-live-message]');
            message.textContent = form.querySelector('[data-live-updating]').textContent;
            fetch(form.getAttribute('action'), {method: 'POST', body: data, signal: controller.signal, credentials: 'same-origin'})
                .then(function (response) { if (!response.ok) throw new Error('Calculation failed'); return response.text(); })
                .then(function (html) {
                    if (current !== generation || !form.isConnected) return;
                    var documentResult = new DOMParser().parseFromString(html, 'text/html');
                    var result = documentResult.getElementById('simulation-result');
                    if (!result) throw new Error('Missing result');
                    var breakdown = form.querySelector('#yield-monthly-results');
                    var nextBreakdown = result.querySelector('#yield-monthly-results');
                    if (breakdown && nextBreakdown) nextBreakdown.open = breakdown.open;
                    window.TuxedoHelp?.close();
                    form.querySelector('#simulation-result').replaceWith(result);
                    window.TuxedoHelp?.init();
                    message.textContent = form.querySelector('[data-live-updated]').textContent;
                })
                .catch(function (error) {
                    if (error.name !== 'AbortError' && form.isConnected) message.textContent = form.querySelector('[data-live-failed]').textContent;
                });
        }, 600);
    });
    document.addEventListener('submit', function (event) {
        if (event.target.matches('[data-yield-simulation]')) {
            clearTimeout(timer);
            if (controller) controller.abort();
            generation += 1;
        }
    });
}());
