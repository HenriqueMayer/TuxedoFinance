// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `planning-refinement-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'MDY'});
    await post(page, '/banking/create/', {name: 'Planning bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'A ordinary account', currency: 'BRL',
        opening_balance: '0', opening_date: '2020-01-01', planning_enabled: 'on'});
    await post(page, '/banking/accounts/create/', {bank, name: 'Z planning account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2020-01-01', reserved_amount: '300'});
    await post(page, '/investments/add/', {institution: bank, name: 'Planning pot', currency: 'BRL',
        valuation_mode: 'MONETARY', purpose: 'MONTHLY_CASH', opening_balance: '500', opening_date: '2020-01-01'});
    await post(page, '/categories/create/', {name: 'Planning category', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: 'Z planning account'}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Planning category$/}).getAttribute('value');
    const goal = await post(page, '/planning/goals/create/', {name: 'Planning target', target_amount: '2000',
        currency: 'BRL', target_date: '2031-12-24'});
    await page.goto(`${goal}reserve/`);
    const pot = await page.locator('#id_source option').filter({hasText: 'Planning pot'}).getAttribute('value');
    const other = await post(page, '/planning/goals/create/', {name: 'Another active goal', target_amount: '2000',
        currency: 'BRL', reserve_now: 'on', source: `account:${account}`, reserved_amount: '250'});
    await post(page, `${other}reserve/`, {source: pot, amount: '100'});
    return {bank, account, category, pot, goal};
}

async function noOverflow(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) {
for (const width of [1440, 390]) {
test(`planning compact forms, capacity and exact balance sources (${width}, ${theme})`, async ({page}, info) => {
    await page.setViewportSize({width, height: 820});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const {bank, account, category, pot, goal} = await seed(page, info);
    const portuguese = width === 390;
    await page.context().addCookies([{name: 'django_language', value: portuguese ? 'pt-br' : 'en', url: info.project.use.baseURL}]);
    const save = portuguese ? 'Salvar' : 'Save';
    const cancel = portuguese ? 'Cancelar' : 'Cancel';
    const monthlyOrigin = '/planning/?month=2030-03#budgets';
    await page.goto(`/planning/budgets/create/?month=2030-03&next=${encodeURIComponent(monthlyOrigin)}`);
    const month = await page.locator('#id_month').boundingBox();
    const currency = await page.locator('#id_currency').boundingBox();
    if (width >= 640) {
        expect(Math.abs(month.y - currency.y)).toBeLessThan(3);
        expect(currency.x).toBeGreaterThan(month.x + month.width);
    } else expect(currency.y).toBeGreaterThan(month.y + month.height);
    await selectChoice(page.locator('#id_category'), category);
    if (width >= 640) {
        const categoryInput = await page.locator('#category-search').boundingBox();
        const limitInput = await page.locator('#id_amount').boundingBox();
        expect(Math.abs(categoryInput.y - limitInput.y)).toBeLessThanOrEqual(2);
    }
    await page.locator('#id_amount').fill('-1');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page.locator('#id_amount')).toHaveValue('-1');
    await expect(page.locator('[data-field-error]').first()).toBeVisible();
    await expect(page.locator('main input[name="next"]')).toHaveValue(monthlyOrigin);
    await noOverflow(page);
    await page.screenshot({path: info.outputPath(`budget-invalid-${width}-${theme}.png`), fullPage: true});
    await page.locator('#id_amount').focus();
    await page.keyboard.press('Tab');
    const saveButton = page.getByRole('button', {name: save, exact: true});
    await expect(saveButton).toBeFocused();
    expect(await saveButton.evaluate(element => element.matches(':focus-visible'))).toBe(true);
    if (width < 640) {
        await expect.poll(async () => {
            const button = await saveButton.boundingBox();
            const dock = await page.locator('.app-bottom-navigation').boundingBox();
            return button.y + button.height - dock.y;
        }).toBeLessThanOrEqual(0);
    }
    await page.getByRole('link', {name: cancel, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === monthlyOrigin);

    await page.goto('/planning/goals/create/');
    const amount = await page.locator('#id_target_amount').boundingBox();
    const targetCurrency = await page.locator('#id_currency').boundingBox();
    if (width >= 640) expect(Math.abs(amount.y - targetCurrency.y)).toBeLessThan(3);
    else expect(targetCurrency.y).toBeGreaterThan(amount.y + amount.height);
    await expect(page.locator('#goal-source-search')).toBeHidden();
    await page.getByRole('link', {name: cancel, exact: true}).press('Enter');

    const origin = `${goal}?context=reservation#goal-reservations`;
    await page.goto(`${goal}reserve/?next=${encodeURIComponent(origin)}`);
    const search = page.locator('#source-search');
    await expect(search).toHaveValue('');
    await expect(page.locator('#id_amount')).toBeHidden();
    await expect(page.locator(`#id_source option[value="account:${account}"]`)).toContainText('BRL 750.00');
    await expect(page.locator(`#id_source option[value="${pot}"]`)).toContainText('BRL 400.00');
    await selectChoice(page.locator('#id_source'), `account:${account}`);
    await search.press('Tab');
    await expect(search.locator('..').getByRole('button')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', {name: portuguese ? 'Explicar Valor reservado' : 'Explain Reserved amount', exact: true})).toBeFocused();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Tab');
    await expect(page.locator('#id_amount')).toBeFocused();
    expect(await page.locator('#id_amount').evaluate(element => element.matches(':focus-visible'))).toBe(true);
    await page.locator('#id_amount').fill('750.01');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page.locator('[role="alert"]').first()).toBeVisible();
    await expect(page.locator('#id_amount')).toHaveValue('750.01');
    await selectChoice(page.locator('#id_source'), pot);
    await expect(page.locator('#id_amount')).toHaveValue('');
    await page.locator('#id_amount').fill('400.01');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page.locator('#id_amount')).toHaveValue('400.01');
    await expect(page.locator('[role="alert"]').first()).toBeVisible();
    await noOverflow(page);
    await page.screenshot({path: info.outputPath(`reservation-invalid-${width}-${theme}.png`), fullPage: true});
    await selectChoice(page.locator('#id_source'), `account:${account}`);
    await page.locator('#id_amount').fill('200');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    // MDY is a user preference even while the interface language is Portuguese.
    await expect(page.locator('main')).toContainText('12/24/2031');
    await expect(page.locator('main')).not.toContainText('24/12/2031');
    await post(page, `${goal}reserve/`, {source: pot, amount: '100'});
    await page.goto(origin);
    const bankReservation = page.locator('main article').filter({has: page.locator(`a[href="/banking/${bank}/#account-row-${account}"]`)});
    await bankReservation.getByRole('link', {name: portuguese ? 'Editar reserva' : 'Edit reservation', exact: true}).press('Enter');
    await expect(page.locator('#id_source')).toHaveValue(`account:${account}`);
    await expect(page.locator('#id_amount')).toHaveValue(/^200(?:[,.]00)?$/);
    await expect(page.locator(`#id_source option[value="account:${account}"]`)).toContainText('BRL 750.00');
    await page.locator('#id_amount').fill('750.01');
    await page.getByRole('button', {name: save, exact: true}).press('Enter');
    await expect(page.locator('[role="alert"]').first()).toBeVisible();
    await expect(page.locator('#id_source')).toHaveValue(`account:${account}`);
    await expect(page.locator('#id_amount')).toHaveValue('750.01');
    await page.getByRole('link', {name: cancel, exact: true}).press('Enter');
    await page.goto(origin);
    const bankSource = page.locator(`main a[href="/banking/${bank}/#account-row-${account}"]`);
    await expect(bankSource).toHaveAttribute('hx-swap', 'innerHTML show:none');
    await bankSource.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === `/banking/${bank}/` && url.hash === `#account-row-${account}`);
    await expect(page.locator(`#account-name-${account}`)).toBeInViewport();
    await expect(page.locator('main #id_name')).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    // Back authorizes a fresh GET. Wait for that workspace to finish settling
    // before starting a second boosted navigation from its source links.
    await expect(page.getByRole('heading', {name: 'Planning target', exact: true})).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
    await expect(page.locator('body')).not.toHaveAttribute('aria-busy', 'true');
    const [, product, asset] = pot.split(':');
    await page.locator(`main a[href="/investments/positions/${product}/${asset}/"]`).press('Enter');
    await expect(page).toHaveURL(new RegExp(`/investments/positions/${product}/${asset}/$`));
    await expect(page.locator('main')).toContainText('Planning pot');
    await expect(page.locator('main #id_name')).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
    await noOverflow(page);
});
}

test(`signal settings and review actions preserve the reviewed consultation (${theme})`, async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 820});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const {account, category} = await seed(page, info);
    await page.context().addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
    const date = new Date().toISOString().slice(0, 10);
    for (let index = 0; index < 2; index++) await post(page, '/transactions/create/', {
        title: 'Review duplicate', amount: '1', transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT',
        bank_account: account, category, date});
    const origin = '/planning/signals/?reviewed=1';
    await page.goto('/planning/signals/');
    await page.locator('#signal-filters input[name="reviewed"]').press('Space');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    const settingsTarget = new URL(await page.getByRole('link', {name: 'Signal settings', exact: true}).getAttribute('href'), info.project.use.baseURL);
    expect(settingsTarget.searchParams.get('next')).toBe(origin);
    await page.getByRole('link', {name: 'Signal settings', exact: true}).press('Enter');
    await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
    await page.locator('#id_duplicate_days').fill('99');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.locator('#id_duplicate_days')).toHaveValue('99');
    await expect(page.locator('[data-field-error]').first()).toBeVisible();
    await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    await expect(page.locator('#signal-filters input[name="reviewed"]')).toBeChecked();
    await page.getByRole('link', {name: 'Signal settings', exact: true}).press('Enter');
    await page.locator('#id_duplicate_days').fill('2');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    await page.getByRole('button', {name: 'Acknowledge', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    await expect(page.getByRole('button', {name: 'Reopen signal', exact: true})).toBeVisible();
    await page.getByRole('button', {name: 'Reopen signal', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    await expect(page.getByRole('button', {name: 'Acknowledge', exact: true})).toBeVisible();
    await noOverflow(page);
});
}

test('native planning reservations retain complete fields, capacity errors and safe origin', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false});
    const page = await context.newPage();
    try {
        const {account, goal} = await seed(page, info);
        await context.addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
        const origin = `${goal}?context=native#goal-reservations`;
        await page.goto(`${goal}reserve/?next=${encodeURIComponent(origin)}`);
        await expect(page.locator('#id_source')).toBeVisible();
        await expect(page.locator('#id_amount')).toBeVisible();
        await page.locator('#id_source').selectOption(`account:${account}`);
        await page.locator('#id_amount').fill('750.01');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('[role="alert"]').first()).toBeVisible();
        await expect(page.locator('#id_amount')).toHaveValue('750.01');
        await page.locator('#id_amount').fill('150');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
        await expect(page.locator('main')).toContainText(/150[,.]00/);
    } finally {await context.close();}
});
