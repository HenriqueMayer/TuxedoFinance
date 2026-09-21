// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path === '/i18n/setlang/' ? '/transactions/' : path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields }, headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(result.status()).toBe(302);
}

async function prepare(page, testInfo, order) {
    const username = `dates-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-Dates-2026!', password2: 'Tuxedo-Dates-2026!',
    });
    await post(page, '/accounts/settings/', { base_currency: 'BRL', date_format: order });
}

for (const [order, theme, language] of [['DMY', 'light', 'en'], ['MDY', 'dark', 'pt-br']]) {
    test(`preferred dates preserve keyboard edits and invalid responses ${order} ${theme}`, async ({ page }, testInfo) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await prepare(page, testInfo, order);
        await post(page, '/i18n/setlang/', { language, next: '/transactions/' });
        const valid = order === 'DMY' ? '14/08/2026' : '08/14/2026';
        const invalid = order === 'DMY' ? '31/02/2026' : '02/31/2026';
        for (const [url, id] of [
            ['/transactions/create/', '#id_date'],
            ['/banking/transfers/create/', '#id_date'],
            ['/banking/loyalty-entries/create/', '#id_date'],
            ['/banking/rewards/redeem/', '#id_date'],
            ['/banking/exchange-rates/create/', '#id_effective_date'],
            ['/investments/create/', '#id_date'],
        ]) {
            await page.goto(url);
            const input = page.locator(id);
            await expect(input).toHaveAttribute('placeholder', order === 'DMY' ? 'DD/MM/YYYY' : 'MM/DD/YYYY');
            await input.focus();
            await input.press('ControlOrMeta+A');
            await input.pressSequentially(valid);
            await input.press('Home');
            await input.press('ArrowRight');
            await input.press('Delete');
            await input.pressSequentially(valid[1]);
            expect(await input.evaluate(element => element.selectionStart)).toBe(2);
            await expect(input).toHaveValue(valid);
            await input.press('Tab');
            const calendar = input.locator('xpath=ancestor::*[@data-preferred-date-field]').locator('[data-open-date-picker]');
            await expect(calendar).toBeFocused();
            await calendar.press('Enter');
            await page.keyboard.press('Escape');
            await input.fill(invalid);
            await page.locator('main form[method="post"] button[type="submit"]').first().click();
            await expect(page.locator(id)).toHaveValue(invalid);
            await expect(page.locator(id)).toHaveAttribute('aria-invalid', 'true');
        }
        expect(errors).toEqual([]);
    });
}

test('date filter keeps ISO URLs through HTMX navigation, history and changed preference', async ({ page }, testInfo) => {
    await prepare(page, testInfo, 'DMY');
    await page.goto('/transactions/?date=2026-04-03');
    await expect(page.locator('#filter-date')).toHaveValue('03/04/2026');
    await page.locator('#filter-date').fill('14/08/2026');
    await page.locator('#transaction-apply-filters').click();
    await expect(page).toHaveURL(/date=2026-08-14/);
    await expect(page.locator('#filter-date')).toHaveValue('14/08/2026');
    await page.locator('#filter-date').press('Tab');
    await expect(page.locator('[data-open-date-picker]')).toBeFocused();
    await page.goBack();
    await expect(page.locator('#filter-date')).toHaveValue('03/04/2026');
    await post(page, '/accounts/settings/', { base_currency: 'BRL', date_format: 'MDY' });
    await page.reload();
    await expect(page.locator('#filter-date')).toHaveValue('04/03/2026');
    await expect(page).toHaveURL(/date=2026-04-03/);
});

test('preferred dates submit and recover errors without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await prepare(page, testInfo, 'MDY');
    await page.goto('/banking/exchange-rates/create/');
    await page.locator('#id_from_currency').selectOption('USD');
    await page.locator('#id_to_currency').selectOption('BRL');
    await page.locator('#id_rate').fill('5.20');
    await page.locator('#id_effective_date').fill('02/31/2026');
    await page.locator('main form button[type="submit"]').click();
    await expect(page.locator('#id_effective_date')).toHaveValue('02/31/2026');
    await expect(page.locator('#id_effective_date')).toHaveAttribute('aria-invalid', 'true');
    await page.locator('#id_effective_date').fill('08/14/2026');
    await page.locator('main form button[type="submit"]').click();
    await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
    await expect(page.locator('main')).toContainText('08/14/2026');
    await context.close();
});
