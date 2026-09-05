// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function postForm(page, path, fields) {
    const response = await page.request.get(path === '/i18n/setlang/' ? '/transactions/' : path);
    const html = await response.text();
    const csrf = html.match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), (await saved.text()).match(/<ul class="errorlist[^>]*>[\s\S]*?<\/ul>/g)?.join(' ') || path).toBe(302);
}

async function prepare(page, testInfo) {
    const username = `txn-${testInfo.workerIndex}-${Date.now()}`;
    await postForm(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    await postForm(page, '/banking/create/', { name: 'Navigation bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await postForm(page, '/banking/accounts/create/', {
        bank, name: 'Daily', currency: 'BRL', opening_balance: '1000', pix_enabled: 'on',
    });
    await postForm(page, '/categories/create/', { name: 'Navigation subscriptions', transaction_type: 'EXPENSE' });
    await postForm(page, '/categories/create/', { name: 'Pay', transaction_type: 'INCOME' });
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({ hasText: /^Navigation subscriptions$/ }).getAttribute('value');
    const salaryCategory = await page.locator('#id_category option').filter({ hasText: /^Pay$/ }).getAttribute('value');
    const defaults = { amount: '120', transaction_type: 'EXPENSE', category,
        payment_channel: 'ACCOUNT', bank_account: account, date: '15/01/2026', installments: '1' };
    await postForm(page, '/transactions/create/', {
        ...defaults, title: 'Monthly subscription', is_fixed: 'on', fixed_until: '28/02/2026',
    });
    await postForm(page, '/transactions/create/', { ...defaults, title: 'One purchase' });
    await postForm(page, '/transactions/create/', {
        ...defaults, title: 'Salary', transaction_type: 'INCOME', category: salaryCategory,
    });
    await page.goto('/transactions/');
    return category;
}

function typeCards(page) { return page.locator('nav[aria-describedby="type-count-help"]'); }

async function assertFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const cards = await typeCards(page).getByRole('link').all();
    const boxes = await Promise.all(cards.map(card => card.boundingBox()));
    expect(Math.max(...boxes.map(box => box.height))).toBeLessThanOrEqual(48);
    expect(Math.max(...boxes.map(box => box.y)) - Math.min(...boxes.map(box => box.y))).toBeLessThanOrEqual(1);

    const apply = page.locator('#transaction-filters button[type="submit"]');
    const category = page.locator('#filter-category');
    const a = await apply.boundingBox();
    const b = await category.boundingBox();
    expect(a.y >= b.y + b.height - 1 || a.x >= b.x + b.width - 1).toBe(true);
}

test('transaction navigation preserves GET state, keyboard selection and browser history', async ({ page }, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const category = await prepare(page, testInfo);
    await expect(typeCards(page).getByRole('link', { name: /^All/ })).toContainText('3');
    const expenses = typeCards(page).getByRole('link', { name: /^Expenses/ });
    await expenses.focus();
    await page.keyboard.press('Enter');
    await expect(expenses).toHaveAttribute('aria-current', 'true');
    await page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ }).click();
    await expect(page.getByRole('status')).toHaveText('1 transaction');
    await page.locator('#filter-category').selectOption(category);
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await expect(page).toHaveURL(new RegExp(`category=${category}`));
    await typeCards(page).getByRole('link', { name: /^Income/ }).click();
    await expect(page).not.toHaveURL(/category=/);
    await expect(page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByText('Installments')).toHaveCount(0);
    await expect(page.getByText('No matching transactions')).toBeVisible();
    await page.goBack();
    await expect(page.locator('#filter-category')).toHaveValue(category);
    await expect(page.getByRole('status')).toHaveText('1 transaction');
    await page.locator('#filter-month').fill('2026-02');
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await expect(typeCards(page).getByRole('link', { name: /^All/ })).toContainText('1');
    await page.getByText('More filters', { exact: true }).click();
    await page.locator('#filter-date').fill('2026-01-15');
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await expect(page.locator('#filter-date')).toBeVisible();
    await page.locator('#filter-sort').selectOption('oldest');
    await page.getByRole('button', { name: 'Sort', exact: true }).click();
    await expect(page).toHaveURL(/recurrence=fixed/);
    await expect(page).toHaveURL(/date=2026-01-15/);
    await expect(page.locator('#filter-category')).toHaveValue(category);
    await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.getByRole('status')).toHaveText('3 transactions');
    expect(errors).toEqual([]);
});

for (const theme of ['light', 'dark']) {
    for (const mobile of [false, true]) {
        test(`transaction layout ${theme} ${mobile ? 'mobile PT-BR' : 'desktop EN'}`, async ({ page }, testInfo) => {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await prepare(page, testInfo);
            if (mobile) {
                await postForm(page, '/i18n/setlang/', { language: 'pt-br', next: '/transactions/' });
                await page.setViewportSize({ width: 390, height: 844 });
                await page.reload();
            }
            await expect(page.getByRole('heading', { level: 1 })).toHaveText(mobile ? 'Transações' : 'Transactions');
            await expect(typeCards(page).getByRole('link').nth(1)).toContainText(mobile ? 'Receitas' : 'Income');
            await expect(page.locator('#filter-date')).toBeHidden();
            await assertFits(page);
            await page.screenshot({ path: testInfo.outputPath('transactions.png'), fullPage: true });
        });
    }
}

test('transaction filtering works without JavaScript on mobile', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    try {
        await prepare(page, testInfo);
        await typeCards(page).getByRole('link', { name: /^Expenses/ }).click();
        await page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ }).click();
        await page.locator('#filter-month').fill('2026-03');
        await page.getByRole('button', { name: 'Apply filters' }).click();
        await expect(page.getByText('No matching transactions')).toBeVisible();
        await page.getByRole('link', { name: 'Clear filters', exact: true }).first().click();
        await expect(page.getByRole('status')).toHaveText('3 transactions');
        await assertFits(page);
    } finally {
        await context.close();
    }
});

for (const width of [390, 1280]) {
test(`transaction updates retain viewport and focus at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 650 });
    await prepare(page, testInfo);

    async function keepsPosition(control, remainsVisible = true) {
        await control.scrollIntoViewIfNeeded();
        await control.evaluate(element => element.focus({ preventScroll: true }));
        const before = await page.evaluate(() => window.scrollY);
        expect(before).toBeGreaterThan(50);
        await control.click();
        await expect(page.locator('body')).not.toHaveClass(/htmx-(request|settling|swapping)/);
        await expect(page.locator('body')).not.toHaveAttribute('aria-busy', 'true');
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const { after, maximum } = await page.evaluate(() => ({
            after: window.scrollY, maximum: document.documentElement.scrollHeight - innerHeight,
        }));
        expect(Math.abs(after - Math.min(before, maximum))).toBeLessThanOrEqual(2);
        if (remainsVisible) await expect(control).toBeFocused();
        else await expect(page.getByRole('heading', { level: 1 })).not.toBeFocused();
    }

    // Set an actual scroll offset even when the first control is already visible.
    await page.evaluate(() => window.scrollTo(0, 240));
    await keepsPosition(typeCards(page).getByRole('link', { name: /^Expenses/ }));
    await expect(page.getByRole('status')).toHaveText('2 transactions');
    await keepsPosition(page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ }));
    await keepsPosition(page.getByRole('button', { name: 'Apply filters' }));
    await page.locator('#filter-sort').selectOption('oldest');
    await keepsPosition(page.getByRole('button', { name: 'Sort', exact: true }));
    await keepsPosition(page.getByRole('link', { name: 'Clear filters', exact: true }), false);
    await expect(page.getByRole('status')).toHaveText('3 transactions');
    await page.locator('#filter-search').fill('No matching record');
    await keepsPosition(page.getByRole('button', { name: 'Apply filters' }));
    await expect(page.getByText('No matching transactions')).toBeVisible();

    // Deliberate navigation to another page still starts at that destination.
    await page.getByRole('link', { name: 'New Transaction', exact: true })
        .evaluate(element => element.focus({ preventScroll: true }));
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});
}
