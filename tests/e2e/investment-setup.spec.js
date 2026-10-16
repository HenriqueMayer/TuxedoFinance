// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');
const { expectContextualDestination } = require('./helpers/navigation');

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

async function tabTo(page, control) {
    for (let i = 0; i < 70; i++) {
        if (await control.evaluate(el => document.activeElement === el)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control not reachable by keyboard');
}

async function openMore(page) {
    const menu = page.locator('[data-investment-more]');
    if (await menu.getAttribute('open') === null) await menu.locator(':scope > summary').press('Enter');
    return menu;
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
        await openMore(page);
        await page.getByRole('link', { name: 'Full configuration', exact: true }).press('Enter');
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

    test(`investment simulation notice blocks navigation and points to Planning (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.goto('/investments/');
        await openMore(page);
        const trigger = page.getByRole('button', { name: 'Simulate returns', exact: true });
        const tooltip = page.locator('#investment-simulation-notice');
        await expect(trigger).toHaveAttribute('aria-disabled', 'true');
        await expect(trigger.locator('svg')).toHaveCount(0);
        await expect(trigger).toHaveCSS('cursor', 'not-allowed');
        await trigger.hover();
        await expect(tooltip).toBeVisible();
        await expect(tooltip).toContainText('Plan → Yield simulation');
        const box = await trigger.boundingBox();
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        await expect(page).toHaveURL(/\/investments\/$/);
        await page.mouse.move(2, 2);
        await expect(tooltip).toBeHidden();
        await page.keyboard.press('Tab');
        await openMore(page);
        await page.locator('[data-investment-more] > summary').focus();
        await tabTo(page, trigger);
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(tooltip).toBeHidden();
        await openMore(page);
        await page.locator('[data-investment-more] > summary').focus();
        await tabTo(page, trigger);
        await page.keyboard.press('Enter');
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Space');
        await expect(page).toHaveURL(/\/investments\/$/);
        await page.setViewportSize({ width: 390, height: 740 });
        await trigger.scrollIntoViewIfNeeded();
        const bounds = await tooltip.boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(12);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(378);
        expect(bounds.y).toBeGreaterThanOrEqual(12);
        expect(bounds.y + bounds.height).toBeLessThanOrEqual(728);
        await page.screenshot({ path: info.outputPath('simulation-notice-mobile.png') });
        await page.keyboard.press('Tab');
        await expect(tooltip).toBeHidden();
        await openMore(page);
        await page.getByRole('link', { name: 'Full configuration', exact: true }).click();
        // Both screens contain this trigger. Wait for the HTMX destination so
        // its swap cannot close a notice opened on the departing screen.
        await expect(page).toHaveURL(/\/investments\/settings\/$/);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText('Investment Settings');
        await page.mouse.move(2, 2);
        await openMore(page);
        await trigger.hover();
        await expect(tooltip).toBeVisible();
        // Section tabs precede the heading now; their open menu intentionally
        // overlays it. Dismiss from the unoccupied main gutter instead.
        await page.locator('main').click({ position: { x: 2, y: 2 } });
        await expect(tooltip).toBeHidden();
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Plan', exact: true }).click();
        await expect(page).toHaveURL(/\/planning\/$/);
        await page.getByRole('navigation', { name: 'Planning sections', exact: true }).getByRole('link', { name: 'Tools', exact: true }).click();
        await page.getByRole('link').filter({ has: page.getByRole('heading', { name: 'Yield simulation', exact: true }) }).click();
        await expect(page).toHaveURL(/\/sandbox\/simulation\/$/);
    });
}

test('investment setup and simulation notice support Portuguese, touch and no JavaScript', async ({ page, browser }, info) => {
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
            await openMore(mobile);
            const trigger = mobile.getByRole('button', { name: 'Simular rendimentos', exact: true });
            await trigger.scrollIntoViewIfNeeded();
            // The native navigation header is taller; keep the target below it.
            if (!javaScriptEnabled) await mobile.evaluate(() => window.scrollTo(0, 0));
            const rect = await trigger.boundingBox();
            await mobile.touchscreen.tap(rect.x + rect.width / 2, rect.y + rect.height / 2);
            const hint = mobile.getByRole('tooltip').filter({ hasText: 'Para simular rendimentos de investimentos' });
            await expect(hint).toBeVisible();
            await expect(hint).toContainText('Planejar → Simulação de rendimentos');
            await expect(mobile).toHaveURL(/\/investments\/$/);
            await mobile.locator('main').tap({ position: { x: 2, y: 2 } });
            if (javaScriptEnabled) await expect(hint).toBeHidden();
            await openMore(mobile);
            await mobile.getByRole('link', { name: 'Cadastros completos', exact: true }).press('Enter');
            await expect(mobile.locator('#investment-setup')).toContainText('1. Banco');
            await mobile.screenshot({ path: info.outputPath(`setup-pt-${javaScriptEnabled ? 'touch' : 'native'}.png`), fullPage: true });
            await mobile.locator('#investment-setup').getByRole('link', { name: 'Novo banco', exact: true }).click();
            await expect(mobile.locator('#id_name')).toBeVisible();
        } finally { await context.close(); }
    }
});
