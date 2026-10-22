// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const fs = require('node:fs/promises');

async function post(page, path, fields = {}) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
}

async function seed(page, info) {
    const username = `home-design-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    const today = new Date().toISOString().slice(0, 10), month = today.slice(0, 7);
    const names = {bank: 'Banco' + 'B'.repeat(85), account: 'Conta' + 'C'.repeat(90),
        card: 'Cartão' + 'T'.repeat(90), category: 'Categoria' + 'E'.repeat(85)};
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    await post(page, '/banking/create/', {name: names.bank, color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: names.account, currency: 'BRL',
        opening_date: '2020-01-01', opening_balance: '25000', planning_enabled: 'on'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: names.card, card_type: 'PHYSICAL',
        closing_day: '31', due_day: '28', manual_settlement_from: today, color: '#5B3E7C'});
    for (const name of [names.category, 'Compras de casa', 'Transportes e deslocamentos']) {
        await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE'});
    }
    await page.goto('/transactions/create/');
    const card = await page.locator('#id_credit_card option').last().getAttribute('value');
    for (const [name, amount] of [[names.category, '110.25'], ['Compras de casa', '89.75'], ['Transportes e deslocamentos', '40.50']]) {
        const category = await page.locator('#id_category option').filter({hasText: name}).getAttribute('value');
        await post(page, '/transactions/create/', {title: `Home source ${name}`, category, amount,
            transaction_type: 'EXPENSE', payment_channel: 'CREDIT_CARD', credit_card: card, date: `${month}-01`});
    }
    return {names, month, bank, account};
}

async function capture(page, info, name, observations) {
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
    observations.push({name, ...await page.evaluate(() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth}))});
    await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
    expect(observations.at(-1).documentWidth).toBeLessThanOrEqual(observations.at(-1).width);
}

for (const theme of ['light', 'dark']) for (const width of [1440, 360]) {
    test(`Home presentation and period controls (${theme}, ${width})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: width < 640 ? 640 : 900});
        const data = await seed(page, info), observations = [];
        await page.context().addCookies([{name: 'django_language', value: width < 640 ? 'pt-br' : 'en', url: info.project.use.baseURL}]);
        await page.goto('/dashboard/');
        // Consume fixture success notices before comparing stable period slots.
        await page.reload();
        await capture(page, info, '01-current', observations);
        await expect(page.locator('#category-heading, #outlook-heading')).toHaveCount(0);
        const invoice = page.locator('main a[href*="/banking/invoices/"]').filter({hasText: data.names.card});
        observations.push({name: 'invoice-name', ...await invoice.evaluate(element => ({width: element.clientWidth, textWidth: element.scrollWidth}))});
        const identity = observations.find(item => item.name === 'invoice-name');
        expect(identity.textWidth).toBeLessThanOrEqual(identity.width);
        await expect(invoice.locator('xpath=ancestor::li').locator('.card-miniature')).toHaveCount(1);
        await page.locator('main').getByRole('link', {name: width < 640 ? 'Análises' : 'Analytics', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/' && url.searchParams.get('month') === data.month);
        const categoryChart = page.locator('#finance-monthly-analysis [aria-labelledby="category-heading"]');
        const category = categoryChart.locator('[data-point]').first();
        observations.push({name: 'category-target', ...await category.evaluate(element => {
            const box = element.getBoundingClientRect(); const label = element.querySelector('span');
            return {height: box.height, labelWidth: label.clientWidth, labelTextWidth: label.scrollWidth};
        })});
        const target = observations.find(item => item.name === 'category-target');
        expect(target.height).toBeGreaterThanOrEqual(44);
        expect(target.labelTextWidth).toBeLessThanOrEqual(target.labelWidth);
        await category.focus();
        await page.keyboard.press('Enter');
        await capture(page, info, '02-category-selected', observations);
        const summary = categoryChart.locator('[data-selection-period]');
        await expect(summary).toHaveText(data.names.category);
        expect(await summary.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        await page.keyboard.press('Control');
        const panel = page.locator(`#${await category.getAttribute('aria-controls')}`);
        await expect(panel).toBeVisible();
        await expect(panel).toContainText(data.names.category);
        await capture(page, info, '03-composition', observations);
        const source = panel.getByRole('link', {name: /Home source/}).first();
        const sourceUrl = new URL(await source.getAttribute('href'), page.url());
        expect(sourceUrl.pathname).toMatch(/^\/transactions\/\d+\/edit\/$/);
        expect(sourceUrl.searchParams.get('next')).toBe(`/analytics/?month=${data.month}#category-heading`);
        await source.press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(`/analytics/?month=${data.month}#category-heading`);
        await page.getByRole('link', {name: width < 640 ? 'Cancelar' : 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === `/analytics/?month=${data.month}#category-heading`);
        await expect(page.locator('#category-heading')).toBeInViewport();
        await page.goto('/dashboard/');
        const navigation = page.locator('[aria-labelledby="performance-heading"] [data-period-navigation]');
        const currentCaption = await page.locator('#selected-period-heading').textContent();
        await navigation.scrollIntoViewIfNeeded();
        const before = await navigation.locator('.period-navigation-rail').boundingBox();
        const beforeScroll = await page.evaluate(() => scrollY);
        await navigation.locator('a').first().press('Enter');
        await expect(page).not.toHaveURL(/\/dashboard\/$/);
        await navigation.scrollIntoViewIfNeeded();
        const after = await navigation.locator('.period-navigation-rail').boundingBox();
        observations.push({name: 'period-rail', before, after});
        expect(Math.abs(before.x - after.x)).toBeLessThan(1);
        expect(Math.abs(before.width - after.width)).toBeLessThan(1);
        expect(Math.abs(before.y + beforeScroll - after.y - await page.evaluate(() => scrollY))).toBeLessThan(1);
        await capture(page, info, '04-past-month', observations);
        await navigation.locator('.period-navigation-reset a').press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await page.goto('/dashboard/?month=invalid');
        await expect(page.locator('#selected-period-heading')).toHaveText(currentCaption);
        await capture(page, info, '05-invalid-month', observations);
        const date = new Date(`${data.month}-01T12:00:00Z`);
        date.setUTCMonth(date.getUTCMonth() + 6);
        await page.goto(`/dashboard/?month=${date.toISOString().slice(0, 7)}`);
        await expect(navigation.locator('.period-navigation-rail > :last-child')).toHaveAttribute('aria-disabled', 'true');
        await capture(page, info, '06-forecast-limit', observations);
        await page.locator('main').getByRole('link', {name: width < 640 ? 'Análises' : 'Analytics', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/');
        const table = page.locator('[role="region"][aria-labelledby="outlook-heading"]');
        await table.focus();
        await expect(table).toBeFocused();
        if (width < 640) {
            await page.keyboard.press('ArrowRight');
            await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
            expect(await page.evaluate(() => scrollX)).toBe(0);
        }
        await capture(page, info, '07-outlook-keyboard', observations);
        await fs.writeFile(info.outputPath('observations.json'), JSON.stringify(observations, null, 2));
    });
}

test('Home native period, references and Analytics outlook retain keyboard access', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 360, height: 640}});
    try {
        const page = await context.newPage();
        const data = await seed(page, info), observations = [];
        await page.goto('/dashboard/');
        await page.reload();
        const navigation = page.locator('[aria-labelledby="performance-heading"] [data-period-navigation]');
        await navigation.getByRole('link', {name: 'Previous month', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(/\/dashboard\/$/);
        await navigation.getByRole('link', {name: 'Back to this month', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        const invoice = page.locator('main a[href*="/banking/invoices/"]').filter({hasText: data.names.card});
        await invoice.press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue('/dashboard/');
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await page.locator('main').getByRole('link', {name: 'Analytics', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/analytics/');
        const table = page.locator('[role="region"][aria-labelledby="outlook-heading"]');
        await table.focus();
        await page.keyboard.press('ArrowRight');
        await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
        await capture(page, info, '08-native-outlook', observations);
    } finally { await context.close(); }
});
