(function () {
    'use strict';
    if (window.TuxedoSandbox) return;
    window.TuxedoSandbox = true;

    document.addEventListener('click', function (event) {
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
            return;
        }

        var addDeductionButton = event.target.closest('[data-add-deduction]');
        if (addDeductionButton) {
            var deductionWorkspace = addDeductionButton.closest('#sandbox-workspace');
            var deductionTemplate = deductionWorkspace && deductionWorkspace.querySelector('#sandbox-deduction-template');
            var deductionContainer = deductionWorkspace && deductionWorkspace.querySelector('[data-deduction-rows]');
            if (deductionTemplate && deductionContainer) {
                deductionContainer.insertAdjacentHTML('beforeend', deductionTemplate.innerHTML.trim());
                var deductionLabels = deductionContainer.querySelectorAll('input[name="deduction_label"]');
                deductionLabels[deductionLabels.length - 1].focus();
            }
            return;
        }

        var removeDeductionButton = event.target.closest('[data-remove-deduction]');
        if (removeDeductionButton) {
            var deductionRow = removeDeductionButton.closest('[data-deduction-row]');
            if (deductionRow) deductionRow.remove();
        }
    });

}());
