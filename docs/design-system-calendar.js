/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    // Keep catalogue IDs and classes while sharing the production calendar.
    function initialize(root = document) {
        window.TuxedoDatePicker?.initialize(root, {
            selector: 'input[type="date"][data-lab-calendar]',
            namespace: 'lab-calendar',
            locale: 'en-US',
        });
    }
    window.TuxedoLabCalendar = {initialize};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initialize(), {once: true});
    else initialize();
}());
