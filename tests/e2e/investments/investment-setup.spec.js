// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('../helpers/forms');
const { expectContextualDestination } = require('../helpers/navigation');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `setup-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', { form: {
        csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(saved.status()).toBe(302);
}

for (const theme of ['light', 'dark']) {
    test(`investment setup guides the first registration and later editing (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.goto('/investments/');
        const primary = page.locator('main header .action-primary');
        await expect(primary).toHaveText('Add investment');
        await expect(page.getByRole('link', { name: 'New operation', exact: true })).toHaveCount(0);
        await primary.press('Enter');
        await expect(page.locator('#id_valuation_mode')).toHaveValue('');
        await expect(page.locator('#id_new_institution')).not.toBeChecked();
        await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
        await page.getByRole('navigation', { name: 'Investment sections' }).getByRole('link', { name: 'Setup', exact: true }).press('Enter');
        const setup = page.locator('#investment-setup');
        await expect(setup.getByText('Pending', { exact: true })).toHaveCount(3);
        await page.screenshot({ path: info.outputPath('setup-empty.png'), fullPage: true });
        await setup.getByRole('link', { name: 'New bank' }).press('Enter');
        await page.locator('#id_name').fill('Setup Bank');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await page.goto('/investments/settings/');
        await expect(setup.getByText('Ready', { exact: true })).toHaveCount(1);
        await setup.getByRole('link', { name: 'New product' }).press('Enter');
        await selectChoice(page.locator('#id_bank'), { label: 'Setup Bank' });
        await page.locator('#id_name').fill('Brokerage');
        await page.locator('#id_purpose').selectOption('INVESTMENT');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(setup.getByText('Ready', { exact: true })).toHaveCount(2);
        await setup.getByRole('link', { name: 'New asset' }).press('Enter');
        await page.locator('#id_name').fill('My fund');
        await page.locator('#id_code').fill('FUND');
        await page.locator('#id_valuation_mode').selectOption('MONETARY');
        await page.locator('#id_asset_class').selectOption('LIQUIDITY');
        await page.locator('#id_currency').selectOption('BRL');
        await page.getByRole('button', { name: 'Save', exact: true }).press('Enter');
        await expect(setup).toHaveCount(0);
        await expect(primary).toHaveText('Add investment');
        await expect(page.locator('#investment-products')).toContainText('Setup Bank');
        await page.locator('#investment-products').getByRole('link', { name: 'Edit', exact: true }).press('Enter');
        await expect(page.locator('#id_name')).toHaveValue('Brokerage');
        await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
        await page.locator('#investment-assets').getByRole('link', { name: 'Edit', exact: true }).press('Enter');
        await expect(page.locator('#id_name')).toHaveValue('My fund');
        await page.getByRole('link', { name: 'Cancel', exact: true }).press('Enter');
        await page.setViewportSize({ width: 390, height: 844 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: info.outputPath('setup-configured-mobile.png'), fullPage: true });
        await page.getByRole('navigation', { name: 'Investment sections' }).getByRole('link', { name: 'My investments', exact: true }).press('Enter');
        // Settings and portfolio share this action; wait for the destination
        // before activating it so the first response cannot replace the form.
        await expect(page).toHaveURL(/\/investments\/$/);
        await expect(primary).toHaveText('Add investment');
        await page.locator('#investment-operations-link').press('Enter');
        await page.getByRole('link', { name: 'New operation', exact: true }).press('Enter');
        await expectContextualDestination(page, '/investments/create/', '/investments/operations/');
        await expect(page.locator('#id_product option').last()).toContainText('Brokerage');
    });

    test(`investment tabs expose registration and keep simulations in Planning (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.goto('/investments/');
        const tabs = page.getByRole('navigation', { name: 'Investment sections' });
        await expect(tabs.getByRole('link')).toHaveText(['My investments', 'History', 'Prices', 'Setup']);
        await expect(tabs.locator('details')).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Simulate returns', exact: true })).toHaveCount(0);
        await tabs.getByRole('link', { name: 'Prices', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/prices\/$/);
        await expect(tabs.getByRole('link', { name: 'Prices', exact: true })).toHaveAttribute('aria-current', 'page');
        await tabs.getByRole('link', { name: 'Setup', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/investments\/settings\/$/);
        await expect(tabs.getByRole('link', { name: 'Setup', exact: true })).toHaveAttribute('aria-current', 'page');
        await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Plan', exact: true }).click();
        await page.getByRole('navigation', { name: 'Planning sections', exact: true }).getByRole('link', { name: 'Tools', exact: true }).click();
        await page.getByRole('link').filter({ has: page.getByRole('heading', { name: 'Yield simulation', exact: true }) }).click();
        await expect(page).toHaveURL(/\/sandbox\/simulation\/$/);
    });
}

test('investment setup tabs support Portuguese, touch and no JavaScript', async ({ page, browser }, info) => {
    await signup(page, info);
    await page.goto('/investments/');
    await page.context().addCookies([{ name: 'django_language', value: 'pt-br', url: page.url() }]);
    const storageState = await page.context().storageState();
    for (const javaScriptEnabled of [true, false]) {
        const context = await browser.newContext({ storageState, javaScriptEnabled, hasTouch: true,
            isMobile: true, viewport: { width: 390, height: 740 } });
        try {
            const mobile = await context.newPage();
            await mobile.goto('/investments/');
            await expect(mobile.locator('main header .action-primary')).toHaveText('Adicionar aplicação');
            const tabs = mobile.getByRole('navigation', { name: 'Seções de investimentos' });
            await expect(tabs.getByRole('link')).toHaveText(['Minhas aplicações', 'Histórico', 'Preços', 'Cadastros']);
            const setupLink = tabs.getByRole('link', { name: 'Cadastros', exact: true });
            await setupLink.scrollIntoViewIfNeeded();
            await setupLink.tap();
            await expect(mobile.locator('#investment-setup')).toContainText('1. Banco');
            await mobile.screenshot({ path: info.outputPath(`setup-pt-${javaScriptEnabled ? 'touch' : 'native'}.png`), fullPage: true });
            await mobile.locator('#investment-setup').getByRole('link', { name: 'Novo banco', exact: true }).click();
            await expect(mobile.locator('#id_name')).toBeVisible();
        } finally { await context.close(); }
    }
});
