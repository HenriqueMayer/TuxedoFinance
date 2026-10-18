// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const fs = require('node:fs/promises');
const {resolve} = require('node:path');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: token, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(result.status(), await result.text()).toBe(302);
}
async function seed(page, info, counts = {banks: 20, accounts: 12, cards: 12}) {
    const username = `bank-practical-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    const names = {bank: 'Institution' + 'X'.repeat(85), account: 'Account' + 'Y'.repeat(90), card: 'Card' + 'Z'.repeat(92)};
    for (let i = 0; i < counts.banks; i++) await post(page, '/banking/create/', {name: i === counts.banks - 1 ? names.bank : `Audit bank ${String(i).padStart(2, '0')}`, color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: names.bank}).getAttribute('value');
    for (let i = 0; i < counts.accounts; i++) await post(page, '/banking/accounts/create/', {bank,
        name: i === counts.accounts - 1 ? names.account : `Audit account ${String(i).padStart(2, '0')}`, currency: 'BRL', opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on', reserved_amount: '0'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').filter({hasText: names.account}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    for (let i = 0; i < counts.cards; i++) await post(page, '/banking/credit-cards/create/', {account,
        name: i === counts.cards - 1 ? names.card : `Audit card ${String(i).padStart(2, '0')}`, card_type: 'PHYSICAL', closing_day: '20', due_day: '28', manual_settlement_from: today,
        color: '#5B3E7C', use_gradient: 'on', gradient_end: '#315D50', gradient_angle: '135'});
    await post(page, '/categories/create/', {name: 'Practical audit groceries', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').filter({hasText: names.card}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Practical audit groceries$/}).getAttribute('value');
    await post(page, '/transactions/create/', {title: 'Practical audit purchase', amount: '100', transaction_type: 'EXPENSE', category,
        payment_channel: 'CREDIT_CARD', credit_card: card, date: today, installments: '1'});
    await post(page, '/banking/exchange-rates/create/', {from_currency: 'USD', to_currency: 'BRL', rate: '5.12345678', effective_date: '2020-01-01', notes: 'Local audit evidence'});
    await post(page, '/banking/loyalty/create/', {name: 'Audit points', bank, unit_name: 'points'});
    return {bank, account, card, names, today};
}
async function measure(locator) {
    return locator.evaluate(element => {
        const range = document.createRange(); range.selectNodeContents(element);
        const text = range.getBoundingClientRect();
        return {left: text.left, right: text.right, scroll: document.documentElement.scrollWidth, viewport: innerWidth};
    });
}
async function expectChoiceFits(input, value, label) {
    await input.fill(label);
    const option = input.locator('..').getByRole('option').first();
    await expect(input.locator('..').getByRole('option')).toHaveCount(1);
    await expect(option).toHaveText(label);
    const size = await option.boundingBox();
    expect(size.height).toBeGreaterThanOrEqual(44);
    expect(size.x).toBeGreaterThanOrEqual(0);
    expect(size.x + size.width).toBeLessThanOrEqual(await input.page().evaluate(() => innerWidth));
    expect(size.y).toBeGreaterThanOrEqual(64);
    expect(size.y + size.height).toBeLessThanOrEqual(await input.page().evaluate(() => innerHeight - (innerWidth < 768 ? 72 : 0)));
    expect(await option.evaluate(element => element.scrollWidth - element.clientWidth)).toBe(0);
    await expect(input).toBeFocused();
    await input.press('ArrowDown');
    await expect(input).toHaveAttribute('aria-activedescendant', await option.getAttribute('id'));
    await input.press('Enter');
    await expect(input).toHaveValue(label);
    await expect(input).toBeFocused();
    await expect(input.page().locator(`#${value.id}`)).toHaveValue(value.selected);
}
async function catalogue(page, info, theme) {
    const root = resolve(__dirname, '../..');
    await page.route('**/audit-reference/**', route => {
        const file = new URL(route.request().url()).pathname.slice('/audit-reference/'.length);
        if ((file.startsWith('docs/design-system') || file.startsWith('static/')) && !file.split('/').includes('..')) return route.fulfill({path: resolve(root, file)});
        return route.abort();
    });
    await page.goto('/audit-reference/docs/design-system.html#navigation');
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#navigation').scrollIntoViewIfNeeded();
    await page.screenshot({path: info.outputPath(`01-design-reference-navigation-${theme}.png`)});
    await page.locator('#forms').scrollIntoViewIfNeeded();
    await page.screenshot({path: info.outputPath(`02-design-reference-forms-${theme}.png`)});
}

for (const theme of ['light', 'dark']) {
    test(`long record actions and activity retain readable native context (${theme})`, async ({page}, info) => {
        test.setTimeout(60000);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await seed(page, info, {banks: 2, accounts: 2, cards: 2});
        await page.goto('/banking/transfers/create/');
        const destination = await page.locator(`#id_destination_account option[value]:not([value=""]):not([value="${data.account}"])`).first().getAttribute('value');
        const movementName = 'AuditMovement' + 'M'.repeat(180);
        await post(page, '/banking/transfers/create/', {source_account: data.account, destination_account: destination,
            source_amount: '5', destination_amount: '5', date: data.today, notes: movementName});
        const observations = [];
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            const notes = {width, cancelLinks: []}; observations.push(notes);
            for (const [type, id] of [['', data.bank], ['accounts/', data.account], ['credit-cards/', data.card]]) {
                const origin = `/banking/${data.bank}/#account-row-${data.account}`;
                await page.goto(`/banking/${type}${id}/delete/?next=${encodeURIComponent(origin)}`);
                notes[type || 'bank'] = await measure(page.locator('main h1'));
                await page.screenshot({path: info.outputPath(`22-delete-${type.replace('/', '') || 'bank'}-${theme}-${width}.png`)});
                notes.cancelLinks.push({expected: origin, actual: await page.getByRole('link', {name: 'Cancel', exact: true}).getAttribute('href')});
                await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
                await expect(page.locator('#planning-availability')).toBeVisible();
            }
            await page.goto(`/banking/${data.bank}/`);
            await page.locator('#bank-activity > summary').press('Enter');
            const activity = page.locator('#bank-activity');
            await expect(activity.getByText(movementName, {exact: true})).toHaveCount(2);
            notes.movement = await measure(activity.getByText(movementName, {exact: true}).first());
            await activity.getByText(movementName, {exact: true}).first().scrollIntoViewIfNeeded();
            await page.screenshot({path: info.outputPath(`23-activity-${theme}-${width}.png`)});
        }
        await fs.writeFile(info.outputPath('24-action-observations.json'), JSON.stringify(observations, null, 2));
        expect(observations.flatMap(item => item.cancelLinks.filter(link => link.expected !== link.actual))).toEqual([]);
        expect(observations.flatMap(item => ['bank', 'accounts/', 'credit-cards/', 'movement']
            .filter(name => item[name].right > item.width + 1 || item[name].left < -1 || item[name].scroll > item.width)
            .map(name => ({width: item.width, name, ...item[name]})))).toEqual([]);
    });

    test(`fresh Accounts cards invoice and FX practical review (${theme})`, async ({page}, info) => {
        // The owned fixture, two complete viewport walkthroughs, screenshots
        // and browser/video teardown share this bounded audit budget.
        test.setTimeout(180000);
        const errors = []; page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width: 1280, height: 900});
        await catalogue(page, info, theme);
        const data = await seed(page, info);
        const observations = [];
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            const capture = async (number, name) => page.screenshot({path: info.outputPath(`${number}-${name}-${theme}-${width}.png`)});
            const notes = {width}; observations.push(notes);
            await page.goto('/banking/');
            await expect(page.locator('#bank-results [data-bank-open]')).toHaveCount(20);
            notes.overview = await measure(page.locator(`#bank-${data.bank} span.font-semibold`));
            await capture('03', 'accounts-overview');
            await page.locator(`#bank-${data.bank}`).press('Enter');
            await expect(page).toHaveURL(new RegExp(`/banking/${data.bank}/$`));
            await expect(page.locator('article[id^="account-row-"]')).toHaveCount(12);
            notes.bankTitle = await measure(page.locator(`#bank-detail-title-${data.bank}`));
            const title = page.locator(`#bank-detail-title-${data.bank}`);
            await expect(title).toHaveAccessibleName(data.names.bank);
            expect(await title.evaluate(element => element.clientHeight <= 2 * parseFloat(getComputedStyle(element).lineHeight) + 1)).toBe(true);
            const row = page.locator(`#account-row-${data.account}`);
            notes.accountTitle = await measure(row.locator('h3'));
            await capture('04', 'bank-open');
            const accountMenu = row.locator('.bank-account-header details.compact-menu');
            await accountMenu.locator(':scope > summary').press('Enter');
            await page.keyboard.press('Tab');
            await expect(accountMenu.getByRole('link', {name: `Edit ${data.names.account} and reserve`, exact: true})).toBeFocused();
            notes.accountMenu = await measure(accountMenu.locator('.secondary-actions-panel'));
            await capture('05', 'account-menu');
            await page.keyboard.press('Escape');
            const cardRow = page.locator(`#credit-card-${data.card}`);
            notes.cardTitle = await measure(cardRow.locator('.card-miniature-heading p').first());
            await cardRow.locator('details.compact-menu > summary').press('Enter');
            await page.keyboard.press('Tab');
            notes.cardMenu = await measure(cardRow.locator('.secondary-actions-panel'));
            await capture('06', 'card-menu');
            await cardRow.getByRole('link', {name: 'Edit', exact: true}).press('Enter');
            await expect(page.locator('#id_name')).toHaveValue(data.names.card);
            await page.locator('#id_closing_day').fill('32');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_closing_day')).toHaveAttribute('aria-invalid', 'true');
            await expect(page.locator('#id_use_gradient')).toBeChecked();
            await page.locator('#id_account-search').focus();
            const firstOption = page.locator('#id_account-search').locator('..').getByRole('option').first();
            notes.accountChoiceOverflow = await firstOption.evaluate(element => Math.max(element.scrollWidth - element.clientWidth,
                ...Array.from(element.children, child => child.scrollWidth - child.clientWidth)));
            await capture('07', 'card-edit-bound');
            const accountLabel = await page.locator(`#id_account option[value="${data.account}"]`).textContent();
            await expectChoiceFits(page.locator('#id_account-search'), {id: 'id_account', selected: data.account}, accountLabel);
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === `/banking/${data.bank}/`);
            await page.goto(`/banking/credit-cards/create/?account=${data.account}`);
            await page.locator('#id_use_gradient').press('Space');
            await page.locator('[data-card-angle-control] [role="slider"]').focus();
            await page.keyboard.press('ArrowRight');
            await capture('08', 'card-create-gradient');
            await page.goto(`/banking/accounts/${data.account}/edit/`);
            await capture('09', 'account-complete-form');
            const bankInput = page.locator('#id_bank-search');
            await bankInput.focus();
            await expectChoiceFits(bankInput, {id: 'id_bank', selected: data.bank}, data.names.bank);
            await capture('09b', 'bank-choice-focus');
            if (width === 1280) {
                const fields = await Promise.all(['#id_currency', '#id_opening_balance'].map(id => page.locator(id).boundingBox()));
                expect(Math.abs(fields[0].y - fields[1].y)).toBeLessThan(2);
            }
            await page.goto('/banking/loyalty/create/');
            await capture('10', 'loyalty-complete-form');
            await page.goto('/banking/transfers/create/');
            await selectChoice(page.locator('#id_source_account'), data.account);
            await capture('11', 'transfer-form');
            await page.goto('/banking/invoices/');
            await expect(page.locator('#invoice-results a.invoice-card')).toHaveCount(12);
            notes.invoiceCard = await measure(page.locator(`#invoice-card-${data.card} h2`));
            await capture('12', 'invoices-overview');
            if (width === 390) {
                const month = await page.locator('#invoice-filter-month-trigger').boundingBox();
                expect(month.height).toBe(44);
                const pair = await Promise.all(['#invoice-filter-bank-search', '#invoice-filter-status'].map(id => page.locator(id).boundingBox()));
                expect(Math.abs(pair[0].y - pair[1].y)).toBeLessThan(2);
                expect(pair[0].y).toBeGreaterThan(month.y);
            }
            await page.locator('#invoice-filter-q').fill(data.names.card);
            await expect(page).toHaveURL(url => url.searchParams.get('q') === data.names.card);
            await page.locator(`#invoice-card-${data.card}`).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === `/banking/credit-cards/${data.card}/invoices/`);
            notes.invoiceHeading = await measure(page.locator('main h1'));
            await capture('13', 'card-invoices');
            await page.locator('#invoice-results').getByRole('link', {name: 'View invoice', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/banking\/invoices\/\d+\//);
            const invoiceUrl = page.url();
            notes.detailHeading = await measure(page.locator('main h1'));
            await capture('14', 'invoice-detail');
            await selectChoice(page.locator('#id_account'), data.account);
            await page.locator('#id_amount').fill('-1');
            await page.locator('#id_date').fill(data.today.split('-').reverse().join('/'));
            await page.getByRole('button', {name: 'Confirm payment', exact: true}).press('Enter');
            await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
            await capture('15', 'invoice-payment-error');
            await page.locator('#id_amount').fill('10');
            await page.getByRole('button', {name: 'Confirm payment', exact: true}).press('Enter');
            // This is a native POST/redirect. Its new HTML can become queryable
            // before load finishes; use the completed document before focusing
            // the next keyboard action, rather than racing document replacement.
            await expect(page).toHaveURL(url => url.pathname === new URL(invoiceUrl).pathname && url.hash === '#invoice-summary');
            await page.waitForLoadState('load');
            await expect(page.locator('#invoice-payments')).toContainText(/10[,.]00/);
            const payments = page.locator('#invoice-payments');
            notes.paymentEdit = await payments.getByRole('link', {name: 'Edit', exact: true}).first().getAttribute('href');
            notes.paymentDelete = await payments.getByRole('link', {name: 'Delete', exact: true}).first().getAttribute('href');
            notes.invoiceLocation = new URL(invoiceUrl).pathname + new URL(invoiceUrl).search;
            expect(new URL(notes.paymentEdit, page.url()).searchParams.get('next')).toBe(notes.invoiceLocation + '#invoice-payments');
            expect(new URL(notes.paymentDelete, page.url()).searchParams.get('next')).toBe(notes.invoiceLocation + '#invoice-payments');
            const paymentEdit = payments.getByRole('link', {name: 'Edit', exact: true}).first();
            await paymentEdit.focus();
            await expect(paymentEdit).toBeFocused();
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(/\/banking\/invoice-payments\/\d+\/edit\//);
            await expect(page.locator('#id_amount')).toHaveValue('10.00');
            await page.locator('#id_amount').fill('-1');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_amount')).toHaveAttribute('aria-invalid', 'true');
            await expect(page.getByRole('link', {name: 'Cancel', exact: true})).toHaveAttribute('href', notes.invoiceLocation + '#invoice-payments');
            await page.locator('#id_amount').fill('10.00');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === new URL(invoiceUrl).pathname && url.search === new URL(invoiceUrl).search && url.hash === '#invoice-payments');
            await payments.getByRole('link', {name: 'Delete', exact: true}).first().press('Enter');
            await expect(page).toHaveURL(/\/banking\/invoice-payments\/\d+\/delete\//);
            await expect(page.getByRole('link', {name: 'Cancel', exact: true})).toHaveAttribute('href', notes.invoiceLocation + '#invoice-payments');
            notes.deleteCancel = await page.getByRole('link', {name: 'Cancel', exact: true}).getAttribute('href');
            expect(notes.deleteCancel).toBe(notes.invoiceLocation + '#invoice-payments');
            await capture('16', 'payment-delete-return');
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === new URL(invoiceUrl).pathname && url.search === new URL(invoiceUrl).search && url.hash === '#invoice-payments');
            await page.goto('/banking/exchange-rates/');
            await page.locator('#rate-filter-date_from').fill('03/01/2020');
            await page.locator('#rate-filter-date_from').press('Tab');
            await page.locator('#rate-filter-date_to').fill('01/01/2020');
            await page.locator('#rate-filter-date_to').press('Tab');
            await expect(page.locator('#rate-filter-date_to-error-1')).toBeVisible();
            const dateBoxes = await Promise.all(['#rate-filter-date_from', '#rate-filter-date_to'].map(id => page.locator(id).boundingBox()));
            expect(Math.abs(dateBoxes[0].y - dateBoxes[1].y), 'The error belongs below its date without displacing the adjacent date').toBeLessThan(2);
            await capture('17', 'fx-filter-invalid');
            await page.goto('/banking/exchange-rates/create/');
            await page.locator('#id_from_currency').selectOption('USD');
            await page.locator('#id_to_currency').selectOption('BRL');
            await page.locator('#id_rate').fill('5.12345678');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_rate')).toHaveValue('5.12345678');
            await capture('18', 'fx-complete-bound');
        }
        await fs.writeFile(info.outputPath('19-observations.json'), JSON.stringify(observations, null, 2));
        expect(errors).toEqual([]);
        expect(observations.flatMap(item => ['overview','bankTitle','accountTitle','cardTitle','accountMenu','cardMenu','invoiceCard','invoiceHeading','detailHeading']
            .filter(name => item[name].right > item.width + 1 || item[name].left < -1 || item[name].scroll > item.width)
            .map(name => ({width: item.width, name, ...item[name]})))).toEqual([]);
        expect(observations.map(item => item.accountChoiceOverflow)).toEqual([0, 0]);
    });

    if (theme === 'light') test('complete banking fields and invoice context retain native submissions', async ({browser, baseURL}, info) => {
        test.setTimeout(90000);
        const context = await browser.newContext({javaScriptEnabled: false, baseURL, viewport: {width: 390, height: 900}});
        const page = await context.newPage();
        try {
            const data = await seed(page, info, {banks: 2, accounts: 2, cards: 2});
            await page.goto(`/banking/accounts/${data.account}/edit/?next=%2Fbanking%2F${data.bank}%2F%23account-row-${data.account}`);
            await expect(page.locator('#id_bank')).toBeVisible();
            await page.locator('#id_name').fill('Native account edit');
            await page.locator('#id_pix_enabled').press('Space');
            await page.locator('#id_reserved_amount').fill('-1');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_reserved_amount')).toHaveAttribute('aria-invalid', 'true');
            await expect(page.locator('#id_pix_enabled')).toBeChecked();
            await page.locator('#id_reserved_amount').fill('2.25');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === `/banking/${data.bank}/` && url.hash === `#account-row-${data.account}`);
            await page.goto(`/banking/credit-cards/${data.card}/edit/`);
            await expect(page.locator('#id_account')).toBeVisible();
            await expect(page.locator('#id_use_gradient')).toBeChecked();
            await expect(page.locator('#id_gradient_angle')).toBeVisible();
            await page.locator('#id_gradient_angle').fill('225');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await page.goto(`/banking/credit-cards/${data.card}/edit/`);
            await expect(page.locator('#id_gradient_angle')).toHaveValue('225');
            await expect(page.locator('#id_gradient_end')).toHaveValue('#315d50');
            await page.goto('/banking/exchange-rates/create/?next=%2Fbanking%2Fexchange-rates%2F%3Fq%3DNative');
            await page.locator('#id_from_currency').selectOption('EUR');
            await page.locator('#id_to_currency').selectOption('BRL');
            await page.locator('#id_rate').fill('6.12345678');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_rate')).toHaveValue('6.12345678');
            await expect(page.locator('#id_effective_date')).toHaveAttribute('aria-invalid', 'true');
            await page.locator('#id_effective_date').fill('01/01/2020');
            await page.locator('#id_notes').fill('Native evidence');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === '/banking/exchange-rates/' && url.searchParams.get('q') === 'Native');
            await expect(page.locator('#rate-results')).toContainText('6,12345678');
            await page.screenshot({path: info.outputPath(`20-native-fields-${theme}-390.png`)});
            await page.goto(`/banking/credit-cards/${data.card}/invoices/?q=${data.names.card}`);
            await page.getByRole('link', {name: 'View invoice', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/banking\/invoices\/\d+\//);
            const invoice = new URL(page.url());
            const expectedReturn = invoice.pathname + invoice.search + '#invoice-payments';
            await page.locator('#id_account').selectOption(data.account);
            await page.locator('#id_amount').fill('10');
            await page.locator('#id_date').fill(data.today);
            await page.getByRole('button', {name: 'Confirm payment', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.hash === '#invoice-summary');
            await page.locator('#invoice-payments').getByRole('link', {name: 'Delete', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/invoice-payments\/\d+\/delete\//);
            await expect(page.getByRole('link', {name: 'Cancel', exact: true})).toHaveAttribute('href', expectedReturn);
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === expectedReturn);
            await page.locator('#invoice-payments').getByRole('link', {name: 'Delete', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/invoice-payments\/\d+\/delete\//);
            await page.getByRole('button', {name: 'Delete', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === expectedReturn);
            await expect(page.locator('#invoice-payments')).toContainText('No confirmed payments.');
            await page.screenshot({path: info.outputPath('21-native-invoice-context-390.png')});
            await post(page, '/banking/create/', {name: 'Native empty institution', color: '#315D50'});
            await page.goto('/banking/');
            const emptyCard = page.locator('.bank-overview-card').filter({has: page.getByText('Native empty institution', {exact: true})});
            const emptyDestination = await emptyCard.getAttribute('href');
            await emptyCard.press('Enter');
            await page.locator('.bank-workspace-panel-header details.compact-menu > summary').press('Enter');
            await page.locator('.bank-workspace-panel-header details.compact-menu').getByRole('link', {name: 'Delete', exact: true}).press('Enter');
            await expect(page.getByRole('link', {name: 'Cancel', exact: true})).toHaveAttribute('href', emptyDestination);
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === emptyDestination);
            await page.locator('.bank-workspace-panel-header details.compact-menu > summary').press('Enter');
            await page.locator('.bank-workspace-panel-header details.compact-menu').getByRole('link', {name: 'Delete', exact: true}).press('Enter');
            await page.getByRole('button', {name: 'Delete', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === '/banking/');
            await expect(page.getByText('Native empty institution', {exact: true})).toHaveCount(0);
            await page.screenshot({path: info.outputPath('25-native-empty-bank-delete-390.png')});
        } finally { await context.close(); }
    });
}
