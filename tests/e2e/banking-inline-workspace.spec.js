// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('./helpers/forms');

async function post(page, path, fields = {}) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info, manyBanks = false) {
    const username = `bank-inline-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    const banks = [];
    // Create in reverse name order to expose a GROUP BY index-order regression.
    for (const [name, amount] of [['Savings bank', '500'], ['Everyday bank', '1000']]) {
        await post(page, '/banking/create/', {name, color: '#315D50'});
        await page.goto('/banking/accounts/create/');
        const bank = await page.locator('#id_bank option').filter({hasText: name}).getAttribute('value');
        await post(page, '/banking/accounts/create/', {bank, name: name + ' account', currency: 'BRL',
            opening_date: '2020-01-01', opening_balance: amount, planning_enabled: 'on'});
        banks.unshift(bank);
    }
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').filter({hasText: 'Everyday bank account'}).getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Everyday credit',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28', color: '#5B3E7C'});
    await post(page, '/banking/exchange-rates/create/', {from_currency: 'USD', to_currency: 'BRL',
        rate: '5.12345678', effective_date: '2026-10-02', notes: 'Exact local rate'});
    if (manyBanks) {
        for (let index = 1; index <= 38; index++) {
            await post(page, '/banking/create/', {name: `Additional bank ${String(index).padStart(2, '0')}`, color: '#315D50'});
        }
    }
    return {banks, account};
}

async function expectFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) {
    for (const width of [1280, 390]) {
        test(`bank panels open, switch, edit and minimize with native history (${theme}, ${width})`, async ({page}, info) => {
            const pageErrors = [];
            page.on('pageerror', error => pageErrors.push(error.message));
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await page.setViewportSize({width, height: 900});
            const {banks, account} = await seed(page, info, true);
            await page.goto('/banking/');
            const summary = page.locator('#planning-availability');
            await expect(summary.locator('details')).toHaveCount(0);
            for (const name of ['Bank balances', 'Cash pots to redeem', 'Set aside']) {
                await expect(summary.getByText(name, {exact: true})).toBeVisible();
            }
            await expect(summary).toContainText('1.500,00');
            const bankOrder = await page.locator('.bank-workspace-tab').evaluateAll(links => links.map(link => link.id));
            expect(bankOrder).toHaveLength(40);
            await page.locator('main').evaluate(element => { element.dataset.inlineSentinel = 'mounted'; });
            const first = page.locator(`#bank-${banks[0]}`);
            await first.focus();
            const overviewTop = await page.evaluate(() => scrollY);
            expect(overviewTop).toBeGreaterThan(100);
            await first.press('Enter');
            await expect(page).toHaveURL(new RegExp(`/banking/${banks[0]}/$`));
            await expect(page.locator('main')).toHaveAttribute('data-inline-sentinel', 'mounted');
            await expect(page.locator('#bank-results')).toHaveCount(0);
            await expect(page.locator('.bank-workspace-tab')).toHaveCount(0);
            await expect(page.locator('#bank-switch-form, #bank-workspace-choice, [data-bank-switch-link]')).toHaveCount(0);
            await expect(page.locator(`#bank-detail-title-${banks[0]}`)).toBeFocused();
            await expect(page.locator('#bank-workspace-panel')).toBeVisible();
            await expect(page.locator(`#account-row-${account}`)).toBeVisible();
            await page.keyboard.press('Tab');
            const minimize = page.getByRole('link', {name: 'Minimize Everyday bank', exact: true});
            await expect(minimize).toBeFocused();
            await expect(minimize).toHaveText('Minimize');
            const minimizeBounds = await minimize.boundingBox();
            expect(minimizeBounds.height).toBeGreaterThanOrEqual(44);
            expect(minimizeBounds.width).toBeGreaterThanOrEqual(44);
            await expectFits(page);
            const windowbar = await page.locator('.bank-workspace-windowbar').boundingBox();
            expect(windowbar.height).toBeLessThanOrEqual(width < 768 ? 140 : 100);
            await page.screenshot({path: info.outputPath(`bank-window-40-${theme}-${width}.png`)});
            await page.locator('.bank-workspace-windowbar').screenshot({path: info.outputPath(`bank-windowbar-${theme}-${width}.png`)});
            await minimize.press('Enter');
            await expect(page).toHaveURL(/\/banking\/$/);
            await expect(first).toBeFocused();
            await expect.poll(async () => Math.abs((await page.evaluate(() => scrollY)) - overviewTop)).toBeLessThan(8);
            expect(await page.locator('.bank-workspace-tab').evaluateAll(links => links.map(link => link.id))).toEqual(bankOrder);
            await page.locator(`#bank-${banks[1]}`).press('Enter');
            await expect(page).toHaveURL(new RegExp(`/banking/${banks[1]}/$`));
            await expect(page.locator('#bank-workspace-panel')).toContainText('Savings bank account');
            await expect(page.locator('#bank-workspace-panel')).not.toContainText('Everyday bank account');
            await page.goBack();
            await expect(page.locator('.bank-workspace-tab')).toHaveCount(40);
            await page.goBack();
            await expect(page.locator(`#bank-detail-title-${banks[0]}`)).toHaveText('Everyday bank');
            await expect(page.locator(`#account-row-${account}`)).toBeVisible();

            const row = page.locator(`#account-row-${account}`);
            await row.locator('.bank-account-header .compact-menu > summary').press('Enter');
            await row.getByRole('link', {name: 'Edit Everyday bank account and reserve', exact: true}).press('Enter');
            await expect(page).toHaveURL(new RegExp(`/banking/accounts/${account}/edit/`));
            await expect(page.locator('main form [name="next"]')).toHaveValue(`/banking/${banks[0]}/`);
            await page.locator('#id_name').fill('Renamed account');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page).toHaveURL(new RegExp(`/banking/${banks[0]}/$`));
            await expect(page.locator('#bank-workspace-panel')).toContainText('Renamed account');
            await expect(summary).toContainText('1.500,00');
            await page.locator(`#planning-toggle-${account}`).press('Enter');
            await expect(page.locator('#planning-availability > .bank-availability-primary > div').first()).toContainText('500,00');
            await expect(row.locator('[data-account-balance]')).toContainText('1.000,00');
            await expect(row.locator('[data-account-available]')).toContainText('0,00');

            await page.getByRole('link', {name: 'Minimize Everyday bank', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/banking\/$/);
            await expect(page.locator('#bank-workspace-panel')).toHaveCount(0);
            await expect(first).toBeFocused();
            await first.press('Enter');
            await expect(page.locator(`#bank-detail-title-${banks[0]}`)).toBeFocused();
            await page.getByRole('link', {name: 'Minimize Everyday bank', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/banking\/$/);
            await expect(page.locator('#bank-workspace-panel')).toHaveCount(0);
            expect(await page.locator('.bank-workspace-tab').evaluateAll(links => links.map(link => link.id))).toEqual(bankOrder);
            await expectFits(page);
            expect(pageErrors).toEqual([]);
            await page.screenshot({path: info.outputPath(`bank-tabs-${theme}-${width}.png`), fullPage: true});
        });
    }

    test(`visible invoice and currency criteria preserve keyboard GET/error recovery (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {banks} = await seed(page, info);
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/banking/invoices/');
            const form = page.locator('#invoice-filter-form');
            await expect(form.locator('details.filter-disclosure')).toHaveCount(0);
            for (const id of ['invoice-filter-month-trigger', 'invoice-filter-bank-search', 'invoice-filter-status']) {
                await expect(page.locator(`#${id}`)).toBeVisible();
            }
            if (width === 1280) {
                expect((await form.boundingBox()).height).toBeLessThanOrEqual(120);
                const bankBounds = await page.locator('#invoice-filter-bank-search').boundingBox();
                const statusBounds = await page.locator('#invoice-filter-status').boundingBox();
                expect(Math.abs(bankBounds.y + bankBounds.height - statusBounds.y - statusBounds.height)).toBeLessThanOrEqual(1);
                expect(bankBounds.height).toBe(statusBounds.height);
            }
            await selectChoice(page.locator('#invoice-filter-bank'), banks[0]);
            await expect(page).toHaveURL(url => url.searchParams.get('bank') === banks[0]);
            await page.locator('#invoice-filter-status').press('End');
            await expect(page).toHaveURL(url => url.searchParams.get('status') === 'PAID');
            await expect(page.locator('#invoice-filter-status')).toBeFocused();
            await page.locator('#invoice-clear-control a').press('Enter');
            await expect(page).toHaveURL(/\/banking\/invoices\/$/);
            await expect(page.locator('#invoice-filter-q')).toBeFocused();
            await expectFits(page);
            await page.screenshot({path: info.outputPath(`invoice-compact-${theme}-${width}.png`), fullPage: true});

            await page.goto('/banking/exchange-rates/');
            await expect(page.getByText('Example: 1 USD = 5.12 BRL means one US dollar is worth 5.12 Brazilian reais.', {exact: true})).toBeVisible();
            await expect(page.getByLabel('From currency (1 unit)', {exact: true})).toBeVisible();
            await expect(page.getByLabel('To currency', {exact: true})).toBeVisible();
            await page.locator('#rate-filter-from_currency').selectOption('USD');
            await page.locator('#rate-filter-to_currency').selectOption('BRL');
            await expect(page.locator('#rate-results')).toContainText('5,12345678');
            await page.locator('#rate-filter-date_from').fill('03/10/2026');
            await page.locator('#rate-filter-date_from').press('Tab');
            await page.locator('#rate-filter-date_to').fill('01/10/2026');
            await page.locator('#rate-filter-date_to').press('Tab');
            await expect(page.locator('#rate-filter-date_to-error-1')).toBeVisible();
            await expect(page.locator('#rate-filter-date_to')).toHaveValue('01/10/2026');
            await page.locator('#rate-clear-control a').press('Enter');
            await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
            await expect(page.locator('#rate-filter-q')).toBeFocused();
            await expectFits(page);
            await page.screenshot({path: info.outputPath(`rate-compact-${theme}-${width}.png`), fullPage: true});
        }
    });

    test(`bank panel navigation rebases unchanged editors and protects an edited redemption (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {banks, account} = await seed(page, info);
        await post(page, '/banking/loyalty/create/', {name: 'Panel points', bank: banks[0], unit_name: 'points'});
        await page.goto('/banking/loyalty-entries/create/');
        const program = await page.locator('#id_program option').filter({hasText: /^Panel points$/}).getAttribute('value');
        await post(page, '/banking/loyalty-entries/create/', {program, kind: 'ADJUSTMENT', direction: 'CREDIT', amount: '2000', date: '2026-10-17'});
        await post(page, '/banking/rewards/redeem/', {program, points: '1000', target_account: account,
            target_amount: '25', iof_amount: '0', date: '2026-10-17'});

        async function openEditor() {
            await page.goto(`/banking/${banks[0]}/`);
            await page.locator('#bank-activity > summary').press('Enter');
            await page.getByRole('link', {name: 'Edit redemption', exact: true}).press('Enter');
            await expect(page.getByRole('form', {name: 'Edit redemption', exact: true})).toBeVisible();
        }
        await openEditor();
        await page.getByRole('link', {name: 'Minimize Everyday bank', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(page.locator('#departure-confirm')).not.toBeVisible();
        await page.locator(`#bank-${banks[1]}`).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${banks[1]}/$`));
        await expect(page.locator('#departure-confirm')).not.toBeVisible();
        await page.getByRole('link', {name: 'Minimize Savings bank', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(page.locator('#departure-confirm')).not.toBeVisible();

        await openEditor();
        const amount = page.locator('[name="redemption-target_amount"]');
        await amount.fill('30');
        await page.getByRole('link', {name: 'Minimize Everyday bank', exact: true}).press('Enter');
        await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-stay]').press('Enter');
        await expect(amount).toHaveValue('30');
        await expect(page.locator(`#bank-detail-title-${banks[0]}`)).toHaveText('Everyday bank');
        await expect(page.locator('#bank-results')).toHaveCount(0);
        await expect(page.locator('#departure-confirm')).not.toBeVisible();
    });
}

test('inline banking and exposed consultation retain complete native mobile navigation', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 900}});
    try {
        const page = await context.newPage();
        const {banks} = await seed(page, info, true);
        await page.goto('/banking/');
        await page.locator(`#bank-${banks[0]}`).press('Enter');
        await expect(page.locator('#bank-workspace-panel')).toContainText('Everyday bank account');
        await expect(page.locator('#bank-results')).toHaveCount(0);
        await expect(page.locator('#bank-switch-form, #bank-workspace-choice, [data-bank-switch-link]')).toHaveCount(0);
        const minimize = page.getByRole('link', {name: 'Minimize Everyday bank', exact: true});
        await expect(minimize).toHaveText('Minimize');
        await minimize.press('Enter');
        await expect(page.locator('.bank-workspace-tab')).toHaveCount(40);
        await page.locator(`#bank-${banks[1]}`).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${banks[1]}/$`));
        await expect(page.locator('#bank-workspace-panel')).toContainText('Savings bank account');
        await page.getByRole('link', {name: 'Minimize Savings bank', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(page.locator('.bank-workspace-tab')).toHaveCount(40);
        await page.goto('/banking/invoices/');
        await page.locator('#invoice-filter-bank').selectOption(banks[0]);
        await page.locator('#invoice-filter-status').selectOption('PAID');
        await page.locator('#invoice-filter-form').getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('bank') === banks[0] && url.searchParams.get('status') === 'PAID');
        await page.goto('/banking/exchange-rates/');
        await page.locator('#rate-filter-from_currency').selectOption('USD');
        await page.locator('#rate-filter-form').getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expect(page.locator('#rate-results')).toContainText('5,12345678');
        await page.goto('/banking/exchange-rates/create/');
        await expect(page.getByText('Example: 1 USD = 5.12 BRL. Select USD as the source, BRL as the target and enter 5.12 as the value.', {exact: true})).toBeVisible();
        await expect(page.locator('#id_rate')).toHaveAttribute('step', '0.00000001');
        await expectFits(page);
    } finally { await context.close(); }
});
