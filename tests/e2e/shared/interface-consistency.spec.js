// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

// These fixtures use the official executor's disposable server/database and the
// same native POST endpoints as the existing form and planning suites.
async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `interface-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: 'Interface bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Interface checking', currency: 'BRL',
        opening_date: '2020-01-01', opening_balance: '1000', pix_enabled: 'on', planning_enabled: 'on'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Interface credit',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28', color: '#5B3E7C',
        use_gradient: 'on', gradient_end: '#C6A173', gradient_angle: '45'});
    await post(page, '/banking/debit-cards/create/', {account, name: 'Interface debit', color: '#315D50'});
    await post(page, '/categories/create/', {name: 'Interface groceries', transaction_type: 'EXPENSE'});
    return {bank};
}

async function expectCompactInput(input) {
    await expect(input).toBeVisible();
    await expect(input).toHaveCSS('border-radius', '8px');
    const dimensions = await input.boundingBox();
    expect(dimensions.height).toBeGreaterThanOrEqual(44);
    expect(dimensions.height).toBeLessThanOrEqual(48);
    expect(await input.evaluate(element => {
        const style = getComputedStyle(element);
        return parseFloat(style.borderTopWidth) === 1 && style.textTransform === 'none';
    })).toBe(true);
}

async function expectBalancedAction(action, radius = 12) {
    await expect(action).toBeVisible();
    await expect(action).toHaveCSS('border-radius', `${radius}px`);
    await expect(action).toHaveCSS('text-transform', 'none');
    await expect(action).toHaveCSS('align-items', 'center');
    await expect(action).toHaveCSS('justify-content', 'center');
    expect((await action.boundingBox()).height).toBeGreaterThanOrEqual(44);
}

async function expectVisibleKeyboardFocus(control) {
    // Navigate away and back with real keyboard events so :focus-visible is
    // tested rather than inferred from a programmatic focus() call alone.
    await control.focus();
    await control.page().keyboard.press('Tab');
    await control.page().keyboard.press('Shift+Tab');
    await expect(control).toBeFocused();
    expect(await control.evaluate(element => {
        const style = getComputedStyle(element);
        return element.matches(':focus-visible') && style.outlineStyle !== 'none'
            && parseFloat(style.outlineWidth) >= 2;
    }), 'The compact field keeps a visible keyboard focus indicator').toBe(true);
}


for (const theme of ['light', 'dark']) {
    test(`shared editorial controls stay compact, balanced and usable across workspaces (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.emulateMedia({reducedMotion: 'reduce'});
        await seed(page, info);
        const pages = [
            ['/banking/accounts/create/', '#id_name'],
            ['/categories/create/', '#id_name'],
            ['/investments/add/', '#id_name'],
            ['/planning/goals/create/', '#id_name'],
            ['/sandbox/simulation/', '#id_rate'],
        ];
        for (const width of [1440, 390]) {
            await page.setViewportSize({width, height: 900});
            for (const [path, field] of pages) {
                await test.step(`${path} at ${width}px`, async () => {
                    await page.goto(path);
                    await expect(page.locator('body')).toHaveClass(/\btuxedo-ui\b/);
                    await expect(page.locator('main .surface-panel').first()).toHaveCSS('border-radius', '14px');
                    const input = page.locator(field);
                    await expectCompactInput(input);
                    await expectVisibleKeyboardFocus(input);
                    if (path === '/banking/accounts/create/') {
                        const checkboxStates = [];
                        for (const id of ['id_pix_enabled', 'id_planning_enabled']) {
                            const checkbox = page.locator(`#${id}`);
                            const label = page.locator(`label[for="${id}"]`);
                            const row = page.locator('.entry-checkbox-choice').filter({has: checkbox});
                            await expect(row).toHaveCount(1);
                            const controlBox = await checkbox.boundingBox();
                            const labelBox = await label.boundingBox();
                            expect(controlBox.width).toBeGreaterThanOrEqual(16);
                            expect(controlBox.width).toBeLessThanOrEqual(24);
                            expect(controlBox.height).toBeGreaterThanOrEqual(16);
                            expect(controlBox.height).toBeLessThanOrEqual(24);
                            expect(labelBox.x).toBeGreaterThan(controlBox.x + controlBox.width);
                            expect(Math.abs(controlBox.y + controlBox.height / 2
                                - labelBox.y - labelBox.height / 2)).toBeLessThan(4);
                            expect((await row.boundingBox()).height).toBeGreaterThanOrEqual(44);
                            const initial = await checkbox.isChecked();
                            await checkbox.press('Space');
                            await expect(checkbox).toBeFocused();
                            await expect(checkbox).toBeChecked({checked: !initial});
                            checkboxStates.push([id, !initial]);
                        }
                        // Submit an incomplete native POST so both checked and
                        // unchecked values must survive rendered Django errors.
                        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
                        await expect(page.locator('#id_name-error-1')).toBeVisible();
                        for (const [id, checked] of checkboxStates) {
                            await expect(page.locator(`#${id}`)).toBeChecked({checked});
                        }
                        // Resume the cross-workspace geometry checks on a fresh
                        // authorized GET, without saving a fixture account here.
                        await page.goto(path);
                    }
                    const calendarField = path === '/banking/accounts/create/' ? '#id_opening_date'
                        : path === '/planning/goals/create/' ? '#id_target_date' : null;
                    if (calendarField) {
                        const date = page.locator(calendarField);
                        await expect(date).toHaveAttribute('data-calendar-enhanced', 'true');
                        // The text area of the date rail opens the shared dialog,
                        // not merely its small icon. Escape never commits a date.
                        await date.click({position: {x: 16, y: 20}});
                        const dialog = page.locator('dialog#date-picker');
                        await expect(dialog).toBeVisible();
                        expect(await dialog.evaluate(element => element.matches(':modal'))).toBe(true);
                        await page.keyboard.press('Escape');
                        await expect(dialog).not.toBeVisible();
                        await expect(date).toBeFocused();
                        await expect(date).toHaveValue('');
                    }
                    const primary = page.locator('main form .action-primary:visible').first();
                    await expectBalancedAction(primary);
                    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
                        `${path} fits the document without horizontal clipping`).toBe(true);
                    if (path === '/banking/accounts/create/') {
                        await page.screenshot({path: info.outputPath(`interface-form-${width}-${theme}.png`), fullPage: true});
                    }
                    if (width === 1440) {
                        const before = await primary.boundingBox();
                        await primary.hover();
                        expect((await primary.boundingBox()).width).toBeCloseTo(before.width, 1);
                        await expect(primary).toHaveCSS('border-radius', '12px');
                    }
                });
            }
        }
    });

    test(`account and invoice miniatures preserve identity while category filters keep native keyboard choices (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width: 1440, height: 900});
        const {bank} = await seed(page, info);
        await page.goto(`/banking/${bank}/`);
        const bankPanel = page.getByRole('region', {name: 'Interface bank', exact: true});
        await expect(bankPanel.getByRole('heading', {name: 'Interface bank', exact: true})).toBeVisible();
        // The open bank owns its identity in the internal window title bar.
        const marker = bankPanel.locator('.bank-workspace-windowtitle .bank-marker');
        await expect(marker).toHaveCount(1);
        await expect(marker).toHaveAttribute('aria-hidden', 'true');
        await expect(marker).toHaveCSS('background-color', 'rgb(49, 93, 80)');
        const credit = page.locator('.credit-card-row').filter({hasText: 'Interface credit'});
        await expect(credit.locator('.card-miniature')).toHaveCSS('background-image',
            'linear-gradient(45deg, rgb(91, 62, 124), rgb(198, 161, 115))');
        await expect(credit.locator('.card-miniature')).toHaveAttribute('aria-hidden', 'true');
        await expect(credit.getByText('Interface credit', {exact: true})).toBeVisible();
        await page.locator('.account-configuration > summary').press('Enter');
        const debit = page.locator('.account-configuration li').filter({hasText: 'Interface debit'});
        await expect(debit.locator('.card-miniature')).toHaveCSS('--card-start', '#315D50');
        await expect(debit.getByRole('link', {name: 'Edit', exact: true})).toBeVisible();
        await page.screenshot({path: info.outputPath(`interface-accounts-${theme}.png`), fullPage: true});
        await page.goto('/banking/invoices/');
        const invoice = page.locator('.invoice-card').filter({hasText: 'Interface credit'});
        await expect(invoice.locator('.card-miniature')).toHaveCSS('background-image',
            'linear-gradient(45deg, rgb(91, 62, 124), rgb(198, 161, 115))');
        await expect(invoice).toContainText('Interface bank');
        await expect(invoice).toContainText('Interface checking');
        await expect(invoice).toHaveAttribute('href', /\/banking\/credit-cards\/\d+\/invoices\//);

        await page.setViewportSize({width: 390, height: 900});
        await page.goto('/categories/');
        await expect(page.locator('#category-filters details.filter-disclosure')).toHaveCount(0);
        const level = page.locator('#filter-level-all');
        await level.focus();
        await page.keyboard.press('Space');
        await page.keyboard.press('ArrowRight');
        await expect(page).toHaveURL(url => url.searchParams.get('level') === 'top');
        await expect(page.locator('#filter-level-top')).toBeChecked();
        await expect(page.locator('#filter-level-top')).toBeFocused();
        await page.locator('#filter-type-all').focus();
        await page.keyboard.press('ArrowRight');
        await page.keyboard.press('ArrowRight');
        await expect(page).toHaveURL(url => url.searchParams.get('type') === 'EXPENSE');
        await expect(page.locator('#filter-type-expense')).toBeChecked();
        await expect(page.locator('#filter-type-expense')).toBeFocused();
        await page.locator('#filter-search').pressSequentially('Interface');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Interface');
        await expect(page.locator('#category-results')).toContainText('Interface groceries');
        await expectBalancedAction(page.locator('#category-clear-filters'), 8);
        for (const width of [390, 320]) {
            await page.setViewportSize({width, height: 900});
            for (const label of await page.locator('#category-filters .entry-segment-options label').all()) {
                const box = await label.boundingBox();
                expect(box.height).toBeGreaterThanOrEqual(44);
                expect(box.x).toBeGreaterThanOrEqual(0);
                expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        await page.locator('#category-filters').screenshot({path: info.outputPath(`interface-category-filters-${theme}.png`)});
        await page.locator('#category-clear-filters').press('Enter');
        await expect(page.locator('#filter-level-all')).toBeChecked();
        await expect(page.locator('#filter-type-all')).toBeChecked();
        await expect(page.locator('#filter-search')).toBeFocused();
    });

    test(`shared field styling preserves rates, durations and eight-decimal investment error recovery (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {bank} = await seed(page, info);
        await page.goto('/sandbox/simulation/');
        await page.locator('#id_rate').fill('1.25');
        await page.locator('#id_months').fill('24');
        await page.locator('#id_rate').press('Tab');
        await expect(page.locator('#id_rate')).toHaveValue('1.25');
        await expect(page.locator('#id_months')).toHaveValue('24');
        await expect(page.locator('#id_rate')).not.toHaveAttribute('data-money-input');
        await expect(page.locator('#id_months')).not.toHaveAttribute('data-money-input');
        // Deliberate navigation leaves this unsaved simulation, without writing
        // a draft. Existing departure protection remains active and is accepted.
        page.once('dialog', dialog => dialog.accept());
        await page.goto('/investments/add/');
        await selectChoice(page.locator('#id_institution'), bank);
        await page.locator('#id_name').fill('Precision holding');
        await page.locator('#id_valuation_mode').selectOption('UNITS');
        const quantity = page.locator('#id_opening_quantity');
        const price = page.locator('#id_opening_unit_price');
        await quantity.pressSequentially('1234.56789012');
        await price.pressSequentially('0.12345678');
        await price.press('Tab');
        await expect(quantity).toHaveValue('1234.56789012');
        await expect(price).toHaveValue('0.12345678');
        await expectCompactInput(quantity);
        await expectCompactInput(price);
        // A missing opening date exercises the rendered Django error path;
        // presentation changes must not round units or discard the POST values.
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_opening_date-error-1')).toBeVisible();
        await expect(quantity).toHaveValue('1234.56789012');
        await expect(price).toHaveValue('0.12345678');
        await expect(page.locator('#id_valuation_mode')).toHaveValue('UNITS');
        await expect(page.locator('#id_name')).toHaveValue('Precision holding');
        await expectBalancedAction(page.getByRole('button', {name: 'Save', exact: true}));
    });
}


test('shared date appearance retains complete preferred-text POSTs without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        viewport: {width: 390, height: 900}});
    const page = await context.newPage();
    try {
        const {bank} = await seed(page, info);
        await page.goto('/banking/accounts/create/');
        await page.locator('#id_bank').selectOption(bank);
        await page.locator('#id_name').fill('Native date checking');
        await page.locator('#id_currency').selectOption('BRL');
        await page.locator('#id_opening_balance').fill('100.50');
        const date = page.locator('#id_opening_date');
        await expect(date).toHaveAttribute('type', 'text');
        await date.pressSequentially('17/10/2026');
        await expect(page.locator('dialog#date-picker')).toHaveCount(0);
        await expect(page.locator('[data-open-date-picker]')).toBeHidden();
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${bank}/`));
        const account = page.locator('.bank-account-card').filter({hasText: 'Native date checking'});
        await expect(account).toBeVisible();
        const id = (await account.getAttribute('id')).replace('account-row-', '');
        await page.goto(`/banking/accounts/${id}/edit/`);
        await expect(page.locator('#id_opening_date')).toHaveValue('17/10/2026');
        expect(Number(await page.locator('#id_opening_balance').inputValue())).toBe(100.5);
        await expectBalancedAction(page.getByRole('button', {name: 'Save', exact: true}));
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally {
        await context.close();
    }
});
