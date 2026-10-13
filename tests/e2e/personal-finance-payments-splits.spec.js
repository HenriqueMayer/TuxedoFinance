// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { selectChoice } = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, { form: {csrfmiddlewaretoken: csrf, ...values}, headers: {Referer: response.url()}, maxRedirects: 0 });
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
    return saved.headers().location;
}

async function prepare(page, testInfo) {
    const username = `personal-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`, password1: 'Personal-E2E-2026!', password2: 'Personal-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Personal bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Cash', currency: 'BRL', opening_balance: '1000', opening_date: '2025-01-01', pix_enabled: 'on'});
    await post(page, '/categories/create/', {name: 'Food', transaction_type: 'EXPENSE'});
    await post(page, '/categories/create/', {name: 'Transport', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Food$/}).getAttribute('value');
    await post(page, '/transactions/create/', {title:'Shared purchase', amount:'100', transaction_type:'EXPENSE', category, payment_channel:'ACCOUNT', bank_account:account, date:'2026-10-01', installments:'1'});
    await page.goto('/transactions/');
    const split = await page.getByRole('link', {name:'Split', exact:true}).getAttribute('href');
    return {account, split};
}

for (const theme of ['light', 'dark']) {
test(`split categories and confirmed invoice payment preserve keyboard errors (${theme})`, async ({page}, testInfo) => {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const externalRequests = [];
    page.on('request', request => { if (!request.url().startsWith(testInfo.project.use.baseURL)) externalRequests.push(request.url()); });
    const {account, split} = await prepare(page, testInfo);
    await page.goto(split);
    await selectChoice(page.locator('#id_splits-0-category'), {label:'Food'});
    await page.locator('#id_splits-0-amount').fill('40');
    await selectChoice(page.locator('#id_splits-1-category'), {label:'Transport'});
    await page.locator('#id_splits-1-amount').fill('59');
    await page.getByRole('button', {name:'Save split', exact:true}).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('alert').filter({hasText:'Category amounts must add up'})).toBeVisible();
    await expect(page.locator('#id_splits-0-category-search')).toHaveValue('Food');
    await page.locator('#id_splits-1-amount').fill('60');
    await page.getByRole('button', {name:'Save split', exact:true}).click();
    await expect(page).toHaveURL(/transactions\/\d+\/edit\/$/);

    const today = new Date().toISOString().slice(0,10);
    await post(page, '/banking/credit-cards/create/', {account, name:'Confirmed card', card_type:'PHYSICAL', closing_day:'31', due_day:'31', manual_settlement_from:today});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText:/^Food$/}).getAttribute('value');
    await post(page, '/transactions/create/', {title:'Invoice purchase', amount:'100', category, transaction_type:'EXPENSE', payment_channel:'CREDIT_CARD', credit_card:card, date:today, installments:'1'});
    await page.goto('/banking/invoices/');
    await page.getByRole('link', {name:/Confirmed card/}).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', {name:'Confirm a payment'})).toBeVisible();
    await selectChoice(page.locator('#id_account'), account);
    await page.locator('#id_amount').fill('101');
    await page.locator('#id_date').fill(today);
    await page.getByRole('button', {name:'Confirm payment', exact:true}).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText('Payments cannot exceed the current invoice amount.', {exact:true})).toBeVisible();
    await expect(page.locator('#id_account-search')).toHaveValue(/Cash/);
    await page.locator('#id_amount').fill('40');
    await page.getByRole('button', {name:'Confirm payment', exact:true}).click();
    await expect(page.getByText(/Partially paid/)).toBeVisible();
    await expect(page.getByText(/Remaining: 60/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`invoice-${theme}.png`), fullPage:true});
    await page.goto('/dashboard/wealth/');
    await expect(page.locator('.metric-panel').filter({hasText:'Net worth'})).toContainText(/800[,.]00/);
    let departureWarnings = 0;
    page.on('dialog', async dialog => { departureWarnings++; await dialog.accept(); });
    await page.locator('#id_start_month').fill('2026-01');
    await page.getByRole('button', {name:'Apply', exact:true}).click();
    await expect(page).toHaveURL(/start_month=2026-01/);
    expect(departureWarnings).toBe(0);
    expect(externalRequests).toEqual([]);
    await page.screenshot({path:testInfo.outputPath(`wealth-${theme}.png`), fullPage:true});
});
}

test('category split has a native no-JavaScript path', async ({browser}, testInfo) => {
    const context = await browser.newContext({javaScriptEnabled:false});
    const page = await context.newPage();
    try {
        const {split} = await prepare(page, testInfo);
        await page.goto(split);
        await page.locator('#id_splits-0-category').selectOption({label:'Food'});
        await page.locator('#id_splits-0-amount').fill('40');
        await page.locator('#id_splits-1-category').selectOption({label:'Transport'});
        await page.locator('#id_splits-1-amount').fill('60');
        await page.getByRole('button', {name:'Save split', exact:true}).click();
        await expect(page).toHaveURL(/transactions\/\d+\/edit\/$/);
    } finally { await context.close(); }
});
