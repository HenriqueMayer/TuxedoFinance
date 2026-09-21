// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    const errors = (await result.text()).match(/<[^>]+id="[^"]+-error-[^"]+"[^>]*>.*?<\/[^>]+>/g);
    expect(result.status(), `${path}: ${errors || 'unexpected response'}`).toBe(302);
}

async function seed(page, testInfo) {
    const username = `context-help-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-Help-2026!', password2: 'Tuxedo-Help-2026!',
    });
    await post(page, '/banking/create/', { name: 'Help bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Savings', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', {
        name: 'Saved balance', code: 'SAVE', asset_class: 'LIQUIDITY', currency: 'BRL',
        valuation_mode: 'MONETARY', opening_balance: '1000', opening_product: product,
        opening_quantity: '0', opening_unit_price: '0',
    });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    await post(page, '/investments/create/', {
        product, asset, kind: 'YIELD', yield_input_mode: 'YIELD_AMOUNT', amount: '10', fees: '0', date: '2026-01-15',
    });
}

async function checkHelp(page, label, id) {
    const trigger = page.getByRole('button', { name: `Explain ${label}`, exact: true });
    const panel = page.locator(`#${id}`);
    await expect(trigger).toBeVisible();
    await trigger.hover();
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(320);
    expect(box.x).toBeGreaterThanOrEqual(12);
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width - 12);
    await panel.hover();
    await expect(panel).toBeVisible();
    await page.mouse.move(4, 80);
    await expect(panel).toBeHidden();
    await trigger.hover();
    await page.mouse.click(4, 80);
    await expect(panel).toBeHidden();
    await trigger.click();
    await page.mouse.move(4, 80);
    await expect(panel).toBeHidden();
    await trigger.scrollIntoViewIfNeeded();
    await trigger.focus();
    await page.keyboard.press('Enter');
    await expect(panel).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(trigger).toBeFocused();
    await expect(panel).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(panel).toBeHidden();
}

for (const dark of [false, true]) {
    test(`contextual dashboard and investment help stays readable and transient (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), dark ? 'dark' : 'light');
        await seed(page, testInfo);
        await page.goto('/dashboard/');
        await checkHelp(page, 'Month performance', 'dashboard-performance-help');
        await checkHelp(page, 'Six-month outlook', 'dashboard-outlook-help');
        await expect(page.locator('[aria-labelledby="category-heading"]')).toHaveClass(/surface-panel/);
        await expect(page.locator('[aria-labelledby="performance-heading"] .metric-panel')).toHaveCount(4);

        await page.goto('/dashboard/reports/');
        await checkHelp(page, 'Balance evolution', 'report-balance-help');
        await page.locator('#report-balance-next').click();
        await expect(page).toHaveURL(/charts_offset=1/);
        await checkHelp(page, 'Balance evolution', 'report-balance-help');
        await expect(page.getByRole('button', { name: 'Explain Balance evolution', exact: true })).toHaveCount(1);
        await checkHelp(page, 'Income and expenses by account or card', 'report-instruments-help');
        await expect(page.locator('#report-instruments-help')).toContainText('Hold Ctrl over a bar');

        await page.goto('/investments/');
        await checkHelp(page, 'Portfolio', 'investments-portfolio-help');
        await checkHelp(page, 'Investment evolution', 'investment-evolution-help');
        const evolution = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Investment evolution', exact: true }) });
        await evolution.getByRole('link', { name: 'Next window', exact: true }).click();
        await expect(page).toHaveURL(/total_offset=1/);
        await checkHelp(page, 'Monthly flow', 'investment-flow-help');
        await expect(page.getByRole('button', { name: 'Explain Monthly flow', exact: true })).toHaveCount(1);
        await page.setViewportSize({ width: 390, height: 740 });
        const positions = page.getByRole('region', { name: 'Positions', exact: true });
        await expect(positions.getByRole('table')).toBeHidden();
        const mobilePosition = positions.getByRole('listitem');
        await expect(mobilePosition).toBeVisible();
        for (const label of ['Saved balance', 'Deposits', 'Yields', 'Withdrawals']) {
            await expect(mobilePosition.getByText(label, { exact: true })).toBeVisible();
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
        await page.getByRole('button', { name: 'Explain Investment evolution', exact: true }).press('Enter');
        const mobileBox = await page.locator('#investment-evolution-help').boundingBox();
        expect(mobileBox.x).toBeGreaterThanOrEqual(12);
        expect(mobileBox.x + mobileBox.width).toBeLessThanOrEqual(378);
        expect(mobileBox.y).toBeGreaterThanOrEqual(12);
        expect(mobileBox.y + mobileBox.height).toBeLessThanOrEqual(728);
        await page.screenshot({ path: testInfo.outputPath(`context-help-${dark ? 'dark' : 'light'}.png`) });
        expect(errors).toEqual([]);
    });
}

test('contextual help remains available without JavaScript and on touch', async ({ page, browser }, testInfo) => {
    await seed(page, testInfo);
    const storageState = await page.context().storageState();
    const native = await browser.newContext({ storageState, javaScriptEnabled: false });
    try {
        const offline = await native.newPage();
        for (const [path, label, text] of [
            ['/dashboard/', 'Month performance', 'available cash changes'],
            ['/dashboard/reports/', 'Balance evolution', 'close of each month'],
            ['/dashboard/reports/', 'Income and expenses by account or card', 'Hold Ctrl over a bar'],
            ['/investments/', 'Portfolio', 'not a live market valuation'],
            ['/investments/settings/', 'Investment Settings', 'Banks, accounts, loyalty programs'],
        ]) {
            await offline.goto(path);
            const summary = offline.locator(`.help-fallback summary[aria-label="Explain ${label}"]`);
            await summary.press('Enter');
            await expect(summary.locator('..')).toHaveAttribute('open', '');
            await expect(summary.locator('..')).toContainText(text);
        }
    } finally {
        await native.close();
    }
    const touch = await browser.newContext({ storageState, hasTouch: true, isMobile: true, viewport: { width: 390, height: 740 } });
    try {
        const mobile = await touch.newPage();
        await mobile.goto('/investments/');
        const trigger = mobile.getByRole('button', { name: 'Explain Portfolio', exact: true });
        await trigger.tap();
        await expect(mobile.locator('#investments-portfolio-help')).toBeVisible();
        await trigger.tap();
        await expect(mobile.locator('#investments-portfolio-help')).toBeHidden();
        await trigger.tap();
        await mobile.getByRole('heading', { level: 1 }).tap();
        await expect(mobile.locator('#investments-portfolio-help')).toBeHidden();
    } finally {
        await touch.close();
    }
});
