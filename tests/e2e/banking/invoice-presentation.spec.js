// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const source = await page.request.get(path);
    const csrf = (await source.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: source.url()}, maxRedirects: 0});
    expect(response.status(), (await response.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
}

async function seed(page, info) {
    const username = `statement-layout-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Statement-E2E-2026!', password2: 'Statement-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Statement institution', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Everyday account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    const cardName = 'Personal purple card ' + 'A'.repeat(65);
    await post(page, '/banking/credit-cards/create/', {account, name: cardName, card_type: 'PHYSICAL',
        closing_day: '31', due_day: '28', manual_settlement_from: new Date().toISOString().slice(0, 10), color: '#72419C'});
    await post(page, '/categories/create/', {name: 'Statement expense', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Statement expense$/}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Statement source ' + 'B'.repeat(80), amount: '84.90',
        date: new Date().toISOString().slice(0, 10), transaction_type: 'EXPENSE', category,
        payment_channel: 'CREDIT_CARD', credit_card: card, installments: '1'});
    return {card, cardName};
}

async function assertFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) for (const width of [320, 1440]) {
    test(`statement identity, amount and payment recovery remain readable (${theme}, ${width})`, async ({page, baseURL}, info) => {
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {card, cardName} = await seed(page, info);
        const portuguese = width === 320;
        if (portuguese) await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: baseURL}]);
        await page.goto(`/banking/credit-cards/${card}/invoices/`);
        await expect(page.locator('.invoice-identity')).toContainText(cardName);
        await expect(page.locator('.invoice-identity .card-miniature')).toBeVisible();
        await expect(page.locator('.invoice-history-amount')).toContainText(/84[,.]90/);
        await assertFits(page);
        const view = page.getByRole('link', {name: portuguese ? 'Ver fatura' : 'View invoice', exact: true}).first();
        expect((await view.boundingBox()).height).toBeGreaterThanOrEqual(44);
        await page.screenshot({path: info.outputPath(`invoice-history-${theme}-${width}.png`), fullPage: true});
        await view.press('Enter');
        await expect(page.locator('#invoice-summary .invoice-summary-total')).toContainText(/84[,.]90/);
        await expect(page.locator('.invoice-identity .card-miniature')).toBeVisible();
        await assertFits(page);
        await page.screenshot({path: info.outputPath(`invoice-summary-${theme}-${width}.png`)});
        await page.locator('#id_amount').fill('-1');
        await page.getByRole('button', {name: portuguese ? 'Confirmar pagamento' : 'Confirm payment', exact: true}).press('Enter');
        await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_amount')).toHaveValue('-1');
        await expect(page.locator('#invoice-summary .invoice-summary-total')).toContainText(/84[,.]90/);
        await assertFits(page);
        await page.locator('#id_amount').scrollIntoViewIfNeeded();
        await page.screenshot({path: info.outputPath(`invoice-payment-error-${theme}-${width}.png`)});
    });
}

test.describe('statement presentation without JavaScript', () => {
    test.use({javaScriptEnabled: false});
    test('the same statement and native payment errors remain available at 320px', async ({page}, info) => {
        await page.setViewportSize({width: 320, height: 900});
        const {card} = await seed(page, info);
        await page.goto(`/banking/credit-cards/${card}/invoices/`);
        await page.getByRole('link', {name: 'View invoice', exact: true}).first().press('Enter');
        await expect(page.locator('#id_account')).toBeVisible();
        await page.locator('#id_amount').fill('-1');
        await page.getByRole('button', {name: 'Confirm payment', exact: true}).press('Enter');
        await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#invoice-summary')).toContainText(/84[,.]90/);
        await assertFits(page);
        await page.screenshot({path: info.outputPath('invoice-native-320.png'), fullPage: true});
    });
});
