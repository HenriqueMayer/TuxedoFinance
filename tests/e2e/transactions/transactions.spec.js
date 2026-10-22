// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { selectChoice } = require('../helpers/forms');
const { test, expect, chromium } = require('@playwright/test');
const { writeFile } = require('node:fs/promises');
const { requestPath, expectContextualDestination } = require('../helpers/navigation');

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

async function prepare(page, testInfo, extraExpenses = 0) {
    const username = `txn-${testInfo.workerIndex}-${Date.now()}`;
    await postForm(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    await postForm(page, '/banking/create/', { name: 'Navigation bank' });
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await postForm(page, '/banking/accounts/create/', {
        bank, name: 'Daily', currency: 'BRL', opening_date: '2025-01-01', opening_balance: '1000', pix_enabled: 'on',
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
    for (let index = 0; index < extraExpenses; index++) {
        await postForm(page, '/transactions/create/', { ...defaults, title: `Stable expense ${index + 1}` });
    }
    await page.goto('/transactions/');
    return category;
}

function typeCards(page) { return page.locator('nav[aria-describedby="type-count-help"]'); }

async function openFilters(page) {
    const disclosure = page.locator('#transaction-extra-filters');
    if (!await disclosure.evaluate(element => element.open)) {
        await disclosure.locator('summary').focus();
        await page.keyboard.press('Enter');
    }
    await expect(disclosure).toHaveAttribute('open', '');
}

async function chooseBilledMonth(page, value) {
    const canonical = page.locator('#filter-month');
    if (await canonical.isVisible()) {
        await canonical.fill(value);
        await canonical.press('Tab');
        return;
    }
    await page.locator('#filter-month-trigger').focus();
    await page.keyboard.press('Enter');
    await page.locator('#filter-month-year').fill(value.slice(0, 4));
    await selectChoice(page.locator('#filter-month-choice'), value.slice(5));
    await expect(canonical).toHaveValue(value);
}

async function assertFits(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const cards = await typeCards(page).getByRole('link').all();
    const boxes = await Promise.all(cards.map(card => card.boundingBox()));
    expect(Math.max(...boxes.map(box => box.height))).toBeLessThanOrEqual(48);
    expect(Math.max(...boxes.map(box => box.y)) - Math.min(...boxes.map(box => box.y))).toBeLessThanOrEqual(1);

    const width = page.viewportSize().width;
    for (const control of await page.locator('#transaction-filters input:not([type="hidden"]), #transaction-filters select, #transaction-filters summary, #transaction-clear-filters, #transaction-apply-filters').all()) {
        if (!await control.isVisible()) continue;
        const box = await control.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    }
    if (width >= 1024 && !await page.locator('#transaction-extra-filters').evaluate(element => element.open)) {
        // The desktop overview stays compact while refinements remain available.
        expect((await page.locator('#transaction-filters').boundingBox()).height).toBeLessThanOrEqual(180);
    }
}

test('transaction navigation preserves GET state, keyboard selection and browser history', async ({ page }, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const category = await prepare(page, testInfo);
    await openFilters(page);
    await page.keyboard.press('Tab');
    await expect(page.locator('#filter-date')).toBeFocused();
    await expect(typeCards(page).getByRole('link', { name: /^All/ })).toContainText('3');
    const expenses = typeCards(page).getByRole('link', { name: /^Expenses/ });
    await expenses.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/type=EXPENSE/);
    await expect(expenses).toHaveAttribute('aria-current', 'true');
    const fixed = page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ });
    await fixed.click();
    await expect(page).toHaveURL(/recurrence=fixed/);
    await expect(fixed).toHaveAttribute('aria-current', 'true');
    await expect(page.locator('#transaction-results-status')).toHaveText('1 transaction');
    const legacyCategory = new URL(page.url());
    legacyCategory.searchParams.set('category', category);
    await page.goto(legacyCategory.pathname + legacyCategory.search);
    await expect(page).toHaveURL(new RegExp(`category=${category}`));
    await expect(page.locator('#transaction-category-context')).toContainText('Navigation subscriptions');
    await page.locator('#transaction-clear-category').press('Enter');
    await expect(page).not.toHaveURL(/category=/);
    await expect(page).toHaveURL(/recurrence=fixed/);
    await page.goBack();
    await expect(page.locator('#filter-category')).toHaveValue(category);
    await typeCards(page).getByRole('link', { name: /^Income/ }).click();
    await expect(page).not.toHaveURL(/category=/);
    await expect(page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByText('Installments')).toHaveCount(0);
    await expect(page.getByText('No matching transactions')).toBeVisible();
    await page.goBack();
    await expect(page.locator('#filter-category')).toHaveValue(category);
    await expect(page.locator('#transaction-results-status')).toHaveText('1 transaction');
    await chooseBilledMonth(page, '2026-02');
    await expect(typeCards(page).getByRole('link', { name: /^All/ })).toContainText('1');
    await page.locator('#filter-date').fill('2026-01-15');
    await page.locator('#filter-date').press('Tab');
    // Sorting uses the applied filter state after the localized date redirect.
    await expect(page).toHaveURL(/date=2026-01-15/);
    await expect(page.locator('#filter-date')).toBeVisible();
    await page.locator('#filter-sort').selectOption('oldest');
    await expect(page).toHaveURL(/sort=oldest/);
    await expect(page).toHaveURL(/recurrence=fixed/);
    await expect(page).toHaveURL(/date=2026-01-15/);
    await expect(page.locator('#filter-category')).toHaveValue(category);
    await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
    await expect(page).toHaveURL(/\/transactions\/$/);
    await expect(page.locator('#transaction-results-status')).toHaveText('3 transactions');
    await page.locator('#filter-search').fill('Navigation subscriptions');
    await expect(page.locator('#transaction-results-status')).toHaveText('2 transactions');
    await page.locator('#filter-search').fill('Navigation bank');
    await expect(page.locator('#transaction-results-status')).toHaveText('3 transactions');
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
            await expect(page.locator('#transaction-extra-filters')).not.toHaveAttribute('open', '');
            await expect(page.locator('#transaction-extra-filters > summary')).toContainText(mobile ? 'Mais filtros' : 'More filters');
            await expect(page.locator('#filter-category-search')).toHaveCount(0);
            await expect(page.locator('#filter-category')).toBeHidden();
            await expect(page.locator('#filter-sort')).toBeHidden();
            await expect(page.locator('#filter-date')).toBeHidden();
            await expect(page.locator('#transaction-apply-filters')).toBeHidden();
            await expect(page.locator('#transaction-sort')).toHaveCount(0);
            await assertFits(page);
            await page.screenshot({ path: testInfo.outputPath('transactions.png'), fullPage: true });
            await openFilters(page);
            await page.keyboard.press('Tab');
            await expect(page.locator('#filter-date')).toBeFocused();
            await expect(page.locator('#filter-date')).toBeVisible();
            await expect(page.locator('#filter-sort')).toBeVisible();
            await expect(page.locator('#transaction-recurrence-options')).toBeVisible();
            await expect(page.locator('#filter-month-trigger')).toHaveCSS('background-color',
                await page.locator('#filter-search').evaluate(element => getComputedStyle(element).backgroundColor));
            if (!mobile) {
                const date = await page.locator('#filter-date').boundingBox();
                const recurrence = await page.locator('#transaction-recurrence-options').boundingBox();
                const sort = await page.locator('#filter-sort').boundingBox();
                expect(Math.abs(date.y - recurrence.y)).toBeLessThanOrEqual(2);
                expect(Math.abs(date.y - sort.y)).toBeLessThanOrEqual(2);
            }
            await assertFits(page);
            await page.screenshot({ path: testInfo.outputPath('transactions-filters.png'), fullPage: true });
        });
    }
}

test('transaction filtering works without JavaScript on mobile', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    try {
        const category = await prepare(page, testInfo);
        await page.goto(`/transactions/?category=${category}&type=EXPENSE`);
        await page.locator('#filter-sort').selectOption('oldest');
        await page.getByRole('button', {name: 'Apply filters'}).press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('category') === category && url.searchParams.get('sort') === 'oldest');
        await page.locator('#transaction-clear-category').press('Enter');
        await expect(page).toHaveURL(url => !url.searchParams.has('category') && url.searchParams.get('type') === 'EXPENSE');
        await typeCards(page).getByRole('link', { name: /^Expenses/ }).click();
        await openFilters(page);
        await page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ }).click();
        await page.locator('#filter-month').fill('2026-03');
        await page.getByRole('button', { name: 'Apply filters' }).click();
        await expect(page.getByText('No matching transactions')).toBeVisible();
        await page.getByRole('link', { name: 'Clear filters', exact: true }).first().click();
        await expect(page.locator('#transaction-results-status')).toHaveText('3 transactions');
        await assertFits(page);
    } finally {
        await context.close();
    }
});

for (const width of [390, 1280]) {
test(`transaction updates retain viewport and focus at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 650 });
    await prepare(page, testInfo);

    async function keepsPosition(control, remainsVisible = true, action = () => control.click()) {
        await control.scrollIntoViewIfNeeded();
        await control.evaluate(element => element.focus({ preventScroll: true }));
        const before = await page.evaluate(() => window.scrollY);
        expect(before).toBeGreaterThan(50);
        const updated = page.evaluate(() => new Promise(resolve => document.addEventListener('tuxedo:live-filters-updated', () => resolve(), {once: true})));
        await action();
        await updated;
        await expect(page.locator('#transaction-results')).not.toHaveAttribute('aria-busy', 'true');
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
    await expect(page.locator('#transaction-results-status')).toHaveText('2 transactions');
    await openFilters(page);
    await keepsPosition(page.getByRole('navigation', { name: 'Recurrence', exact: true }).getByRole('link', { name: /^Fixed/ }));
    await keepsPosition(page.locator('#filter-sort'), true, () => page.locator('#filter-sort').selectOption('oldest'));
    await keepsPosition(page.getByRole('link', { name: 'Clear filters', exact: true }), false);
    await expect(page.locator('#transaction-results-status')).toHaveText('3 transactions');
    await keepsPosition(page.locator('#filter-search'), true, async () => {
        await page.locator('#filter-search').fill('No matching record');
        await page.locator('#filter-search').press('Enter');
    });
    await expect(page.getByText('No matching transactions')).toBeVisible();

    // Deliberate navigation to another page still starts at that destination.
    const origin = requestPath(page.url());
    await page.getByRole('link', { name: 'New transaction', exact: true })
        .evaluate(element => element.focus({ preventScroll: true }));
    await page.keyboard.press('Enter');
    await expectContextualDestination(page, '/transactions/create/', origin);
    await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});
}

async function toolbarGeometry(page, native = false) {
    await page.evaluate(async () => { await document.fonts.ready; });
    return page.evaluate(({native}) => {
        const selectors = {
            bar: '#transaction-filters', search: '#filter-search',
            month: native ? '#filter-month' : '#filter-month-trigger',
            types: '#transaction-type-options', all: '#transaction-type-all',
            income: '#transaction-type-INCOME', expenses: '#transaction-type-EXPENSE',
            allCount: '#transaction-type-all .transaction-type-count',
            incomeCount: '#transaction-type-INCOME .transaction-type-count',
            expensesCount: '#transaction-type-EXPENSE .transaction-type-count',
            filters: '#transaction-extra-filters > summary',
            indicator: '#transaction-extra-filter-indicator', clearSlot: '#transaction-clear-control',
        };
        if (native) selectors.apply = '#transaction-apply-filters';
        const boxes = Object.fromEntries(Object.entries(selectors).map(([key, selector]) => {
            const box = document.querySelector(selector).getBoundingClientRect();
            return [key, {x: box.x + scrollX, y: box.y + scrollY, width: box.width, height: box.height}];
        }));
        return {boxes, clientWidth: document.documentElement.clientWidth,
            layoutWidth: document.querySelector('.app-layout').getBoundingClientRect().width,
            overflowing: document.documentElement.scrollHeight > document.documentElement.clientHeight};
    }, {native});
}

function expectSameToolbar(before, after, expanded = false) {
    // Root clientWidth excludes only a rendered scrollbar, not an empty stable
    // gutter (CSSOM View #dom-element-clientwidth). Compare the actual layout.
    expect(after.layoutWidth).toBe(before.layoutWidth);
    for (const [name, box] of Object.entries(before.boxes)) {
        for (const dimension of ['x', 'y', 'width', 'height']) {
            // Deliberately expanding criteria changes only the form's height.
            if (expanded && name === 'bar' && dimension === 'height') continue;
            expect(Math.abs(after.boxes[name][dimension] - box[dimension]), `${name}.${dimension}`).toBeLessThanOrEqual(1);
        }
    }
}

async function applyTypeWithKeyboard(page, kind) {
    const target = page.locator(`#transaction-type-${kind || 'all'}`);
    await target.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(url => (url.searchParams.get('type') || '') === kind);
    await expect(target).toHaveAttribute('aria-current', 'true');
    return target;
}

async function scrollbarLayout(page) {
    return page.evaluate(() => {
        const root = document.documentElement;
        const app = document.querySelector('.app-layout');
        const rootStyle = getComputedStyle(root);
        return {
            innerWidth, innerHeight,
            rootClientWidth: root.clientWidth, rootRectWidth: root.getBoundingClientRect().width,
            bodyClientWidth: document.body.clientWidth, bodyRectWidth: document.body.getBoundingClientRect().width,
            appLayoutWidth: app.getBoundingClientRect().width,
            mainWidth: document.querySelector('main').getBoundingClientRect().width,
            computedGutter: rootStyle.scrollbarGutter, rootOverflowX: rootStyle.overflowX, rootOverflowY: rootStyle.overflowY,
            renderedScrollbarWidth: innerWidth - root.clientWidth,
            reservedLayoutGutter: innerWidth - app.getBoundingClientRect().width,
        };
    });
}

for (const theme of ['light', 'dark']) {
    for (const [width, height, language] of [[1536, 900, 'en'], [1440, 900, 'pt-br'], [1100, 900, 'pt-br'], [390, 1200, 'pt-br'], [320, 1200, 'en']]) {
        test(`transaction toolbar geometry stays stable across live states (${width}, ${language}, ${theme})`, async ({page}, info) => {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await page.setViewportSize({width, height});
            await prepare(page, info, 10);
            await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
            await page.goto('/transactions/');
            await expect(page.locator('#transaction-results-status')).toHaveText(language === 'pt-br' ? '13 transações' : '13 transactions');
            await expect(page.locator('#transaction-clear-filters')).toHaveCount(0);
            const baseline = await toolbarGeometry(page);
            expect(baseline.overflowing).toBe(true);
            if (width >= 1440) {
                expect(baseline.boxes.bar.height).toBeLessThanOrEqual(74);
                for (const name of ['month', 'types', 'filters', 'clearSlot']) {
                    expect(Math.abs(baseline.boxes[name].y - baseline.boxes.search.y), name).toBeLessThanOrEqual(1);
                }
            }
            await page.screenshot({path: info.outputPath('toolbar-all.png')});

            for (const kind of ['INCOME', 'EXPENSE', '']) {
                const target = await applyTypeWithKeyboard(page, kind);
                await expect(target).toBeFocused();
                const geometry = await toolbarGeometry(page);
                expectSameToolbar(baseline, geometry);
                if (kind === 'INCOME') expect(geometry.overflowing).toBe(false);
                await expect(page.locator('#transaction-clear-filters')).toHaveCount(kind ? 1 : 0);
                await page.screenshot({path: info.outputPath(`toolbar-${kind || 'all-again'}.png`)});
            }
            await page.goBack();
            await expect(page).toHaveURL(url => url.searchParams.get('type') === 'EXPENSE');
            expectSameToolbar(baseline, await toolbarGeometry(page));
            await page.goForward();
            await expect(page).toHaveURL(url => !url.searchParams.has('type'));
            expectSameToolbar(baseline, await toolbarGeometry(page));

            const search = page.locator('#filter-search');
            await search.focus();
            await page.keyboard.type('Monthly');
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Monthly');
            await expect(page.locator('#transaction-results-status')).toHaveText(language === 'pt-br' ? '1 transação' : '1 transaction');
            await expect(search).toBeFocused();
            expect(await search.evaluate(input => input.selectionStart)).toBe(7);
            expectSameToolbar(baseline, await toolbarGeometry(page));
            await page.locator('#transaction-clear-filters').press('Enter');
            await expect(page).toHaveURL(url => !url.searchParams.has('q'));
            expectSameToolbar(baseline, await toolbarGeometry(page));

            await page.locator('#filter-month-trigger').press('Enter');
            const year = page.locator('#filter-month-year');
            await year.focus(); await page.keyboard.press('ControlOrMeta+A');
            await page.keyboard.type('2026'); await page.keyboard.press('Enter');
            await page.keyboard.type(language === 'en' ? 'sep' : 'sete');
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(url => url.searchParams.get('month') === '2026-09');
            await expect(page.locator('#filter-month-trigger')).toBeFocused();
            expectSameToolbar(baseline, await toolbarGeometry(page));
            await page.locator('#transaction-clear-filters').press('Enter');
            await expect(page).toHaveURL(url => !url.searchParams.has('month'));

            await openFilters(page);
            expectSameToolbar(baseline, await toolbarGeometry(page), true);
            const panel = await page.locator('#transaction-extra-filters > .filter-disclosure-panel').boundingBox();
            const summary = await page.locator('#transaction-extra-filters > summary').boundingBox();
            expect(panel.y).toBeGreaterThanOrEqual(summary.y + summary.height);
            await applyTypeWithKeyboard(page, 'INCOME');
            expectSameToolbar(baseline, await toolbarGeometry(page), true);
            await applyTypeWithKeyboard(page, 'EXPENSE');
            expectSameToolbar(baseline, await toolbarGeometry(page), true);
            const sort = page.locator('#filter-sort');
            await sort.focus(); await page.keyboard.press('Home'); await page.keyboard.press('ArrowDown');
            await expect(page).toHaveURL(url => url.searchParams.get('sort') === 'oldest');
            await page.locator('#transaction-extra-filters > summary').press('Enter');
            await expect(page.locator('#transaction-extra-filters')).not.toHaveAttribute('open', '');
            expectSameToolbar(baseline, await toolbarGeometry(page));
            await page.locator('#transaction-clear-filters').press('Enter');
            await expect(page).toHaveURL(url => !url.searchParams.has('sort') && !url.searchParams.has('type'));
            expectSameToolbar(baseline, await toolbarGeometry(page));
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            for (const label of await typeCards(page).locator('a > span:first-child').all()) {
                expect(await label.evaluate(node => node.scrollWidth <= node.clientWidth), await label.textContent()).toBe(true);
            }
        });
    }
}

for (const [width, language] of [[1366, 'en'], [1440, 'pt-br'], [390, 'pt-br']]) {
    test(`transaction toolbar geometry remains stable with native GET (${width}, ${language})`, async ({browser}, info) => {
        const context = await browser.newContext({javaScriptEnabled: false, viewport: {width, height: 1200}});
        try {
            const page = await context.newPage();
            await prepare(page, info, 10);
            await context.addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
            await page.goto('/transactions/');
            await expect(page.locator('#filter-month-trigger')).toHaveCount(0);
            await expect(page.locator('#transaction-apply-filters')).toBeVisible();
            const baseline = await toolbarGeometry(page, true);
            if (width >= 1440) {
                for (const name of ['month', 'types', 'filters', 'clearSlot']) {
                    expect(Math.abs(baseline.boxes[name].y - baseline.boxes.search.y), name).toBeLessThanOrEqual(1);
                }
            }
            for (const kind of ['INCOME', 'EXPENSE', '']) {
                await applyTypeWithKeyboard(page, kind);
                expectSameToolbar(baseline, await toolbarGeometry(page, true));
                await expect(page.locator('#transaction-clear-filters')).toHaveCount(kind ? 1 : 0);
            }
            await page.locator('#filter-month').fill('2026-09');
            await page.locator('#transaction-apply-filters').press('Enter');
            await expect(page).toHaveURL(url => url.searchParams.get('month') === '2026-09');
            expectSameToolbar(baseline, await toolbarGeometry(page, true));
            await page.locator('#transaction-clear-filters').press('Enter');
            await expect(page.locator('#filter-month')).toHaveValue('');
            expectSameToolbar(baseline, await toolbarGeometry(page, true));
        } finally { await context.close(); }
    });
}


for (const theme of ['light', 'dark']) {
    test(`transaction toolbar reserves a real classic scrollbar gutter (${theme})`, async ({baseURL}, info) => {
        // Headless Chromium normally hides scrollbars. This independent launch
        // must expose a measured gutter, rather than certify overlay geometry.
        const classicBrowser = await chromium.launch({
            headless: true, ignoreDefaultArgs: ['--hide-scrollbars'],
            args: ['--disable-features=OverlayScrollbar,FluentOverlayScrollbar'],
        });
        try {
            const context = await classicBrowser.newContext({baseURL, viewport: {width: 1440, height: 900}});
            const measurements = [];
            try {
                const page = await context.newPage();
                await page.addInitScript(value => localStorage.setItem('theme', value), theme);
                await prepare(page, info, 10);
                await context.addCookies([{name: 'django_language', value: 'pt-br', url: baseURL}]);
                await page.goto('/transactions/');
                await expect(page.locator('#transaction-results-status')).toHaveText('13 transações');
                const baseline = await toolbarGeometry(page);
                const baselineLayout = await scrollbarLayout(page);
                measurements.push({state: 'long', ...baselineLayout, geometry: baseline});
                expect(baselineLayout.renderedScrollbarWidth, 'the long list must render a real classic scrollbar').toBeGreaterThan(0);
                expect(baselineLayout.reservedLayoutGutter).toBeGreaterThan(0);
                expect(baselineLayout.computedGutter).toBe('stable');
                expect(baseline.overflowing).toBe(true);
                expect(baseline.boxes.bar.height).toBeLessThanOrEqual(74);
                for (const name of ['month', 'types', 'filters', 'clearSlot']) {
                    expect(Math.abs(baseline.boxes[name].y - baseline.boxes.search.y), name).toBeLessThanOrEqual(1);
                }
                await page.screenshot({path: info.outputPath(`toolbar-classic-${theme}-long.png`)});

                for (const [kind, count] of [['INCOME', '1 transação'], ['EXPENSE', '12 transações'], ['', '13 transações']]) {
                    const target = await applyTypeWithKeyboard(page, kind);
                    await expect(target).toBeFocused();
                    await expect(page.locator('#transaction-results-status')).toHaveText(count);
                    const geometry = await toolbarGeometry(page);
                    const layout = await scrollbarLayout(page);
                    measurements.push({state: kind || 'all', ...layout, geometry});
                    // A short list has no rendered scrollbar. Its reserved gutter
                    // still reduces body.app-layout, unlike root.clientWidth.
                    expect(layout.reservedLayoutGutter, 'the short list must retain the classic gutter').toBeGreaterThan(0);
                    expect(layout.reservedLayoutGutter).toBe(baselineLayout.reservedLayoutGutter);
                    expect(layout.mainWidth).toBe(baselineLayout.mainWidth);
                    expect(layout.computedGutter).toBe('stable');
                    expect(geometry.overflowing).toBe(kind !== 'INCOME');
                    expectSameToolbar(baseline, geometry);
                    await expect(page.locator('#transaction-clear-filters')).toHaveCount(kind ? 1 : 0);
                    if (kind === 'INCOME') {
                        await page.screenshot({path: info.outputPath(`toolbar-classic-${theme}-short.png`)});
                    }
                }
            } finally {
                try {
                    const path = info.outputPath('classic-scrollbar-measurements.json');
                    await writeFile(path, JSON.stringify(measurements, null, 2));
                    await info.attach('classic-scrollbar-measurements', {path, contentType: 'application/json'});
                } finally { await context.close(); }
            }
        } finally { await classicBrowser.close(); }
    });
}
