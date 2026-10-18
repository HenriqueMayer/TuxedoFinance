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

async function seed(page, info, order = 'DMY') {
    const username = `editorial-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Q8!vM5#rT2@pL9$x', password2: 'Q8!vM5#rT2@pL9$x'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: order});
    await post(page, '/banking/create/', {name: 'Editorial bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Daily account', currency: 'BRL',
        opening_date: '2020-01-01', opening_balance: '1000', pix_enabled: 'on'});
    for (const name of ['Food', 'Books']) {
        await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE'});
    }
    await post(page, '/categories/create/', {name: 'Salary', transaction_type: 'INCOME'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Daily card',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28',
        manual_settlement_from: new Date().toISOString().slice(0, 10)});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    return {account, card, order};
}

function calendar(page) { return page.locator('dialog#date-picker'); }

async function expectCalendarFits(page) {
    const dialog = calendar(page);
    await expect(dialog).toBeVisible();
    expect(await dialog.evaluate(element => {
        const box = element.getBoundingClientRect();
        return element instanceof HTMLDialogElement && element.matches(':modal')
            && box.x >= 0 && box.right <= innerWidth && box.y >= 0 && box.bottom <= innerHeight
            && element.scrollWidth <= element.clientWidth;
    }), 'The date dialog fits the viewport without horizontal clipping').toBe(true);
    await expect(page.locator('dialog[open]')).toHaveCount(1);
}

async function expectDay(page, value) {
    const day = calendar(page).locator(`[data-date="${value}"]`);
    await expect(day).toBeFocused();
    await expect(calendar(page).locator('[data-date][tabindex="0"]')).toHaveCount(1);
    expect(await day.evaluate(element => {
        const style = getComputedStyle(element);
        return element.matches(':focus-visible') && parseFloat(style.outlineWidth) > 0
            && style.outlineStyle !== 'none';
    }), 'Keyboard date navigation keeps a visible focus indicator').toBe(true);
}

for (const theme of ['light', 'dark']) {
    test(`editorial workspace and transaction choices retain errors, transitions and contextual editing (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account, card} = await seed(page, info);
        const navigation = page.getByRole('navigation', {name: 'Main navigation', exact: true});
        await expect(page.locator('.app-sidebar')).toHaveCSS('background-color',
            theme === 'dark' ? 'rgb(38, 38, 38)' : 'rgb(235, 231, 222)');
        await expect(navigation.locator('.app-navigation-label')).toHaveText(['Home', 'Transactions', 'Accounts', 'Investments', 'Plan']);
        await expect(navigation.locator('.app-navigation-number')).toHaveCount(0);
        await expect(navigation.getByRole('link', {name: 'Transactions', exact: true})).toHaveAttribute('aria-current', 'page');
        await expect(navigation.locator('summary, details')).toHaveCount(0);

        const origin = '/transactions/?q=Editorial&month=2026-10';
        await page.goto(origin);
        await page.locator('main .workspace-header').getByRole('link', {name: 'New transaction', exact: true}).press('Enter');
        const form = page.locator('#transaction-entry-form');
        await expect(form).toHaveAttribute('data-transaction-entry', '');
        const type = page.locator('#id_transaction_type');
        const payment = page.locator('#id_payment_channel');
        await expect(type.getByRole('radio', {checked: true})).toHaveCount(0);
        await expect(payment.getByRole('radio', {checked: true})).toHaveCount(0);
        await expect(page.locator('#category-fields')).toBeHidden();
        const firstType = type.getByRole('radio').first();
        await firstType.focus();
        await page.keyboard.press('Space');
        const before = await firstType.inputValue();
        await page.keyboard.press('ArrowRight');
        await expect(type.getByRole('radio', {checked: true})).toHaveCount(1);
        expect(await type.getByRole('radio', {checked: true}).inputValue()).not.toBe(before);
        await selectChoice(type, 'EXPENSE');
        await expect(page.locator('#category-fields')).toBeVisible();
        await page.locator('#id_title').fill('Editorial card purchase');
        await page.locator('#id_amount').fill('42.50');
        await page.locator('#id_date').fill('17/10/2026');
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await selectChoice(payment, 'CREDIT_CARD');
        await expect(page.locator('#credit-card-fields')).toBeVisible();
        await expect(page.locator('#credit-card-details')).toBeHidden();
        await selectChoice(page.locator('#id_credit_card'), card);
        await expect(page.locator('#credit-card-details')).toBeVisible();
        await expect(page.locator('#payment-channel-status')).toContainText('require confirmed payments');
        await page.locator('#id_installments').fill('0');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_installments-error-1')).toBeVisible();
        await expect(page.locator('#id_installments')).toHaveValue('0');
        await expect(type.locator('input[value="EXPENSE"]')).toBeChecked();
        await expect(payment.locator('input[value="CREDIT_CARD"]')).toBeChecked();
        await expect(page.locator('#id_credit_card')).toHaveValue(card);
        await expect(form.locator('[name="next"]')).toHaveValue(origin);

        await selectChoice(type, 'INCOME');
        await expect(payment.locator('input[value="CREDIT_CARD"]')).toBeDisabled();
        await expect(payment.getByRole('radio', {checked: true})).toHaveCount(0);
        await expect(page.locator('#credit-card-fields')).toBeHidden();
        await expect(page.locator('#id_credit_card')).toHaveValue('');
        await expect(page.locator('#id_category')).toHaveValue('');
        await expect(page.locator('#id_installments')).toHaveValue('1');
        await expect(page.locator('#id_installments-error-1')).toHaveCount(0);
        await expect(page.locator('#id_title')).toHaveValue('Editorial card purchase');
        await selectChoice(type, 'EXPENSE');
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await selectChoice(payment, 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), account);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await page.locator('main').getByRole('link', {name: 'Edit', exact: true}).press('Enter');
        await expect(type.locator('input[value="EXPENSE"]')).toBeChecked();
        await expect(payment.locator('input[value="ACCOUNT"]')).toBeChecked();
        await expect(page.locator('#id_bank_account')).toHaveValue(account);
        await expect(form.locator('[name="next"]')).toHaveValue(origin);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    });
}

for (const theme of ['light', 'dark']) {
    test(`owned card appearance persists through keyboard presets, gradient recovery and transaction shortcuts (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account} = await seed(page, info);
        await page.goto('/banking/credit-cards/create/');
        const form = page.locator('[data-card-appearance-form]');
        await selectChoice(page.locator('#id_account'), account);
        await page.locator('#id_name').fill('Editorial plum card');
        await page.locator('#id_card_type').selectOption('PHYSICAL');
        await page.locator('#id_closing_day').fill('20');
        await page.locator('#id_due_day').fill('28');
        const graphite = form.getByRole('radio', {name: 'Graphite', exact: true});
        await expect(graphite).toBeChecked();
        await expect(form.getByRole('checkbox', {name: 'Use a gradient', exact: true})).not.toBeChecked();
        await graphite.focus();
        await page.keyboard.press('Space');
        await page.keyboard.press('ArrowRight');
        await expect(form.getByRole('radio', {name: 'Plum', exact: true})).toBeChecked();
        await expect(form.getByRole('radio', {name: 'Plum', exact: true})).toBeFocused();
        await expect(form.locator('[data-card-preview-name]')).toHaveText('Editorial plum card');
        await expect(form.locator('[data-card-appearance-preview]')).toHaveCSS('--card-start', '#5B3E7C');
        await form.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(/\/credit-cards\/create\/$/);

        // Read the owned identifier from the same scoped record selector that
        // users receive. The fixture never queries the installation database.
        await page.goto('/transactions/create/');
        const card = await page.locator('#id_credit_card option').filter({hasText: /^Editorial plum card -/}).getAttribute('value');
        const editor = `/banking/credit-cards/${card}/edit/`;
        await page.goto(editor);
        await expect(page.locator('#id_color')).toHaveValue('#5b3e7c');
        await expect(page.locator('#id_account')).toHaveValue(account);
        await expect(page.locator('#id_closing_day')).toHaveValue('20');
        await expect(page.locator('#id_due_day')).toHaveValue('28');
        const gradient = page.locator('#id_use_gradient');
        const fields = page.locator('[data-card-gradient-fields]');
        await expect(gradient).not.toBeChecked();
        await expect(fields).toBeHidden();
        await expect(page.locator('#id_gradient_angle')).toBeDisabled();
        await page.locator('#id_color').fill('#315d50');
        await gradient.focus();
        await page.keyboard.press('Space');
        await expect(gradient).toBeChecked();
        await expect(gradient).toBeFocused();
        await expect(fields).toBeVisible();
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_gradient_end')).toBeFocused();
        await page.locator('#id_gradient_end').fill('#c6a173');
        // The dial cannot generate an invalid angle. Forge its retained native
        // POST value to exercise the server's bound-form recovery deliberately.
        await page.locator('#id_gradient_angle').evaluate(input => { input.value = '400'; });
        await form.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_gradient_angle-error-1')).toBeVisible();
        await expect(page.locator('#id_gradient_angle')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_gradient_angle')).toHaveValue('400');
        await expect(page.locator('#id_gradient_end')).toHaveValue('#c6a173');
        await expect(page.locator('#id_color')).toHaveValue('#315d50');
        await expect(page.locator('#id_name')).toHaveValue('Editorial plum card');
        await expect(page.locator('#id_account')).toHaveValue(account);
        await expect(gradient).toBeChecked();
        await expect(fields).toBeVisible();

        await gradient.press('Space');
        await expect(gradient).not.toBeChecked();
        await expect(fields).toBeHidden();
        await expect(page.locator('#id_gradient_angle-error-1')).toHaveCount(0);
        await expect(page.locator('#id_gradient_angle')).not.toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_gradient_angle')).toBeDisabled();
        await gradient.press('Space');
        await expect(fields).toBeVisible();
        await page.locator('#id_gradient_end').fill('#c6a173');
        await page.locator('#id_gradient_angle').fill('45');
        await form.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(url => url.pathname === editor);
        await page.goto(editor);
        await expect(gradient).toBeChecked();
        await expect(fields).toBeVisible();
        await expect(page.locator('#id_color')).toHaveValue('#315d50');
        await expect(page.locator('#id_gradient_end')).toHaveValue('#c6a173');
        await expect(page.locator('#id_gradient_angle')).toHaveValue('45');
        await expect(form.locator('[data-card-appearance-preview]')).toHaveCSS('--card-start', '#315D50');
        await expect(form.locator('[data-card-appearance-preview]')).toHaveCSS('--card-end', '#C6A173');
        await expect(form.locator('[data-card-appearance-preview]')).toHaveCSS('--card-angle', '45deg');
        await page.screenshot({path: info.outputPath('card-appearance-' + theme + '.png'), fullPage: true});

        await page.goto(`/transactions/create/?credit_card=${card}`);
        await expect(page.locator('#id_transaction_type input[value="EXPENSE"]')).toBeChecked();
        await expect(page.locator('#id_payment_channel input[value="CREDIT_CARD"]')).toBeChecked();
        await expect(page.locator('#id_credit_card')).toHaveValue(card);
        const preview = page.locator('[data-entry-card-preview]');
        await expect(preview).toBeVisible();
        await expect(preview.locator('[data-entry-card-name]')).toHaveText('Editorial plum card');
        await expect(preview.locator('[data-entry-card-context]')).toContainText('Daily account');
        await expect(preview.locator('.entry-card-art')).toHaveCSS('background-image',
            'linear-gradient(45deg, rgb(49, 93, 80), rgb(198, 161, 115))');
        await page.screenshot({path: info.outputPath('transaction-appearance-' + theme + '.png'), fullPage: true});
        await selectChoice(page.locator('#id_transaction_type'), 'INCOME');
        await expect(preview).toBeHidden();
        await expect(page.locator('#id_credit_card')).toHaveValue('');
        await expect(page.locator('#id_payment_channel input[value="CREDIT_CARD"]')).not.toBeChecked();
    });
}

for (const [order, theme] of [['DMY', 'light'], ['MDY', 'dark']]) {
    test(`transaction date calendar preserves preferred text, keyboard edits and POST recovery (${order}, ${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info, order);
        await page.clock.setFixedTime('2026-10-17T15:00:00Z');
        const date = page.locator('#id_date');
        const leapEve = order === 'DMY' ? '28/02/2024' : '02/28/2024';
        const leapDay = order === 'DMY' ? '29/02/2024' : '02/29/2024';
        await expect(date).toHaveAttribute('type', 'text');
        await date.fill(leapEve);
        await date.focus();
        await date.press('Tab');
        const trigger = date.locator('xpath=ancestor::*[@data-preferred-date-field]').locator('[data-open-date-picker]');
        await expect(trigger).toBeFocused();
        await expect(calendar(page)).not.toBeVisible();
        await trigger.press('Shift+Tab');
        await expect(date).toBeFocused();
        for (const fraction of [.08, .5, .92]) {
            await date.scrollIntoViewIfNeeded();
            const box = await date.boundingBox();
            await page.mouse.click(box.x + box.width * fraction, box.y + box.height / 2);
            await expectCalendarFits(page);
            await page.keyboard.press('Escape');
            await expect(calendar(page)).not.toBeVisible();
            await expect(date).toBeFocused();
            await expect(date).toHaveValue(leapEve);
        }
        await date.press('Alt+ArrowDown');
        await expectDay(page, '2024-02-28');
        await page.keyboard.press('ArrowRight');
        await expectDay(page, '2024-02-29');
        await expect(date).toHaveValue(leapEve);
        await page.keyboard.press('Enter');
        await expect(calendar(page)).not.toBeVisible();
        await expect(date).toBeFocused();
        await expect(date).toHaveValue(leapDay);
        await expect(page.locator('[data-native-date-picker]').first()).toHaveValue('2024-02-29');
        await expect(page).toHaveURL(/\/transactions\/create\/$/);

        await date.fill(order === 'DMY' ? '31/01/2024' : '01/31/2024');
        await date.press('Alt+ArrowDown');
        await page.keyboard.press('PageDown');
        await expectDay(page, '2024-02-29');
        await page.keyboard.press('Shift+PageDown');
        await expectDay(page, '2025-02-28');
        await page.keyboard.press('Escape');

        // Keep a genuinely invalid bound value untouched; the server owns
        // validation even after the enhanced picker has been initialized.
        const invalid = order === 'DMY' ? '31/02/2026' : '02/31/2026';
        await date.fill(invalid);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(date).toHaveValue(invalid);
        await expect(date).toHaveAttribute('aria-invalid', 'true');
        await date.press('Alt+ArrowDown');
        await expectCalendarFits(page);
        await calendar(page).locator('[data-calendar-action="today"]').press('Enter');
        await expect(date).toHaveValue(order === 'DMY' ? '17/10/2026' : '10/17/2026');
        await date.press('Alt+ArrowDown');
        await calendar(page).locator('[data-calendar-action="clear"]').press('Enter');
        await expect(date).toHaveValue('');
        await expect(date).toBeFocused();
    });
}

for (const [width, theme] of [[320, 'light'], [390, 'dark']]) {
    test(`transaction calendar and final action fit the mobile shell (${width}px, ${theme})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 500});
        await page.emulateMedia({reducedMotion: 'reduce'});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info);
        const date = page.locator('#id_date');
        await date.fill('17/10/2026');
        await date.press('Alt+ArrowDown');
        await expectCalendarFits(page);
        await page.keyboard.press('Escape');
        await expect(date).toBeFocused();
        const save = page.getByRole('button', {name: 'Save', exact: true});
        await save.focus();
        await expect.poll(async () => {
            const box = await save.boundingBox();
            const dock = await page.locator('[data-app-navigation="mobile"]').boundingBox();
            const header = await page.locator('body > header').boundingBox();
            return box.y >= header.y + header.height && box.y + box.height <= dock.y;
        }).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`transaction-mobile-${width}-${theme}.png`), fullPage: true});
    });
}

test('editorial transaction form retains its complete native POST path and contextual return', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 780}});
    try {
        const page = await context.newPage();
        const {account} = await seed(page, info, 'MDY');
        const origin = '/transactions/?q=Native&month=2026-10';
        await page.goto(`/transactions/create/?next=${encodeURIComponent(origin)}`);
        await expect(page.locator('#transaction-entry-form')).toHaveAttribute('autocomplete', 'off');
        await expect(page.locator('#transaction-entry-form')).toHaveAttribute('novalidate', '');
        await expect(page.locator('#id_transaction_type')).toBeVisible();
        await expect(page.locator('#id_payment_channel')).toBeVisible();
        await page.locator('#id_title').fill('Native editorial purchase');
        await page.locator('#id_amount').fill('35.50');
        await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
        await selectChoice(page.locator('#id_category'), {label: 'Food'});
        await selectChoice(page.locator('#id_payment_channel'), 'ACCOUNT');
        await selectChoice(page.locator('#id_bank_account'), account);
        await page.locator('#id_date').fill('02/31/2026');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_date')).toHaveValue('02/31/2026');
        await expect(page.locator('#id_date')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#transaction-entry-form [name="next"]')).toHaveValue(origin);
        await expect(page.locator('#id_bank_account')).toHaveValue(account);
        await page.locator('#id_date').fill('10/17/2026');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await expect(page.locator('main')).toContainText('Native editorial purchase');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally {
        await context.close();
    }
});
