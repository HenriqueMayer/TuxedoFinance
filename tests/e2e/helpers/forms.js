const { expect } = require('@playwright/test');

// Existing smoke tests exercise both short native choices and model pickers.
async function selectChoice(locator, choice) {
    const page = locator.page();
    if (await locator.evaluate(element => element.tagName !== 'SELECT'
        && Boolean(element.querySelector('input[type="radio"]')))) {
        // Short choices use native grouped radios; record choices below retain
        // their shared searchable select and keyboard confirmation contract.
        const radio = typeof choice === 'object'
            ? locator.getByRole('radio', {name: choice.label, exact: true})
            : locator.locator(`input[type="radio"][value="${choice}"]`);
        return radio.press('Space');
    }
    if (await locator.evaluate(element => element.tagName === 'SELECT' && !element.hidden)) {
        return locator.selectOption(choice);
    }
    const selectId = await locator.evaluate(element => element.tagName === 'SELECT'
        ? element.id : element.closest('.search-choice').previousElementSibling.id);
    const select = page.locator(`[id="${selectId}"]`);
    const searchId = await select.getAttribute('data-search-id') || `${selectId}-search`;
    const input = page.locator(`[id="${searchId}"]`);
    if (choice === '') {
        await input.locator('..').getByRole('button').click();
        await input.press('Escape');
        return;
    }
    const label = typeof choice === 'object' ? choice.label : await select.locator('option').evaluateAll(
        (options, value) => options.find(option => option.value === value).textContent, choice);
    await input.fill(label);
    const options = input.locator('..').getByRole('option');
    // Illustrated choices retain the complete native record name as their
    // accessible label while arranging the visible title/context separately.
    const index = (await options.evaluateAll(items => items.map(item =>
        item.getAttribute('aria-label') || item.textContent))).indexOf(label);
    expect(index).toBeGreaterThanOrEqual(0);
    for (let i = 0; i <= index; i++) await input.press('ArrowDown');
    await input.press('Enter');
    if (await select.getAttribute('data-payment-choices') !== null) {
        // The payment board stays visible and restores all options after a
        // commit. Its compact input is a filter, not the selected-record label.
        await expect(select).toHaveValue(typeof choice === 'object'
            ? await select.locator('option').evaluateAll((options, targetLabel) => options.find(option => option.textContent === targetLabel).value, label) : choice);
        await expect(input).toHaveValue('');
    } else await expect(input).toHaveValue(label);
}
module.exports = { selectChoice };
