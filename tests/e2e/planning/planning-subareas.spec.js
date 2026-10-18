// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, values, source = path) {
    const response = await page.request.get(source);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `planning-subareas-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Planning bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Daily account', currency: 'BRL',
        opening_balance: '5000', opening_date: '2020-01-01', planning_enabled: 'on', pix_enabled: 'on'});
    await post(page, '/investments/add/', {institution: bank, name: 'Travel reserve', currency: 'BRL',
        valuation_mode: 'MONETARY', purpose: 'MONTHLY_CASH', opening_balance: '500', opening_date: '2020-01-01'});
    await post(page, '/categories/create/', {name: 'Daily food', transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: 'Daily account'}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: /^Daily food$/}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10), month = today.slice(0, 7);
    for (let index = 0; index < 2; index++) await post(page, '/transactions/create/', {
        title: 'Groceries review', amount: '50', category, transaction_type: 'EXPENSE',
        payment_channel: 'ACCOUNT', bank_account: account, date: today});
    await post(page, '/planning/budgets/create/', {month, category, currency: 'BRL', amount: '80'});
    const goal = await post(page, '/planning/goals/create/', {name: 'Travel target', target_amount: '2000',
        currency: 'BRL', target_date: '2031-12-24', reserve_now: 'on', source: `account:${account}`, reserved_amount: '1000'});
    await page.goto(`${goal}reserve/`);
    const pot = await page.locator('#id_source option').filter({hasText: 'Travel reserve'}).getAttribute('value');
    await post(page, `${goal}reserve/`, {source: pot, amount: '200'});
    const archived = await post(page, '/planning/goals/create/', {name: 'Archived target', target_amount: '1000', currency: 'BRL'});
    await post(page, `${archived}archive/`, {}, archived);
    return {month, category, account, goal, archived, pot};
}

async function ready(page) {
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function allowDeparture(page) {
    page.on('dialog', dialog => dialog.accept());
    await page.addLocatorHandler(page.locator('#departure-confirm[open]'), async () => {
        await page.locator('[data-departure-leave]').click();
    });
}

async function helpBounds(page, tooltip) {
    const box = await tooltip.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(12);
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width - 12);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize().height);
    return box;
}

test('planning subareas keep readable complete screens', async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    await page.addInitScript(() => localStorage.setItem('theme', sessionStorage.getItem('subareaTheme') || 'light'));
    const {month, goal} = await seed(page, info);
    // Consume synthetic setup notices before comparing the actual workspaces.
    await page.goto('/planning/');
    await page.context().addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
    const routes = [
        ['01-month', `/planning/?month=${month}`],
        ['02-goals', '/planning/goals/?archived=1'],
        ['03-goal-detail', goal],
        ['04-tools', '/planning/tools/'],
        ['05-signals', '/planning/signals/?reviewed=1'],
        ['06-settings', '/planning/signals/settings/'],
        ['07-goal-create', '/planning/goals/create/'],
        ['08-budget-create', `/planning/budgets/create/?month=${month}`],
    ];
    for (const [name, route] of routes) {
        await page.goto(route); await ready(page);
        await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
    }
    await page.setViewportSize({width: 390, height: 820});
    await page.evaluate(() => sessionStorage.setItem('subareaTheme', 'dark'));
    await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: info.project.use.baseURL}]);
    for (const [name, route] of [['09-settings-mobile', '/planning/signals/settings/'], ['10-goal-mobile', goal]]) {
        await page.goto(route); await ready(page);
        await expect(page.locator('html')).toHaveClass(/dark/);
        await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
    }
});

for (const theme of ['light', 'dark']) {
for (const width of [1440, 390]) {
test(`complete planning setup keeps grouped rules, source context and native actions (${width}, ${theme})`, async ({page}, info) => {
    await page.setViewportSize({width, height: 820});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await allowDeparture(page);
    const {account, goal, pot} = await seed(page, info);
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'MDY'});
    await page.context().addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
    const origin = '/planning/signals/?reviewed=1';
    await page.goto(`/planning/signals/settings/?next=${encodeURIComponent(origin)}`);
    const groups = page.locator('fieldset.finance-entry-group');
    await expect(groups).toHaveCount(4);
    const duplicateGroup = groups.filter({has: page.locator('#id_duplicates_enabled')});
    await expect(duplicateGroup.locator('#id_duplicate_days')).toBeVisible();
    await expect(groups.filter({has: page.locator('#id_subscriptionincrease_enabled')}).locator('#id_subscription_increase_percent')).toBeVisible();
    await expect(groups.filter({has: page.locator('#id_futurecashshortage_enabled')}).locator('#id_forecast_days')).toBeVisible();
    const duplicate = page.locator('#id_duplicates_enabled');
    await duplicate.press('Space');
    await expect(duplicate).not.toBeChecked();
    await page.keyboard.press('Tab');
    const duplicateHelp = page.locator('[data-help-trigger][aria-controls="id_duplicates_enabled-help"]');
    await expect(duplicateHelp).toBeFocused();
    await expect(page.locator('#id_duplicates_enabled-help')).toBeVisible();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Tab');
    await expect(page.locator('#id_duplicate_days')).toBeFocused();
    expect(await page.locator('#id_duplicate_days').evaluate(element => element.matches(':focus-visible'))).toBe(true);
    await page.locator('#id_duplicate_days').fill('99');
    await page.locator('#id_subscription_increase_percent').fill('12.34');
    await page.locator('#id_forecast_days').fill('45');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.locator('#id_duplicate_days-error-1')).toBeVisible();
    await expect(duplicate).not.toBeChecked();
    await expect(page.locator('#id_duplicate_days')).toHaveValue('99');
    await expect(page.locator('#id_subscription_increase_percent')).toHaveValue('12.34');
    await expect(page.locator('#id_forecast_days')).toHaveValue('45');
    await ready(page);
    await page.screenshot({path: info.outputPath(`settings-recovery-${width}-${theme}.png`), fullPage: true});
    await page.locator('#id_duplicate_days').fill('4');
    await duplicate.press('Space');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    const duplicateSignal = page.locator('#signal-results article').filter({hasText: 'Possible duplicate transaction'});
    const source = duplicateSignal.getByRole('link').first();
    const sourceURL = new URL(await source.getAttribute('href'), info.project.use.baseURL);
    expect(sourceURL.searchParams.get('next')).toBe(origin);
    const today = new Date().toISOString().slice(0, 10).split('-');
    await expect(source).toContainText(`${today[1]}/${today[2]}/${today[0]}`);
    await source.press('Enter');
    await expect(page.locator('#id_title')).toHaveValue('Groceries review');
    await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === origin);
    await expect(page.locator('#signal-filters input[name="reviewed"]')).toBeChecked();
    await duplicateSignal.getByRole('button', {name: 'Acknowledge', exact: true}).press('Enter');
    await expect(duplicateSignal.locator('.status-badge')).toHaveText('Acknowledged');
    await duplicateSignal.getByRole('button', {name: 'Reopen signal', exact: true}).press('Enter');
    await expect(duplicateSignal.locator('.status-badge')).toHaveCount(0);

    await page.goto(goal); await ready(page);
    await expect(page.getByRole('link', {name: 'Daily account', exact: true})).toBeVisible();
    await expect(page.getByRole('link', {name: 'Travel reserve', exact: true})).toBeVisible();
    expect((await page.locator('progress').boundingBox()).height).toBeLessThanOrEqual(8);
    await expect(page.locator('.monthly-outlook .money-highlight')).toContainText(/1[.,]200[.,]00/);
    await page.screenshot({path: info.outputPath(`goal-sources-${width}-${theme}.png`), fullPage: true});

    await page.goto('/planning/goals/create/');
    const reserve = page.locator('#id_reserve_now');
    const help = page.locator('[data-help-trigger][aria-controls="id_reserve_now-help"]');
    const tooltip = page.locator('#id_reserve_now-help');
    await help.hover();
    await expect(tooltip).toBeVisible();
    const box = await helpBounds(page, tooltip);
    await page.mouse.move(box.x + 16, box.y + 16);
    await expect(tooltip).toBeHidden();
    await reserve.focus();
    await page.keyboard.press('Tab');
    await expect(help).toBeFocused();
    await expect(tooltip).toBeVisible();
    await helpBounds(page, tooltip);
    await page.keyboard.press('Escape');
    await expect(tooltip).toBeHidden();
    await expect(help).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(reserve).toBeFocused();
    await page.keyboard.press('Space');
    await expect(page.locator('#goal-source-search')).toBeVisible();
    await expect(page.locator(`#id_source option[value="${pot}"]`)).toHaveText('Travel reserve · Planning bank · BRL 300.00');
    await selectChoice(page.locator('#id_source'), pot);
    await page.locator('#id_name').fill('Complete planning target');
    await page.locator('#id_target_amount').fill('2000');
    await page.locator('#id_target_date').fill('12/24/2031');
    await page.locator('#id_reserved_amount').fill('300.01');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.locator('#id_reserved_amount-error-1')).toBeVisible();
    await expect(reserve).toBeChecked();
    await expect(page.locator('#id_source')).toHaveValue(pot);
    await expect(page.locator('#id_reserved_amount')).toHaveValue('300.01');
    await ready(page);
    await page.screenshot({path: info.outputPath(`complete-goal-invalid-${width}-${theme}.png`), fullPage: true});
    await selectChoice(page.locator('#id_source'), `account:${account}`);
    await expect(page.locator('#id_reserved_amount')).toHaveValue('');
    await page.locator('#id_reserved_amount').fill('100');
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.getByRole('heading', {name: 'Complete planning target', exact: true})).toBeVisible();
    await expect(page.locator('.monthly-outlook .money-highlight')).toContainText(/100[.,]00/);
    await expect(page.locator('main')).toContainText('12/24/2031');
    await page.getByRole('button', {name: 'Archive goal', exact: true}).press('Enter');
    await expect(page.locator('.monthly-outlook .status-badge')).toHaveText('Archived');
    await expect(page.getByRole('link', {name: 'Reserve a balance', exact: true})).toHaveCount(0);
    await page.getByRole('button', {name: 'Restore goal', exact: true}).press('Enter');
    await expect(page.getByRole('link', {name: 'Reserve a balance', exact: true})).toBeVisible();
    await ready(page);
});
}

test(`initial reservation help supports touch without pinning mouse help (${theme})`, async ({browser}, info) => {
    const context = await browser.newContext({hasTouch: true, viewport: {width: 390, height: 820}});
    try {
        const page = await context.newPage();
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await seed(page, info);
        await context.addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
        await page.goto('/planning/goals/');
        // New help must initialize after the application's boosted navigation,
        // not only on a full document load.
        await page.getByRole('link', {name: 'New goal', exact: true}).tap();
        await expect(page).toHaveURL(url => url.pathname === '/planning/goals/create/'
            && url.searchParams.get('next') === '/planning/goals/');
        const help = page.locator('[data-help-trigger][aria-controls="id_reserve_now-help"]');
        const tooltip = page.locator('#id_reserve_now-help');
        await help.tap(); await expect(tooltip).toBeVisible();
        await helpBounds(page, tooltip);
        await page.screenshot({path: info.outputPath(`initial-reservation-touch-${theme}.png`)});
        await page.getByRole('heading', {name: 'New goal', exact: true}).tap();
        await expect(tooltip).toBeHidden();
        await expect(page.locator('#id_reserve_now')).not.toBeChecked();
        await expect(page.locator('#goal-source-search')).toBeHidden();
    } finally {await context.close();}
});
}

test('native complete planning registration and grouped settings retain recovery and help', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 820}});
    try {
        const page = await context.newPage();
        const {account} = await seed(page, info);
        await context.addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
        await page.goto('/planning/goals/create/');
        const summary = page.locator('summary[aria-label="Explain Reserve a balance now"]');
        await summary.press('Enter');
        const help = summary.locator('..').locator('.help-fallback-content');
        await expect(help).toBeVisible();
        await helpBounds(page, help);
        await summary.press('Enter');
        await page.locator('#id_name').fill('Native complete target');
        await page.locator('#id_target_amount').fill('500');
        await page.locator('#id_target_date').fill('24/12/2031');
        await page.locator('#id_reserve_now').press('Space');
        await page.locator('#id_source').selectOption(`account:${account}`);
        await page.locator('#id_reserved_amount').fill('99999');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_reserved_amount-error-1')).toBeVisible();
        await expect(page.locator('#id_source')).toHaveValue(`account:${account}`);
        await expect(page.locator('#id_reserved_amount')).toHaveValue('99999');
        await page.locator('#id_reserved_amount').fill('50');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.getByRole('heading', {name: 'Native complete target', exact: true})).toBeVisible();
        await expect(page.locator('.monthly-outlook .money-highlight')).toContainText(/50[.,]00/);
        const origin = '/planning/signals/?reviewed=1';
        await page.goto(`/planning/signals/settings/?next=${encodeURIComponent(origin)}`);
        await page.locator('#id_duplicates_enabled').press('Space');
        await page.locator('#id_duplicate_days').fill('99');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_duplicate_days-error-1')).toBeVisible();
        await expect(page.locator('#id_duplicates_enabled')).not.toBeChecked();
        await page.locator('#id_duplicate_days').fill('4');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await ready(page);
    } finally {await context.close();}
});
