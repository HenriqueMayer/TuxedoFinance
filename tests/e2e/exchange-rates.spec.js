// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, { form: { csrfmiddlewaretoken: token, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0 });
    expect(result.status(), await result.text()).toBe(302);
}

async function seed(page, testInfo) {
    const username = `rates-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
    await post(page, '/banking/exchange-rates/create/', { from_currency: 'USD', to_currency: 'BRL',
        rate: '5.19', effective_date: '2026-09-24', notes: 'Original rate' });
    await page.goto('/banking/exchange-rates/');
}

async function tabTo(page, locator) {
    for (let i = 0; i < 70; i++) {
        if (await locator.evaluate(element => element === document.activeElement)) return;
        await page.keyboard.press('Tab');
    }
    throw new Error('Control is not reachable with Tab');
}

for (const dark of [false, true]) {
    test(`exchange rates keyboard edit, invalid recovery and confirmed delete (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        await seed(page, testInfo);
        await page.evaluate(value => {
            document.documentElement.classList.toggle('dark', value);
            localStorage.setItem('theme', value ? 'dark' : 'light');
        }, dark);
        const edit = page.locator('main').getByRole('link', { name: 'Edit', exact: true });
        await tabTo(page, edit);
        await expect(edit).toBeFocused();
        expect(await edit.evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe('none');
        await page.screenshot({ path: testInfo.outputPath('rate-actions-desktop.png'), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await expect(edit).toBeInViewport();
        await expect(page.locator('main').getByRole('link', { name: 'Delete', exact: true })).toBeInViewport();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath('rate-actions-mobile.png'), fullPage: true });
        await page.keyboard.press('Enter');
        await expect(page.getByRole('heading', { name: 'Edit exchange rate' })).toBeVisible();
        await expect(page.locator('#id_from_currency')).toHaveValue('USD');
        await expect(page.locator('#id_to_currency')).toHaveValue('BRL');
        await expect(page.locator('#id_effective_date')).toHaveValue('24/09/2026');
        await expect(page.locator('#id_notes')).toHaveValue('Original rate');
        await tabTo(page, page.locator('#id_from_currency'));
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_to_currency')).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(page.locator('#id_from_currency')).toBeFocused();
        await page.keyboard.press('Tab');
        await page.keyboard.press('u');
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_to_currency')).toHaveValue('USD');
        await tabTo(page, page.getByRole('button', { name: 'Save', exact: true }));
        await page.keyboard.press('Enter');
        await expect(page.getByRole('alert')).toContainText('Currencies must differ.');
        await expect(page.locator('#id_to_currency')).toHaveValue('USD');
        await tabTo(page, page.locator('#id_to_currency'));
        await page.keyboard.press('Home');
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_to_currency')).toHaveValue('BRL');
        await tabTo(page, page.locator('#id_rate'));
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('0');
        await tabTo(page, page.getByRole('button', { name: 'Save', exact: true }));
        await page.keyboard.press('Space');
        await expect(page.locator('#id_rate')).toHaveValue('0');
        await expect(page.getByRole('alert')).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath('rate-invalid-edit.png'), fullPage: true });
        await tabTo(page, page.locator('#id_rate'));
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('5.25');
        await tabTo(page, page.locator('#id_notes'));
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('Corrected rate');
        await tabTo(page, page.getByRole('button', { name: 'Save', exact: true }));
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
        await expect(page.locator('main li')).toContainText('1 USD = 5,25000000 BRL');
        await expect(page.locator('main li')).toContainText('Corrected rate');
        const remove = page.locator('main').getByRole('link', { name: 'Delete', exact: true });
        await tabTo(page, remove);
        await page.keyboard.press('Enter');
        await expect(page.locator('main')).toContainText('Conversions already saved');
        await tabTo(page, page.getByRole('link', { name: 'Cancel', exact: true }));
        await page.keyboard.press('Enter');
        await expect(page.locator('main li')).toContainText('Corrected rate');
        await tabTo(page, remove);
        await page.keyboard.press('Enter');
        await tabTo(page, page.getByRole('button', { name: 'Delete', exact: true }));
        await page.keyboard.press('Space');
        await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
        await expect(page.getByText('No exchange rates yet', { exact: true })).toBeVisible();
    });
}

test('exchange rates work without JavaScript and translate to Portuguese', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        await seed(page, testInfo);
        await page.locator('main').getByRole('link', { name: 'Edit', exact: true }).click();
        await page.locator('#id_rate').fill('6.12');
        await page.locator('#id_effective_date').fill('23/09/2026');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        await expect(page.locator('main li')).toContainText('1 USD = 6,12000000 BRL');
        await context.addCookies([{ name: 'django_language', value: 'pt-br', url: page.url() }]);
        await page.reload();
        await page.locator('main').getByRole('link', { name: 'Editar', exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Editar taxa de câmbio' })).toBeVisible();
        await expect(page.locator('#id_effective_date')).toHaveValue('23/09/2026');
        await page.getByRole('link', { name: 'Cancelar', exact: true }).click();
        await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
        await page.locator('main').getByRole('link', { name: 'Excluir', exact: true }).click();
        await expect(page.locator('main')).toContainText('serão preservadas.');
        await page.getByRole('button', { name: 'Excluir', exact: true }).click();
        await expect(page.locator('main li')).toHaveCount(0);
    } finally {
        await context.close();
    }
});
