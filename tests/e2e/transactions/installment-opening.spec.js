// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const source = await page.request.get(path);
    const csrf = (await source.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: source.url()}, maxRedirects: 0});
    expect(result.status(), (await result.text()).match(/data-field-error[^>]*>[^<]*/g)?.join(' ') || path).toBe(302);
}

async function seed(page, info) {
    const username = `plan-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Opening-Installments-2026!', password2: 'Opening-Installments-2026!'});
    await post(page, '/banking/create/', {name: 'Synthetic opening bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Daily', currency: 'BRL', opening_balance: '0'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Synthetic card', card_type: 'PHYSICAL',
        closing_day: '24', due_day: '1', color: '#111111'});
    await post(page, '/categories/create/', {name: 'Opening purchase category', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: 'Opening purchase category'}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Existing installment purchase', amount: '1200',
        transaction_type: 'EXPENSE', payment_channel: 'CREDIT_CARD', credit_card: card, category,
        installments: '12', installment_start: '9', date: '2026-02-18'});
    await page.goto('/transactions/');
    await page.getByRole('link', {name: 'Edit', exact: true}).first().press('Enter');
    await expect(page).toHaveURL(/\/transactions\/\d+\/edit\//);
    await expect(page.locator('#id_installment_start')).toHaveValue('9');
    return {card};
}

async function exercise(page, info, {native = false, width, theme, language = 'en', baseURL}) {
    await seed(page, info);
    const save = language === 'pt-br' ? 'Salvar' : 'Save';
    const edit = language === 'pt-br' ? 'Editar' : 'Edit';
    if (language !== 'en') {
        await page.context().addCookies([{name: 'django_language', value: language, url: baseURL}]);
        await page.reload();
    }
    const start = page.locator('#id_installment_start');
    await expect(start).toBeVisible();
    await expect(start).toHaveValue('9');
    await expect(page.locator('form[method="post"]').filter({has: start})).toHaveAttribute('novalidate', '');
    await start.fill('13');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(start).toBeVisible();
    await expect(start).toHaveValue('13');
    await expect(start).toHaveAttribute('aria-invalid', 'true');
    await start.fill('9');
    await start.press('Tab');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.getByText(language === 'pt-br' ? 'Controle das parcelas 9–12' : 'Tracking installments 9–12', {exact: true})).toBeVisible();
    await page.getByRole('link', {name: edit, exact: true}).first().press('Enter');
    await expect(start).toHaveValue('9');
    if (!native) {
        await page.locator('#id_installments').fill('1');
        await expect(start).not.toBeVisible();
        await expect(start).toHaveValue('1');
        await page.locator('#id_installments').fill('12');
        const disclosure = start.locator('xpath=ancestor::details');
        if (!await disclosure.evaluate(element => element.open)) await disclosure.locator('summary').press('Enter');
        await start.fill('9');
    }
    await start.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath(`opening-plan-${width}-${theme}-${native}.png`)});
    await page.getByRole('button', {name: save, exact: true}).scrollIntoViewIfNeeded();
    await expect(page.getByRole('button', {name: save, exact: true})).toBeInViewport();
}

for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
    test(`opening installments retain numbering and keyboard recovery (${theme}, ${width})`, async ({page}, info) => {
        test.setTimeout(60000);
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await exercise(page, info, {width, theme});
    });
}

test.describe('opening installments without JavaScript', () => {
    test.use({javaScriptEnabled: false});
    test('native invalid recovery retains the first unpaid installment', async ({page}, info) => {
        test.setTimeout(60000);
        await page.setViewportSize({width: 390, height: 900});
        await exercise(page, info, {native: true, width: 390, theme: 'light'});
    });
});

for (const theme of ['light', 'dark']) {
    test(`Portuguese opening installments preserve mobile recovery (${theme})`, async ({page, baseURL}, info) => {
        test.setTimeout(60000);
        await page.setViewportSize({width: 390, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await exercise(page, info, {width: 390, theme, language: 'pt-br', baseURL});
    });
}
