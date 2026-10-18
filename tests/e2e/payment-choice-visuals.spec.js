// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: token, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
}

async function seed(page, info) {
    const username = `payment-art-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Q8!vM5#rT2@pL9$x', password2: 'Q8!vM5#rT2@pL9$x'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Cedar bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    for (const [name, pix] of [['Daily account', true], ['No PIX account', false]]) {
        await post(page, '/banking/accounts/create/', {bank, name, currency: 'BRL',
            opening_date: '2020-01-01', opening_balance: '5000', ...(pix ? {pix_enabled: 'on'} : {})});
    }
    await post(page, '/categories/create/', {name: 'Food', transaction_type: 'EXPENSE'});
    await post(page, '/categories/create/', {name: 'Salary', transaction_type: 'INCOME'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: 'Daily account'}).getAttribute('value');
    const noPixAccount = await page.locator('#id_bank_account option').filter({hasText: 'No PIX account'}).getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Travel credit',
        color: '#5B3E7C', card_type: 'PHYSICAL', closing_day: '20', due_day: '28'});
    await post(page, '/banking/debit-cards/create/', {account, name: 'Daily debit', color: '#315D50'});
    await page.goto('/transactions/create/');
    const credit = await page.locator('#id_credit_card option').filter({hasText: 'Travel credit'}).getAttribute('value');
    const debit = await page.locator('#id_debit_card option').filter({hasText: 'Daily debit'}).getAttribute('value');
    await post(page, `/banking/credit-cards/${credit}/edit/`, {account, name: 'Travel credit',
        color: '#5B3E7C', use_gradient: 'on', gradient_end: '#C6A173', gradient_angle: '45',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28'});
    await page.goto('/transactions/create/');
    return {account, noPixAccount, credit, debit};
}

async function chooseExpense(page) {
    await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
}

async function canonicalAmount(page) {
    return page.locator('#transaction-entry-form').evaluate(form => new FormData(form).get('amount'));
}

function paymentPicker(page, id) {
    return page.locator(`#${id} + .search-choice`);
}

for (const theme of ['light', 'dark']) {
    test(`payment miniatures identify owned accounts, PIX and card colors with keyboard transitions (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account, noPixAccount, credit, debit} = await seed(page, info);
        await chooseExpense(page);
        const channel = page.locator('#id_payment_channel');
        const accountSelect = page.locator('#id_bank_account');
        const accounts = paymentPicker(page, 'id_bank_account');
        const search = accounts.getByRole('combobox');
        await selectChoice(channel, 'ACCOUNT');
        await expect(channel.locator('input[value="ACCOUNT"]')).toBeFocused();
        await expect(accountSelect).toHaveAttribute('data-payment-kind', 'account');
        await expect(accounts.getByRole('option')).toHaveCount(2);
        const daily = accounts.getByRole('option').filter({hasText: 'Daily account'});
        await expect(daily.locator('.payment-choice-name')).toHaveText('Daily account');
        await expect(daily.locator('.payment-choice-detail')).toContainText('Cedar bank');
        await expect(daily.locator('.payment-choice-detail')).toContainText('BRL');
        await expect(daily.locator('.payment-choice-art')).toHaveAttribute('data-choice-kind', 'account');
        await expect(daily.locator('.payment-choice-icon')).toBeVisible();
        await expect(daily.locator('.payment-choice-bank-dot')).toHaveCSS('background-color', 'rgb(49, 93, 80)');
        await page.screenshot({path: info.outputPath(`payment-accounts-${theme}.png`), fullPage: true});

        // Typing one exact result never selects a financial record implicitly.
        await search.focus();
        await search.fill('Daily');
        await search.press('Enter');
        await expect(accountSelect).toHaveValue('');
        await expect(search).toBeFocused();
        await search.press('ArrowDown');
        await expect(search).toHaveAttribute('aria-activedescendant', /-results-0$/);
        await search.press('Enter');
        await expect(accountSelect).toHaveValue(account);
        await search.press('Tab');
        await expect(daily).toBeVisible();
        await expect(daily).toHaveAttribute('aria-selected', 'true');
        await expect(accounts.getByRole('option')).toHaveCount(2);
        await expect(search).toHaveValue('');
        expect((await search.boundingBox()).height).toBe(44);
        expect((await search.boundingBox()).width).toBeLessThanOrEqual(480);
        // Filtering and leaving the field never dismiss the choice board or
        // implicitly replace a previously selected financial instrument.
        await search.fill('No PIX');
        await page.locator('#id_title').click();
        await expect(accounts.getByRole('option')).toHaveCount(1);
        await expect(accounts.getByRole('option')).toBeVisible();
        await expect(search).toHaveValue('No PIX');
        await expect(accountSelect).toHaveValue(account);
        await search.focus();
        await search.press('Escape');
        await expect(accounts.getByRole('option')).toHaveCount(2);
        await selectChoice(channel, 'PIX');
        await expect(accountSelect).toHaveValue(account);
        await expect(accountSelect).toHaveAttribute('data-payment-kind', 'pix');
        await expect(accounts.getByRole('option', {selected: true}).locator('.payment-choice-art')).toHaveAttribute('data-choice-kind', 'pix');
        await search.focus();
        await search.fill('');
        await expect(accounts.getByRole('option')).toHaveCount(1);
        await expect(accounts.getByRole('option').locator('.payment-choice-art')).toHaveAttribute('data-choice-kind', 'pix');
        await expect(page.locator(`#id_bank_account option[value="${noPixAccount}"]`)).toBeHidden();
        await search.press('Escape');
        await selectChoice(channel, 'ACCOUNT');
        await selectChoice(accountSelect, noPixAccount);
        await selectChoice(channel, 'PIX');
        await expect(accountSelect).toHaveValue('');
        await expect(accounts.getByRole('option', {selected: true})).toHaveCount(0);
        await expect(accounts.getByRole('option')).toHaveCount(1);

        await selectChoice(channel, 'CREDIT_CARD');
        const credits = paymentPicker(page, 'id_credit_card');
        await expect(accounts).toBeHidden();
        await expect(credits.getByRole('option')).toHaveCount(1);
        const cardOption = credits.getByRole('option');
        await expect(cardOption.locator('.payment-choice-name')).toHaveText('Travel credit');
        await expect(cardOption.locator('.payment-choice-detail')).toContainText('Daily account');
        await expect(cardOption.locator('.payment-choice-art[data-choice-kind="card"]')).toHaveCSS('background-image',
            'linear-gradient(45deg, rgb(91, 62, 124), rgb(198, 161, 115))');
        await page.evaluate(() => window.scrollTo({top: 0, behavior: 'instant'}));
        await page.screenshot({path: info.outputPath(`payment-miniatures-${theme}.png`), fullPage: true});
        await selectChoice(page.locator('#id_credit_card'), credit);
        await page.locator('#id_installments').focus();
        const selectedCredit = credits.locator('[data-entry-card-preview]');
        await expect(selectedCredit).toBeVisible();
        await expect(page.locator('[data-entry-card-preview]:visible')).toHaveCount(1);
        await expect(selectedCredit.locator('.payment-choice-art[data-choice-kind="card"]')).toHaveCSS('background-image',
            'linear-gradient(45deg, rgb(91, 62, 124), rgb(198, 161, 115))');
        await selectChoice(channel, 'DEBIT_CARD');
        await expect(page.locator('#id_credit_card')).toHaveValue('');
        const debits = paymentPicker(page, 'id_debit_card');
        await expect(debits.getByRole('option').locator('.payment-choice-art[data-choice-kind="card"]')).toHaveCSS('background-image',
            'linear-gradient(135deg, rgb(49, 93, 80), rgb(49, 93, 80))');
        await selectChoice(page.locator('#id_debit_card'), debit);
        await page.locator('#id_title').focus();
        await expect(debits.getByRole('option', {selected: true}).locator('.payment-choice-name')).toHaveText('Daily debit');
        await page.locator('#id_amount').fill('12.34');
        await page.locator('#id_date').fill('17/10/2026');
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_title-error-1')).toBeVisible();
        await expect(page.locator('#id_debit_card')).toHaveValue(debit);
        await expect(debits.getByRole('option', {selected: true}).locator('.payment-choice-name')).toHaveText('Daily debit');
        await expect(debits.getByRole('option', {selected: true}).locator('.payment-choice-bank-dot')).toHaveCSS('background-color', 'rgb(49, 93, 80)');
        await selectChoice(page.locator('#id_transaction_type'), 'INCOME');
        await expect(page.locator('#id_debit_card')).toHaveValue('');
        await expect(debits).toBeHidden();
        await expect(page.locator('[data-entry-card-preview]:visible')).toHaveCount(0);
        await selectChoice(channel, 'ACCOUNT');
        await page.setViewportSize({width: 390, height: 700});
        await search.focus();
        await search.fill('Daily');
        await search.press('ArrowDown');
        await expect(search).toBeFocused();
        await expect.poll(() => accounts.getByRole('option').evaluate(element => {
            const box = element.getBoundingClientRect();
            const dock = document.querySelector('.app-bottom-navigation').getBoundingClientRect();
            return box.x >= 0 && box.right <= innerWidth && box.bottom <= dock.top;
        })).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`payment-mobile-${theme}.png`)});
        await search.press('Enter');
        await expect(accountSelect).toHaveValue(account);
    });
}

for (const [language, theme] of [['en', 'light'], ['pt-br', 'dark']]) {
    test(`transaction amount follows cents, keyboard editing, paste and canonical POST (${language}, ${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account} = await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        await page.goto('/transactions/create/');
        const money = page.locator('#id_amount');
        const local = value => language === 'pt-br' ? value.replace('.', ',') : value;
        await expect(money).toHaveAttribute('data-money-input', '');
        await expect(money).toHaveAttribute('type', 'text');
        await expect(money).toHaveAttribute('inputmode', 'decimal');
        await money.focus();
        await money.pressSequentially('1234');
        await expect(money).toHaveValue(local('12.34'));
        await expect.poll(() => canonicalAmount(page)).toBe('12.34');
        await money.press('Backspace');
        await expect(money).toHaveValue(local('1.23'));
        await money.press('ControlOrMeta+A');
        await money.pressSequentially('9876');
        await expect(money).toHaveValue(local('98.76'));
        await money.press('Home');
        await money.press('ArrowRight');
        await money.press('Delete');
        await expect(money).toHaveValue(local('9.76'));
        await expect.poll(() => canonicalAmount(page)).toBe('9.76');
        await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
        await page.evaluate(() => navigator.clipboard.writeText('1.234,56'));
        await money.press('ControlOrMeta+A');
        await money.press('ControlOrMeta+V');
        await expect(money).toHaveValue(language === 'pt-br' ? '1.234,56' : '1,234.56');
        await expect.poll(() => canonicalAmount(page)).toBe('1234.56');
        await expect(money).toBeFocused();
        expect(await money.evaluate(input => getComputedStyle(input).outlineStyle !== 'none'
            || getComputedStyle(input).boxShadow !== 'none')).toBe(true);
        await money.press('Tab');
        await expect(money).not.toBeFocused();
        await chooseExpense(page);
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), account);
        await page.locator('#id_date').fill('17/10/2026');
        const save = page.getByRole('button', {name: language === 'en' ? 'Save' : 'Salvar', exact: true});
        await save.press('Enter');
        await expect(page.locator('#id_title-error-1')).toBeVisible();
        await expect.poll(() => canonicalAmount(page)).toBe('1234.56');
        await page.locator('#id_title').fill('Cents keyboard purchase');
        const submitted = page.waitForRequest(request => request.method() === 'POST'
            && new URL(request.url()).pathname === '/transactions/create/');
        await save.press('Enter');
        const payload = new URLSearchParams((await submitted).postData());
        expect(payload.get('amount')).toBe('1234.56');
        await expect(page).toHaveURL(/\/transactions\/$/);
        await page.locator('main').getByRole('link', {name: language === 'en' ? 'Edit' : 'Editar', exact: true}).press('Enter');
        await expect.poll(() => canonicalAmount(page)).toBe('1234.56');
        await money.focus();
        await money.press('ControlOrMeta+A');
        await money.press('Backspace');
        await expect(money).toHaveValue('');
        await expect.poll(() => canonicalAmount(page)).toBe('');
    });
}

test('transaction payment options retain native selectors and decimal submission without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 780}});
    try {
        const page = await context.newPage();
        const {account} = await seed(page, info);
        await chooseExpense(page);
        await expect(page.locator('#id_bank_account')).toBeVisible();
        await expect(page.locator('#id_amount')).toHaveAttribute('type', 'number');
        await page.locator('#id_title').fill('Native visual choice purchase');
        await page.locator('#id_amount').fill('12.34');
        await page.locator('#id_date').fill('17/10/2026');
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), account);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/transactions\/$/);
        await expect(page.locator('main')).toContainText('Native visual choice purchase');
        await page.locator('main').getByRole('link', {name: 'Edit', exact: true}).press('Enter');
        await expect(page.locator('#id_amount')).toHaveValue('12.34');
        await expect(page.locator('#id_bank_account')).toHaveValue(account);
    } finally {
        await context.close();
    }
});
