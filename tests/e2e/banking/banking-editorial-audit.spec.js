// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields = {}) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `bank-audit-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {
        name: 'Editorial institution with a longer name', color: '#315D50',
    });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Everyday checking and household spending',
        currency: 'BRL', opening_date: '2020-01-01', opening_balance: '1000', planning_enabled: 'on'});
    await post(page, '/categories/create/', {name: 'Editorial audit groceries', transaction_type: 'EXPENSE'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Everyday travel and rewards credit card',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28', color: '#5B3E7C'});
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Editorial audit groceries$/}).getAttribute('value');
    await post(page, '/transactions/create/', {transaction_type: 'EXPENSE', title: 'Editorial ledger amount regression',
        amount: '680.00', date: '2026-10-17', category, payment_channel: 'CREDIT_CARD', credit_card: card,
        installments: '1'});
    return {bank};
}

async function expectControl(control, radius) {
    await expect(control).toBeVisible();
    await expect(control).toHaveCSS('border-radius', `${radius}px`);
    expect((await control.boundingBox()).height).toBeGreaterThanOrEqual(44);
}

async function expectDocumentFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        'The actual controls and financial amounts fit the viewport').toBe(true);
}

for (const theme of ['light', 'dark']) {
    test(`banking headings, color controls and native gradient choices match the shared catalogue (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {bank} = await seed(page, info);
        for (const width of [1280, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/banking/');
            await expect(page.locator('main h1')).toHaveCSS('font-size', '24px');
            await expect(page.locator('#banking-workspace > .workspace-header .secondary-actions')).toHaveCount(0);
            const loyalty = page.getByRole('navigation', {name:'Account sections'}).getByRole('link',{name:'Loyalty',exact:true});
            await expect(loyalty).toBeVisible();
            expect((await loyalty.boundingBox()).height).toBeGreaterThanOrEqual(44);

            await page.goto(`/banking/${bank}/`);
            const compact = page.locator('.workspace-header .compact-menu > summary');
            await expectControl(compact, 8);
            await page.goto('/banking/create/');
            const color = page.locator('#id_color');
            await expectControl(color, 8);
            expect((await color.boundingBox()).height).toBe(44);
            await expect(color).toHaveAttribute('type', 'color');

            await page.goto('/banking/debit-cards/create/');
            const checkbox = page.locator('#id_use_gradient');
            const label = page.locator('label[for="id_use_gradient"]');
            const row = page.locator('.entry-checkbox-choice').filter({has: checkbox});
            const boxes = await row.evaluate(element => {
                const input = element.querySelector('input');
                const label = element.querySelector('label');
                const first = input.getBoundingClientRect();
                const second = label.getBoundingClientRect();
                return {gap: second.x - first.right, vertical: Math.abs(second.y + second.height / 2 - first.y - first.height / 2)};
            });
            expect(boxes.gap).toBeGreaterThanOrEqual(8);
            expect(boxes.gap).toBeLessThanOrEqual(16);
            expect(boxes.vertical).toBeLessThan(4);
            await checkbox.press('Space');
            await expect(checkbox).toBeChecked();
            await expect(checkbox).toBeFocused();
            await expect(page.locator('[data-card-gradient-fields]')).toBeVisible();
            await label.click();
            await expect(checkbox).not.toBeChecked();
            await checkbox.press('Space');
            // An invalid native POST must keep the deliberately selected
            // gradient and the native error recovery controls together.
            await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
            await expect(page.locator('#id_name-error-1')).toBeVisible();
            await expect(checkbox).toBeChecked();
            await expect(page.locator('[data-card-gradient-fields]')).toBeVisible();
            await expectDocumentFits(page);
            await page.screenshot({path: info.outputPath(`banking-native-controls-${width}-${theme}.png`), fullPage: true});
        }
    });

    test(`category exports and ledger amounts stay balanced without losing GET navigation (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info);
        for (const width of [1280, 768, 390]) {
            await page.setViewportSize({width, height: 900});
            await page.goto('/categories/');
            const menu = page.locator('.workspace-header .secondary-actions');
            await menu.locator('summary').press('Enter');
            const spreadsheet = menu.getByRole('link', {name: 'Export CSV for spreadsheets', exact: true});
            await expectControl(spreadsheet, 8);
            await expect(spreadsheet).toHaveAttribute('href', '/categories/export/?format=spreadsheet');
            await spreadsheet.focus();
            await page.keyboard.press('Shift+Tab');
            await page.keyboard.press('Tab');
            await expect(spreadsheet).toBeFocused();
            await page.keyboard.press('Escape');

            await page.goto('/transactions/');
            const search = page.locator('#filter-search');
            await search.pressSequentially('Editorial ledger');
            await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Editorial ledger');
            await expect(search).toBeFocused();
            const row = page.locator('#transaction-results li').filter({hasText: 'Editorial ledger amount regression'});
            const amount = row.locator('p.text-lg');
            await expect(amount).toBeVisible();
            await expect(amount).toHaveText('-BRL 680,00');
            expect(await amount.evaluate(element => element.getBoundingClientRect().height <= parseFloat(getComputedStyle(element).lineHeight) + 1),
                'The signed currency and amount remain on one line even with long instrument labels').toBe(true);
            await expectDocumentFits(page);
            const edit = row.getByRole('link', {name: 'Edit', exact: true});
            await edit.press('Enter');
            await expect(page.locator('#id_title')).toHaveValue('Editorial ledger amount regression');
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname === '/transactions/' && url.searchParams.get('q') === 'Editorial ledger');
            await expect(page.locator('#filter-search')).toHaveValue('Editorial ledger');
            await page.screenshot({path: info.outputPath(`ledger-amount-${width}-${theme}.png`), fullPage: true});
        }
    });
}
