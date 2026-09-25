// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(result.status(), path).toBe(302);
}

async function seed(page, info) {
    const username = `month-filter-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    await post(page, '/banking/create/', { name: 'Filter bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {
        bank, name: 'Daily', currency: 'BRL', opening_balance: '1000', pix_enabled: 'on',
    });
    await post(page, '/categories/create/', { name: 'Monthly groceries', transaction_type: 'EXPENSE' });
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({ hasText: 'Monthly groceries' }).getAttribute('value');
    const now = new Date();
    const months = [0, -1, 1].map(offset => new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offset, 1)).toISOString().slice(0, 7));
    for (const [index, month] of months.entries()) {
        await post(page, '/transactions/create/', {
            title: `Groceries ${month}`, category, amount: ['20', '10', '40'][index],
            transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account,
            date: `${month}-01`, installments: '1',
        });
    }
    return months;
}

async function chooseNextMonth(page, id) {
    const select = page.locator(`#${id}`);
    await select.focus();
    const top = await page.evaluate(() => window.scrollY);
    expect(top).toBeGreaterThan(0);
    await select.press('Space');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    return top;
}

for (const theme of ['light', 'dark']) {
    test(`instrument month arrows and installment selection stay independent (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const [current, previous, future] = await seed(page, info);
        await page.goto(`/dashboard/reports/?charts_offset=1&installment_month=${current}`);
        await expect(page.locator('#instrument-month')).toHaveCount(0);
        await expect(page.locator('#reports-charts').getByRole('button', { name: 'Filter', exact: true })).toHaveCount(0);
        const installmentTop = await chooseNextMonth(page, 'installment-month');
        await expect(page).toHaveURL(new RegExp(`installment_month=${previous}`));
        await expect(page.locator('#installment-month')).toBeFocused();
        await expect(page.locator('#installments [data-donut-total]')).toContainText(/10[,.]00/);
        expect(Math.abs(await page.evaluate(() => window.scrollY) - installmentTop)).toBeLessThan(4);

        const instrument = page.locator('#instrument-activity');
        const bar = instrument.locator('[data-chart-layer="instrument-interactions"] [data-point]').first();
        for (const [id, month, amount] of [
            ['instrument-previous', previous, '10'],
            ['instrument-next', current, '20'],
            ['instrument-next', future, '40'],
        ]) {
            const arrow = page.locator(`#${id}`);
            await arrow.focus();
            const top = await page.evaluate(() => window.scrollY);
            expect(top).toBeGreaterThan(0);
            await arrow.press('Enter');
            await expect(page).toHaveURL(new RegExp(`instrument_month=${month}`));
            await expect(arrow).toBeFocused();
            expect(Math.abs(await page.evaluate(() => window.scrollY) - top)).toBeLessThan(4);
            await expect(page).toHaveURL(/charts_offset=1/);
            await expect(page.locator('#installment-month')).toHaveValue(previous);
            await bar.press('Enter');
            await expect(instrument.locator('[data-selection-values]')).toContainText(new RegExp(`${amount}[,.]00`));
            await page.keyboard.down('Control');
            await expect(page.locator('.chart-composition:visible')).toContainText('Monthly groceries');
            await expect(page.locator('.chart-composition:visible')).toContainText(new RegExp(`${amount}[,.]00`));
            await page.keyboard.up('Control');
        }
        await page.locator('#instrument-all').press('Enter');
        await expect(page).toHaveURL(/instrument_month=ALL/);
        await expect(page.locator('#instrument-all')).toBeFocused();
        await expect(page.locator('#instrument-window')).toHaveText('All time');
        await bar.press('Enter');
        await expect(instrument.locator('[data-selection-values]')).toContainText(/30[,.]00/);
        await page.locator('#instrument-current').press('Enter');
        await expect(page).toHaveURL(new RegExp(`instrument_month=${current}`));
        await expect(page.locator('#instrument-current')).toBeFocused();
        await instrument.screenshot({ path: info.outputPath(`month-arrows-${theme}.png`) });

        await page.goto('/dashboard/reports/?instrument_month=2026-13&installment_month=invalid');
        await expect(page.locator('#instrument-current')).toHaveText('Current month');
        await expect(page.locator('#installment-month')).toHaveValue('ALL');
        await page.locator('#instrument-next').click();
        await expect(page).toHaveURL(new RegExp(`instrument_month=${future}`));
        await page.setViewportSize({ width: 390, height: 844 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await instrument.screenshot({ path: info.outputPath(`month-arrows-mobile-${theme}.png`) });
    });
}

test('instrument month arrows and installment submission work without JavaScript', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        const [current, previous, future] = await seed(page, info);
        await page.goto(`/dashboard/reports/?charts_offset=1&installment_month=${current}`);
        await page.locator('#installment-month').selectOption(previous);
        await page.locator('#installments').getByRole('button', { name: 'Filter', exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`installment_month=${previous}`));
        for (const [id, month] of [['instrument-previous', previous], ['instrument-next', current], ['instrument-next', future], ['instrument-all', 'ALL'], ['instrument-current', current]]) {
            await page.locator(`#${id}`).press('Enter');
            await expect(page).toHaveURL(new RegExp(`instrument_month=${month}`));
            await expect(page).toHaveURL(/charts_offset=1/);
            await expect(page.locator('#installment-month')).toHaveValue(previous);
        }
    } finally {
        await context.close();
    }
});
