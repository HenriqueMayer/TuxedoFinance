// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: token, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(result.status(), (await result.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
    return result;
}

async function fixture(page, info) {
    const username = `loyalty-art-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Cedar rewards bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: 'Cedar rewards bank'}).getAttribute('value');
    const longAccount = 'Travel reserves ' + 'A'.repeat(70);
    for (const name of ['Daily account', longAccount]) {
        await post(page, '/banking/accounts/create/', {bank, name, currency: 'BRL',
            opening_date: '2020-01-01', opening_balance: '5000', pix_enabled: 'on'});
    }
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').filter({hasText: 'Daily account'}).getAttribute('value');
    const otherAccount = await page.locator('#id_account option').filter({hasText: longAccount}).getAttribute('value');
    const cardNames = ['Daily credit', 'Travel credit ' + 'C'.repeat(72)];
    for (const [index, name] of cardNames.entries()) {
        await post(page, '/banking/credit-cards/create/', {account: index ? otherAccount : account, name,
            color: index ? '#5B3E7C' : '#253330', use_gradient: index ? 'on' : '',
            gradient_end: '#C6A173', gradient_angle: '45', card_type: 'PHYSICAL', closing_day: '20', due_day: '28'});
    }
    await page.goto('/transactions/create/');
    const cards = await page.locator('#id_credit_card option').evaluateAll(options => options.filter(o => o.value).map(o => o.value));
    await post(page, '/categories/create/', {name: 'Loyalty review purchase', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const category = await page.locator('#id_category option').filter({hasText: /^Loyalty review purchase$/}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    await post(page, '/transactions/create/', {title: 'Loyalty review invoice', amount: '10.25', transaction_type: 'EXPENSE',
        category, payment_channel: 'CREDIT_CARD', credit_card: cards[0], date: today, installments: '1'});
    await post(page, '/banking/loyalty/create/', {bank, name: 'Travel points', unit_name: 'Miles'});
    await page.goto('/banking/loyalty-entries/create/');
    const program = await page.locator('#id_program option').filter({hasText: 'Travel points'}).getAttribute('value');
    const invoice = await page.locator('#id_invoice option').filter({hasText: 'Daily credit'}).last().getAttribute('value');
    await post(page, '/banking/loyalty-entries/create/', {program, direction: 'CREDIT', kind: 'ADJUSTMENT', amount: '10000.25', date: today});
    return {bank, account, otherAccount, cards, cardNames, program, today, invoice};
}

async function capture(page, info, name, target) {
    if (target) await target.scrollIntoViewIfNeeded();
    await page.screenshot({path: info.outputPath(name)});
}

for (const theme of ['light', 'dark']) {
    test(`shared loyalty miniatures preserve keyboard, errors and conditional sources (${theme})`, async ({page}, info) => {
        test.setTimeout(120000);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await fixture(page, info);
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/transactions/create/');
            await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
            await selectChoice(page.locator('#id_payment_channel'), 'CREDIT_CARD');
            await capture(page, info, `01-reference-cards-${theme}-${width}.png`, page.locator('#id_credit_card-search'));
            await page.goto(`/banking/loyalty/create/?bank=${data.bank}`);
            await page.locator('#id_cards-search').focus();
            const cardPicker = page.locator('#id_cards + .search-choice');
            await expect(cardPicker).toHaveClass(/search-choice--payment/);
            await expect(cardPicker.locator('.payment-choice-art')).toHaveCount(2);
            await expect(cardPicker.locator('.payment-choice-art').last()).toHaveCSS('background-image', 'linear-gradient(45deg, rgb(91, 62, 124), rgb(198, 161, 115))');
            await capture(page, info, `02-program-cards-${theme}-${width}.png`, page.locator('#id_cards-search'));
            const multiSearch = page.locator('#id_cards-search');
            for (const cardName of data.cardNames) {
                await multiSearch.fill(cardName);
                await multiSearch.press('Tab');
                const checkbox = cardPicker.getByRole('checkbox').first();
                await expect(checkbox).toBeFocused();
                await page.keyboard.press('Space');
                await expect(checkbox).toBeChecked();
                await expect(checkbox).toBeFocused();
            }
            await multiSearch.fill('');
            await expect(cardPicker.getByRole('checkbox', {checked: true})).toHaveCount(2);
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_name-error-1')).toBeVisible();
            await expect(page.locator('#id_cards + .search-choice').getByRole('checkbox', {checked: true})).toHaveCount(2);
            await page.locator('#id_name').fill(`Reviewed cards ${width}`);
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page).not.toHaveURL(/loyalty\/create/);
            await page.waitForLoadState('load');
            await page.goto(`/banking/loyalty-entries/create/?program=${data.program}`);
            await expect(page.locator('#id_funding_credit_card-search')).toBeHidden();
            await page.locator('#id_kind').selectOption('PURCHASE');
            await page.locator('#id_funding_credit_card-search').focus();
            const fundedCards = page.locator('#id_funding_credit_card + .search-choice');
            const fundedAccounts = page.locator('#id_funding_account + .search-choice');
            await expect(fundedCards.locator('.payment-choice-art[data-choice-kind="card"]')).toHaveCount(2);
            await expect(fundedAccounts.locator('.payment-choice-art[data-choice-kind="account"]')).toHaveCount(2);
            await expect(page.locator('#id_cash_amount')).toBeHidden();
            await selectChoice(page.locator('#id_funding_credit_card'), data.cards[0]);
            await expect(fundedCards.getByRole('option', {selected: true})).toHaveCount(1);
            await expect(page.locator('#id_cash_amount')).toBeVisible();
            await capture(page, info, `03-purchase-card-${theme}-${width}.png`, page.locator('#id_funding_credit_card-search'));
            await selectChoice(page.locator('#id_funding_account'), data.account);
            await expect(page.locator('#id_funding_credit_card')).toHaveValue('');
            await expect(fundedCards.getByRole('option', {selected: true})).toHaveCount(0);
            await expect(fundedAccounts.getByRole('option', {selected: true})).toHaveCount(1);
            await page.locator('#id_direction').selectOption('CREDIT');
            await page.locator('#id_amount').fill('1234.56');
            await page.locator('#id_cash_amount').fill('-1');
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_cash_amount-error-1')).toBeVisible();
            await expect(page.locator('#id_funding_account')).toHaveValue(data.account);
            await expect(page.locator('#id_funding_account + .search-choice').getByRole('option', {selected: true})).toHaveCount(1);
            await expect(page.locator('#id_amount')).toHaveValue('1234.56');
            await page.locator('#id_kind').selectOption('ADJUSTMENT');
            await expect(page.locator('#id_funding_account-search')).toBeHidden();
            await expect(page.locator('#id_funding_account')).toHaveValue('');
            await expect(page.locator('#id_cash_amount')).toHaveValue('');
            await page.locator('#id_kind').selectOption('INVOICE_AWARD');
            await expect(page.locator('#id_funding_credit_card-search')).toBeHidden();
            await selectChoice(page.locator('#id_invoice'), data.invoice);
            const invoiceChoice = page.locator('#id_invoice + .search-choice').getByRole('option', {selected: true});
            await expect(invoiceChoice.locator('.payment-choice-art[data-choice-kind="card"]')).toBeVisible();
            await expect(invoiceChoice).toHaveAttribute('aria-label', /Daily credit.*Cedar rewards bank.*\d{4}-\d{2}/);
            await capture(page, info, `05-invoice-award-${theme}-${width}.png`, page.locator('#id_invoice-search'));
            await page.goto(`/banking/rewards/redeem/?program=${data.program}`);
            await page.locator('#id_iof_amount').fill('1.25');
            await page.locator('#id_iof_credit_card-search').focus();
            const iofCards = page.locator('#id_iof_credit_card + .search-choice');
            await expect(iofCards.locator('.payment-choice-art[data-choice-kind="card"]')).toHaveCount(2);
            await selectChoice(page.locator('#id_iof_credit_card'), data.cards[1]);
            await selectChoice(page.locator('#id_iof_account'), data.account);
            await expect(page.locator('#id_iof_credit_card')).toHaveValue('');
            await expect(iofCards.getByRole('option', {selected: true})).toHaveCount(0);
            await selectChoice(page.locator('#id_iof_credit_card'), data.cards[1]);
            await expect(page.locator('#id_iof_account')).toHaveValue('');
            await page.locator('#id_iof_credit_card-search').fill('Daily');
            await page.locator('#id_notes').focus();
            await expect(iofCards.getByRole('option')).toHaveCount(1);
            await expect(page.locator('#id_iof_credit_card-search')).toHaveValue('Daily');
            await page.locator('#id_iof_credit_card-search').press('Escape');
            await expect(iofCards.getByRole('option')).toHaveCount(2);
            await expect(page.locator('#id_iof_credit_card')).toHaveValue(data.cards[1]);
            await capture(page, info, `04-redemption-card-${theme}-${width}.png`, page.locator('#id_iof_credit_card-search'));
            await expect(page.locator('#id_iof_credit_card-search')).toBeFocused();
            const bounds = await iofCards.getByRole('option').first().boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
            expect(bounds.height).toBeGreaterThanOrEqual(44);
            expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
            await page.locator('#id_iof_amount').fill('0');
            await expect(page.locator('#id_iof_credit_card-search')).toBeHidden();
            await expect(page.locator('#id_iof_credit_card')).toHaveValue('');
        }
        await expect(page.locator('#id_points')).not.toHaveAttribute('data-money-input');
    });
}

test('loyalty multi-selection, purchase and redemption remain complete without JavaScript', async ({page, browser}, info) => {
    test.setTimeout(90000);
    const data = await fixture(page, info);
    const context = await browser.newContext({storageState: await page.context().storageState(), javaScriptEnabled: false,
        viewport: {width: 390, height: 844}});
    try {
        const native = await context.newPage();
        await native.goto(`/banking/loyalty/create/?bank=${data.bank}`);
        await native.locator('#id_cards').selectOption(data.cards);
        await native.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native.locator('#id_name-error-1')).toBeVisible();
        expect(await native.locator('#id_cards').evaluate(select => [...select.selectedOptions].map(o => o.value))).toEqual(data.cards);
        await native.locator('#id_name').fill('Native multi-card points');
        await native.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native).not.toHaveURL(/loyalty\/create/);
        await native.waitForLoadState('load');

        await native.goto(`/banking/loyalty-entries/create/?program=${data.program}`);
        await native.locator('#id_kind').selectOption('PURCHASE');
        await native.locator('#id_direction').selectOption('CREDIT');
        await native.locator('#id_amount').fill('123.45');
        await native.locator('#id_funding_account').selectOption(data.account);
        await native.locator('#id_cash_amount').fill('-1');
        await native.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native.locator('#id_cash_amount-error-1')).toBeVisible();
        await expect(native.locator('#id_funding_account')).toHaveValue(data.account);
        await expect(native.locator('#id_amount')).toHaveValue('123.45');
        await native.locator('#id_cash_amount').fill('25.10');
        await native.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native).toHaveURL(/\/banking\/$/);
        await native.waitForLoadState('load');
        await native.goto(`/banking/rewards/redeem/?program=${data.program}`);
        await native.locator('#id_points').fill('100.25');
        await native.locator('#id_target_account').selectOption(data.account);
        await native.locator('#id_target_amount').fill('12.34');
        await native.locator('#id_iof_amount').fill('1.25');
        await native.locator('#id_iof_credit_card').selectOption(data.cards[1]);
        await native.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native).toHaveURL(new RegExp(`/banking/${data.bank}/#reward-redemptions$`));
        await native.waitForLoadState('load');
        const edit = native.getByRole('link', {name: 'Edit redemption', exact: true});
        await edit.focus();
        await expect(edit).toBeFocused();
        await native.keyboard.press('Enter');
        await expect(native.locator('#id_redemption-iof_credit_card')).toHaveValue(data.cards[1]);
        await expect(native.locator('#id_redemption-points')).toHaveValue('100.25');
        await capture(native, info, '06-native-inline-redemption-390.png', native.locator('#id_redemption-iof_credit_card'));
    } finally { await context.close(); }
});

for (const theme of ['light', 'dark']) {
    test(`multiple card selection keeps complete long record names inside the form (${theme})`, async ({page}, info) => {
        test.setTimeout(60000);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await fixture(page, info);
        const observations = [];
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto(`/banking/loyalty/create/?bank=${data.bank}`);
            const search = page.locator('#id_cards-search');
            const board = page.locator('#id_cards + .search-choice');
            for (const cardName of data.cardNames) {
                await search.fill(cardName);
                await search.press('Tab');
                await page.keyboard.press('Space');
            }
            await search.fill('');
            await expect(board.getByRole('checkbox', {checked: true})).toHaveCount(2);
            observations.push(await board.evaluate(element => ({
                viewport: innerWidth, document: document.documentElement.scrollWidth,
                status: element.querySelector('[aria-live]').getBoundingClientRect().toJSON(),
            })));
            await capture(page, info, `07-program-selected-long-${theme}-${width}.png`, search);
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_name-error-1')).toBeVisible();
            await expect(page.locator('#id_cards + .search-choice').getByRole('checkbox', {checked: true})).toHaveCount(2);
            await expect(page.locator('#id_cards')).toHaveValues(data.cards);
            observations.push(await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, bound: true})));
            await capture(page, info, `08-program-bound-long-${theme}-${width}.png`, page.locator('#id_cards-search'));
        }
        await require('node:fs/promises').writeFile(info.outputPath('07-geometry.json'), JSON.stringify(observations, null, 2));
        for (const observation of observations) expect(observation.document).toBe(observation.viewport);
    });
    }
