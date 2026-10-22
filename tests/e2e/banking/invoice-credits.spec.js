// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, fields) {
    const source = await page.request.get(path);
    const csrf = (await source.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: source.url()}, maxRedirects: 0});
    const body = await response.text();
    const errors = [...body.matchAll(/data-field-error[^>]*>([^<]*)/g)].map(match => match[1]);
    expect(response.status(), JSON.stringify(errors)).toBe(302);
}

async function seed(page, info) {
    const username = `invoice-credit-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-Credits-2026!', password2: 'Tuxedo-Credits-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Local bank', color: '#111111'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Cash account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on', reserved_amount: '0'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    await post(page, '/banking/credit-cards/create/', {account, name: 'Prime ' + 'A'.repeat(70),
        card_type: 'PHYSICAL', closing_day: '31', due_day: '28', manual_settlement_from: today, color: '#111111'});
    const categoryName = 'Transport ' + 'B'.repeat(70);
    await post(page, '/categories/create/', {name: categoryName, transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: categoryName}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Synthetic purchase', amount: '100', date: today,
        transaction_type: 'EXPENSE', category, payment_channel: 'CREDIT_CARD', credit_card: card, installments: '1'});
    return {card, category, categoryName, today};
}

const english = {view: 'View invoice', add: 'Add invoice credit', save: 'Save', edit: 'Edit',
    remove: 'Delete', cancel: 'Cancel', empty: 'No invoice credits.'};
const portuguese = {view: 'Ver fatura', add: 'Adicionar crédito à fatura', save: 'Salvar', edit: 'Editar',
    remove: 'Excluir', cancel: 'Cancelar', empty: 'Nenhum crédito na fatura.'};

async function exercise(page, info, {theme, width, native = false, language = 'en', baseURL}) {
    const labels = language === 'pt-br' ? portuguese : english;
    const data = await seed(page, info);
    if (language !== 'en') await page.context().addCookies([{name: 'django_language', value: language, url: baseURL}]);
    await page.goto(`/banking/credit-cards/${data.card}/invoices/`);
    await page.getByRole('link', {name: labels.view, exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/banking\/invoices\/\d+\//);
    const invoice = new URL(page.url());
    const origin = invoice.pathname + invoice.search + '#invoice-credits';
    const add = page.getByRole('link', {name: labels.add, exact: true});
    await add.scrollIntoViewIfNeeded();
    const bounds = await add.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(new URL(await add.getAttribute('href'), page.url()).searchParams.get('next')).toBe(origin);
    await add.press('Enter');
    await expect(page.locator('#id_amount')).toBeVisible();
    await expect(page.locator('form.finance-entry-form')).toHaveAttribute('novalidate', '');
    await expect(page.locator('#id_category')).toHaveValue('');
    const title = 'Synthetic refund ' + 'C'.repeat(95);
    await page.locator('#id_title').fill(title);
    await page.locator('#id_amount').fill('-1');
    await page.locator('#id_date').fill(data.today.split('-').reverse().join('/'));
    if (native) await page.locator('#id_category').selectOption(data.category);
    else {
        const search = page.locator('#category-search');
        await search.fill(data.categoryName);
        await search.press('Enter');
        await expect(page.locator('#id_category')).toHaveValue('');
        const option = search.locator('..').getByRole('option').first();
        await expect(option).toHaveText(data.categoryName);
        expect((await option.boundingBox()).height).toBeGreaterThanOrEqual(44);
        await search.press('ArrowDown');
        await search.press('Enter');
        await expect(page.locator('#id_category')).toHaveValue(data.category);
        await search.press('Tab');
    }
    await page.getByRole('button', {name: labels.save, exact: true}).press('Enter');
    await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('#id_title')).toHaveValue(title);
    await expect(page.locator('#id_category')).toHaveValue(data.category);
    await expect(page.getByRole('link', {name: labels.cancel, exact: true})).toHaveAttribute('href', origin);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath(`credit-error-${theme}-${width}-${language}-${native}.png`), fullPage: true});
    await page.locator('#id_amount').fill('8.95');
    await page.getByRole('button', {name: labels.save, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    await page.waitForLoadState('load');
    const credits = page.locator('#invoice-credits');
    await expect(credits).toContainText(title);
    await expect(credits).toContainText(data.categoryName);
    await expect(credits).toContainText(/8[,.]95/);
    const creditRow = credits.locator('article').first();
    const [rowBounds, titleBounds] = await Promise.all([creditRow.boundingBox(), creditRow.locator('h3').boundingBox()]);
    expect(titleBounds.width).toBeGreaterThanOrEqual(rowBounds.width * 0.9);
    await expect(page.locator('#invoice-summary')).toContainText(/91[,.]05/);
    await expect(page.locator('#invoice-summary')).toContainText(/100[,.]00/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await credits.scrollIntoViewIfNeeded();
    await page.screenshot({path: info.outputPath(`credit-saved-${theme}-${width}-${language}-${native}.png`)});
    await credits.getByRole('link', {name: labels.edit, exact: true}).press('Enter');
    await expect(page.locator('#id_amount')).toHaveValue('8.95');
    await expect(page.locator('#id_category')).toHaveValue(data.category);
    if (!native) {
        await selectChoice(page.locator('#id_category'), data.category);
        await expect(page.locator('#category-search')).toBeFocused();
        await page.keyboard.press('Escape');
    }
    await page.locator('#id_amount').fill('9.25');
    await page.getByRole('button', {name: labels.save, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    await page.waitForLoadState('load');
    await expect(credits).toContainText(/9[,.]25/);
    await expect(page.locator('#invoice-summary')).toContainText(/90[,.]75/);
    await credits.getByRole('link', {name: labels.remove, exact: true}).press('Enter');
    await expect(page.getByRole('link', {name: labels.cancel, exact: true})).toHaveAttribute('href', origin);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath(`credit-delete-${theme}-${width}-${language}-${native}.png`)});
    await page.getByRole('link', {name: labels.cancel, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    await page.waitForLoadState('load');
    await expect(credits).toContainText(title);
    await credits.getByRole('link', {name: labels.remove, exact: true}).press('Enter');
    await page.getByRole('button', {name: labels.remove, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    await expect(credits).toContainText(labels.empty);
    await expect(page.locator('#invoice-summary')).toContainText(/100[,.]00/);
}

for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
    test(`invoice credits preserve keyboard, validation and native accounting (${theme}, ${width})`, async ({page, baseURL}, info) => {
        test.setTimeout(90000);
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await exercise(page, info, {theme, width, baseURL});
    });
}

for (const theme of ['light', 'dark']) {
    test(`Portuguese invoice credit forms remain readable on mobile (${theme})`, async ({page, baseURL}, info) => {
        test.setTimeout(90000);
        await page.setViewportSize({width: 390, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await exercise(page, info, {theme, width: 390, language: 'pt-br', baseURL});
    });
}

test.describe('invoice credits without JavaScript', () => {
    test.use({javaScriptEnabled: false});
    for (const width of [390, 1440]) test(`native create, edit and deliberate delete (${width})`, async ({page, baseURL}, info) => {
        test.setTimeout(90000);
        await page.setViewportSize({width, height: 900});
        await exercise(page, info, {theme: 'light', width, native: true, baseURL});
    });
});
