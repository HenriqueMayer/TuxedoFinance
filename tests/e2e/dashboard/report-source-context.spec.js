// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `source-context-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Context bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Context account', currency: 'BRL',
        opening_balance: '1000', opening_date: '2020-01-01'});
    await post(page, '/categories/create/', {name: 'Context category', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Context category$/}).getAttribute('value');
    const month = new Date().toISOString().slice(0, 7);
    await post(page, '/transactions/create/', {title: 'Context source', category, amount: '18.25',
        transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, date: `${month}-01`});
    await post(page, '/transactions/create/', {title: 'Outside source period', category, amount: '99',
        transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, date: '2020-02-01'});
    return {month, bank, account};
}

for (const [theme, language] of [['light', 'en'], ['dark', 'pt-br']]) {
for (const workspace of ['categories', 'reports']) {
    test(`chart source Cancel, Back and Save retain exact context (${workspace}, ${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 800});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {month} = await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        const path = workspace === 'categories' ? `/analytics/?month=${month}`
            : `/analytics/?charts_offset=-1&instrument_month=${month}&installment_month=${month}`;
        const anchor = workspace === 'categories' ? 'category-heading' : 'instrument-activity';
        const origin = `${path}#${anchor}`;
        // An already contextualized owned target keeps its own query/hash, but
        // must never retain an externally supplied return destination.
        await page.route('**/dashboard/chart-details/?token=*', async route => {
            const response = await route.fetch();
            const data = await response.json();
            for (const row of data.rows) for (const source of row.sources) {
                const target = new URL(source.url, info.project.use.baseURL);
                target.searchParams.set('record_context', 'preserved');
                target.searchParams.set('next', 'https://outside.example/');
                target.hash = 'id_title';
                source.url = target.pathname + target.search + target.hash;
            }
            await route.fulfill({response, body: JSON.stringify(data), contentType: 'application/json'});
        });
        await page.goto(path);
        const mark = page.locator(workspace === 'categories'
            ? '[aria-labelledby="category-heading"] [data-point]' : '#instrument-activity [data-point]').first();
        const panel = page.locator('.chart-composition:visible');
        async function openSource() {
            await mark.focus();
            await page.keyboard.press('Control');
            const source = panel.getByRole('link', {name: /Context source/});
            await expect(source).toBeVisible();
            await expect(panel).not.toContainText('Outside source period');
            const target = new URL(await source.getAttribute('href'));
            expect(target.pathname).toMatch(/^\/transactions\/\d+\/edit\/$/);
            expect(target.searchParams.get('record_context')).toBe('preserved');
            expect(target.searchParams.getAll('next')).toEqual([origin]);
            expect(target.hash).toBe('#id_title');
            await source.press('Enter');
            await expect(page).toHaveURL(target.href);
            await expect(page.locator('#id_title')).toHaveValue('Context source');
            await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        }
        const cancelLabel = language === 'en' ? 'Cancel' : 'Cancelar';
        const saveLabel = language === 'en' ? 'Save' : 'Salvar';
        await openSource();
        await expect(page.getByRole('link', {name: cancelLabel, exact: true})).toHaveAttribute('href', origin);
        await page.getByRole('link', {name: cancelLabel, exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
        await expect(page.locator(`#${anchor}`)).toBeInViewport();
        await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(20);
        await openSource();
        await page.goBack();
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
        await expect(page.locator(`#${anchor}`)).toBeInViewport();
        await openSource();
        await page.locator('#id_title').fill('Context source saved');
        await page.getByRole('button', {name: saveLabel, exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === origin);
        await expect(page.locator(`#${anchor}`)).toBeInViewport();
        expect((await page.request.get('/transactions/')).status()).toBe(200);
    });
}
}

test('balance composition opens the exact account in the viewport including reserves', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 600});
    await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
    const {bank, account} = await seed(page, info);
    // Keep the source below several ordinary accounts so the assertion detects
    // a body-swap scroll reset rather than an accidentally visible first row.
    for (let index = 0; index < 3; index++) {
        await post(page, '/banking/accounts/create/', {bank, name: `A context ${index}`, currency: 'BRL',
            opening_balance: '0', opening_date: '2020-01-01', planning_enabled: 'on'});
    }
    const path = '/analytics/?charts_offset=0';
    for (const reserved of [true, false]) {
        if (!reserved) {
            await post(page, `/banking/accounts/${account}/edit/`, {bank, name: 'Context account', currency: 'BRL',
                opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on'});
        }
        await page.goto(path);
        const mark = page.locator('#balance-evolution [data-point]').last();
        await mark.focus();
        await page.keyboard.press('Control');
        const source = page.locator('.chart-composition:visible').getByRole('link', {name: /Context account/});
        await expect(source).toBeVisible();
        const target = new URL(await source.getAttribute('href'));
        expect(target.pathname).toBe(`/banking/${bank}/`);
        expect(target.hash).toBe(`#account-row-${account}`);
        expect(target.searchParams.get('next')).toBe(`${path}#balance-evolution`);
        await source.press('Enter');
        await expect(page).toHaveURL(target.href);
        if (reserved) await expect(page.locator(`#bank-reserves-${bank}`)).toHaveAttribute('open', '');
        const heading = page.locator(`#account-name-${account}`);
        await expect(heading).toBeInViewport();
        await expect.poll(async () => (await heading.boundingBox())?.y).toBeGreaterThanOrEqual(70);
        await page.screenshot({path: info.outputPath(`balance-account-${reserved ? 'reserved' : 'included'}.png`)});
    }
});
