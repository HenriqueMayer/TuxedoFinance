(function () {
    'use strict';
    if (window.TuxedoSandbox) return;
    window.TuxedoSandbox = true;

    function indexRows() {
        ['variable', 'deduction'].forEach(function (prefix) {
            document.querySelectorAll('[data-' + prefix + '-row]').forEach(function (row, index) {
                var button = row.querySelector('[data-remove-' + prefix + ']');
                if (button) button.value = 'remove_' + prefix + '_' + index;
            });
        });
    }

    document.addEventListener('click', function (event) {
        var clearButton = event.target.closest('[data-clear-planning]');
        if (clearButton) {
            event.preventDefault();
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

        var addDeductionButton = event.target.closest('[data-add-deduction]');
        if (addDeductionButton) {
            event.preventDefault();
            var deductionWorkspace = addDeductionButton.closest('#sandbox-workspace');
            var deductionTemplate = deductionWorkspace && deductionWorkspace.querySelector('#sandbox-deduction-template');
            var deductionContainer = deductionWorkspace && deductionWorkspace.querySelector('[data-deduction-rows]');
            if (deductionTemplate && deductionContainer) {
                deductionContainer.insertAdjacentHTML('beforeend', deductionTemplate.innerHTML.trim());
                var deductionLabels = deductionContainer.querySelectorAll('input[name="deduction_label"]');
                indexRows();
                deductionLabels[deductionLabels.length - 1].focus();
            }
            return;
        }

        var removeDeductionButton = event.target.closest('[data-remove-deduction]');
        if (removeDeductionButton) {
            event.preventDefault();
            var deductionRow = removeDeductionButton.closest('[data-deduction-row]');
            if (deductionRow) deductionRow.remove();
            indexRows();
        }
    });

    var timer;
    var controller;
    var generation = 0;
    document.addEventListener('input', function (event) {
        var form = event.target.closest('[data-yield-simulation]');
        if (!form || event.target.name === 'draft_name') return;
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
