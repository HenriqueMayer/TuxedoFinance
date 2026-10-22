// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('../helpers/forms');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `investment-routine-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', { form: {
        csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status()).toBe(302);
}

async function tabTo(page, control) {
    for (let count = 0; count < 30; count++) {
        if (await control.evaluate(element => document.activeElement === element)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control is not reachable through the keyboard');
}

for (const width of [390, 1440]) {
for (const theme of ['light', 'dark']) {
test(`guided investments and contextual updates (${width}, ${theme})`, async ({ page }, info) => {
    page.on('dialog', dialog => dialog.accept());
    await page.setViewportSize({ width, height: 780 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await signup(page, info);
    await page.goto('/investments/');
    await page.locator('main header').getByRole('link', { name: 'Add investment', exact: true }).press('Enter');
    await expect(page.locator('#id_valuation_mode')).toHaveValue('');
    await expect(page.locator('#id_new_institution')).not.toBeChecked();
    await expect(page.locator('#guided-values')).toBeHidden();
    await page.locator('#id_new_institution').press('Space');
    await expect(page.locator('#guided-existing-institution')).toBeHidden();
    await page.locator('#id_institution_name').fill('Routine institution');
    await page.locator('#id_name').fill('Routine pot');
    await page.locator('#id_valuation_mode').focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Tab');
    await expect(page.locator('#guided-balance')).toBeVisible();
    await expect(page.locator('#id_purpose')).toHaveValue('');
    await page.locator('#id_purpose').press('End');
    await page.keyboard.press('Tab');
    await tabTo(page, page.locator('#id_planning_enabled'));
    await expect(page.locator('#id_planning_enabled')).not.toBeChecked();
    await page.keyboard.press('Space');
    await page.locator('#id_valuation_mode').press('End');
    await expect(page.locator('#guided-units')).toBeVisible();
    await expect(page.locator('#id_planning_enabled')).not.toBeChecked();
    await expect(page.locator('#guided-planning')).toBeHidden();
    await page.locator('#id_opening_quantity').fill('2');
    await page.locator('#id_valuation_mode').press('Home');
    await page.locator('#id_valuation_mode').press('ArrowDown');
    await expect(page.locator('#id_opening_quantity')).toHaveValue('');
    await page.locator('#id_purpose').press('End');
    await page.locator('#id_opening_balance').fill('100');
    await page.locator('#id_name').press('Enter');
    await expect(page.locator('#id_opening_date')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('#id_new_institution')).toBeChecked();
    await expect(page.locator('#id_opening_balance')).toHaveValue('100');
    await expect(page.locator('#guided-date')).toBeVisible();
    await page.screenshot({ path: info.outputPath(`guided-investment-error-${width}-${theme}.png`), fullPage: true });
    await page.locator('#id_opening_date').fill('01/01/2026');
    await page.locator('#guided-investment-form').getByText('Advanced options', { exact: true }).press('Enter');
    const classificationHelp = page.locator('[data-help-trigger][aria-controls="id_asset_class-help"]');
    const classificationCopy = page.locator('#id_asset_class-help');
    await classificationHelp.hover();
    await expect(classificationCopy).toContainText('existing history locks this choice');
    const bounds = await classificationCopy.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await page.mouse.move(1, 1);
    await expect(classificationCopy).toBeHidden();
    await classificationHelp.focus();
    await expect(classificationCopy).toBeVisible();
    await classificationHelp.press('Escape');
    await expect(classificationCopy).toBeHidden();
    await classificationHelp.press('Tab');
    await expect(page.locator('#id_asset_class')).toBeFocused();
    await page.keyboard.press('End');
    await page.locator('#id_name').press('Enter');
    await expect(page).toHaveURL(/\/investments\/positions\/\d+\/\d+\//);
    await expect(page.locator('main')).toContainText(/BRL 100[,.]00/);
    await expect(page.locator('main')).toContainText('Outside monthly planning');
    await page.locator('main header').getByRole('link', { name: 'Update', exact: true }).press('Enter');
    await expect(page.getByRole('link', { name: 'Update price', exact: true })).toHaveCount(0);
    await page.getByRole('link', { name: 'Record yield', exact: true }).press('Enter');
    await expect(page.locator('#id_kind')).toHaveValue('YIELD');
    await expect(page.locator('input[name="yield_input_mode"]:checked')).toHaveCount(0);
    await page.getByRole('radio', { name: 'Use the final balance', exact: true }).press('Space');
    await page.locator('#id_ending_balance').fill('110');
    await page.locator('#id_date').fill('05/01/2026');
    await page.locator('#id_ending_balance').press('Enter');
    await expect(page).toHaveURL(/\/investments\/positions\/\d+\/\d+\//);
    await expect(page.locator('main')).toContainText(/BRL 110[,.]00/);
    await page.goto('/investments/');
    const search = page.locator('#position-search');
    await search.fill('Routine pot');
    await expect(page.locator('#position-results-status')).toContainText('1 position');
    await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Routine pot');
    await expect(search).toBeFocused();
    await search.fill('unmatched');
    await expect(page.locator('#investment-position-list')).toContainText('No positions match these filters.');
    await expect(search).toBeFocused();
    await page.getByRole('link', { name: 'Clear filters', exact: true }).press('Enter');
    await expect(page.locator('#investment-position-list')).toContainText('Routine pot');
    const tabs = page.getByRole('navigation', { name: 'Investment sections' });
    await expect(tabs.getByRole('link')).toHaveText(['My investments', 'History', 'Prices', 'Setup']);
    await expect(tabs.locator('details')).toHaveCount(0);
    await tabs.getByRole('link', { name: 'Setup', exact: true }).focus();
    await expect(tabs.getByRole('link', { name: 'Setup', exact: true })).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`investment-routine-${width}-${theme}.png`), fullPage: true });
});
}
}

test('zero and unit registration remain complete without JavaScript', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 780 } });
    try {
        const page = await context.newPage();
        await signup(page, info);
        await page.goto('/investments/add/');
        await page.locator('#id_new_institution').check();
        await page.locator('#id_institution_name').fill('Native institution');
        await page.locator('#id_name').fill('Zero application');
        await page.locator('#id_valuation_mode').selectOption('MONETARY');
        await page.locator('#id_purpose').selectOption('INVESTMENT');
        await page.locator('#id_currency').selectOption('BRL');
        await page.locator('#id_opening_balance').fill('0');
        await page.locator('#id_name').press('Enter');
        await expect(page.locator('main')).toContainText('No current position.');
        await page.goto('/investments/');
        await expect(page.locator('#investment-total')).toContainText(/BRL 0[,.]00/);
        await expect(page.locator('#investment-position-list')).toContainText('Zero application');
        await page.locator('main header').getByRole('link', { name: 'Add investment', exact: true }).press('Enter');
        await selectChoice(page.locator('#id_institution'), { label: 'Native institution' });
        await page.locator('#id_name').fill('Native share');
        await page.locator('#id_valuation_mode').selectOption('UNITS');
        await page.locator('#id_currency').selectOption('BRL');
        await page.locator('#id_opening_quantity').fill('2');
        await page.locator('#id_opening_unit_price').fill('50');
        await page.locator('#id_name').press('Enter');
        await expect(page.locator('#id_opening_date')).toHaveAttribute('aria-invalid', 'true');
        await page.locator('#id_opening_date').fill('01/01/2026');
        await page.locator('#id_name').press('Enter');
        await expect(page.locator('main')).toContainText(/BRL 100[,.]00/);
        await expect(page.locator('main')).toContainText('At remaining acquisition cost');
        await page.locator('main header').getByRole('link', { name: 'Update', exact: true }).press('Enter');
        await page.getByRole('link', { name: 'Update price', exact: true }).press('Enter');
        await page.locator('#id_date').fill('05/01/2026');
        await page.locator('#id_unit_price').fill('60');
        await page.locator('#id_source').fill('Local statement');
        await page.locator('#id_source').press('Enter');
        await expect(page.locator('main')).toContainText(/BRL 120[,.]00/);
        await expect(page.locator('main')).toContainText('2 units');
    } finally { await context.close(); }
});

test('Portuguese decimal openings retain the date through partial input and native errors', async ({ browser }, info) => {
    for (const javaScriptEnabled of [true, false]) {
        const context = await browser.newContext({ locale: 'pt-BR', javaScriptEnabled,
            viewport: { width: 390, height: 780 } });
        try {
            const page = await context.newPage();
            await signup(page, info);
            await page.goto('/investments/add/');
            const advanced = page.locator('#guided-investment-form > details').filter({ has: page.locator('#id_code') });
            await expect(advanced).not.toHaveAttribute('open', '');
            await page.locator('#id_new_institution').check();
            await page.locator('#id_institution_name').fill('Instituição local');
            await page.locator('#id_name').fill('Caixa fracionário');
            await page.locator('#id_valuation_mode').selectOption('MONETARY');
            await page.locator('#id_purpose').selectOption('INVESTMENT');
            await page.locator('#id_opening_balance').fill('0,5');
            await expect(page.locator('#guided-date')).toBeVisible();
            if (javaScriptEnabled) {
                await page.locator('#id_opening_date').fill('01/01/2026');
                await page.locator('#id_opening_balance').fill('0,');
                await expect(page.locator('#id_opening_date')).toHaveValue('01/01/2026');
                await expect(page.locator('#guided-date')).toBeVisible();
                await page.locator('#id_opening_balance').fill('1.000,00');
                await page.locator('#id_name').press('Enter');
                await expect(page.locator('main')).toContainText('BRL 1.000,00');
            } else {
                await page.locator('#id_name').press('Enter');
                await expect(page.locator('#id_opening_date')).toHaveAttribute('aria-invalid', 'true');
                await expect(page.locator('#id_opening_balance')).toHaveValue('0,5');
                await page.locator('#id_opening_date').fill('01/01/2026');
                await page.locator('#id_name').press('Enter');
                await expect(page.locator('main')).toContainText('BRL 0,50');
            }
        } finally { await context.close(); }
    }
});
