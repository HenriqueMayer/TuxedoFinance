const { expect } = require('@playwright/test');

// Existing smoke tests exercise both short native choices and model pickers.
async function selectChoice(locator, choice) {
    const page = locator.page();
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
    const index = (await options.allTextContents()).indexOf(label);
    expect(index).toBeGreaterThanOrEqual(0);
    for (let i = 0; i <= index; i++) await input.press('ArrowDown');
    await input.press('Enter');
    await expect(input).toHaveValue(label);
}
module.exports = { selectChoice };
