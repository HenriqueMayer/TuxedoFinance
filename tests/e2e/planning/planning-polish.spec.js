// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');
const fs = require('node:fs/promises');

async function post(page, path, values, source = path, expected = 302) {
    const response = await page.request.get(source);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(expected);
    return saved.headers().location;
}

test('unbroken target context stays inside reservation entry', async ({page}, info) => {
    await page.addInitScript(() => localStorage.setItem('theme', sessionStorage.getItem('contextTheme') || 'light'));
    const {longGoal} = await seed(page, info), observations = [];
    for (const [width, theme] of [[1440, 'light'], [360, 'dark']]) {
        await page.setViewportSize({width, height: 640});
        await page.evaluate(value => sessionStorage.setItem('contextTheme', value), theme);
        await page.goto(`${longGoal}reserve/`);
        await record(page, info, `${width}-unbroken-reservation-context`, observations);
        await expect(page.locator('#source-search')).toBeVisible();
        await expect(page.locator('#id_amount')).toBeHidden();
    }
    await fs.writeFile(info.outputPath('context-layout.json'), JSON.stringify(observations, null, 2));
    expect(observations.filter(row => row.documentWidth > row.width)).toEqual([]);
});

async function seed(page, info) {
    const username = `plan-polish-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    const bankName = 'Banco de planejamento para viagens e compromissos familiares internacionais';
    const accountName = 'Conta de despesas e reservas familiares para viagens e compromissos de longo prazo';
    const potName = 'Reserva para despesas extraordinárias e viagens internacionais em família';
    const goalName = 'Reserva para uma viagem internacional com toda a família e despesas extraordinárias planejadas';
    const categoryName = 'Alimentação e compras para viagens e compromissos familiares';
    await post(page, '/banking/create/', {name: bankName, color: '#527891'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: accountName, currency: 'BRL',
        opening_balance: '5000', opening_date: '2020-01-01', planning_enabled: 'on'});
    await post(page, '/investments/add/', {institution: bank, name: potName, currency: 'BRL',
        valuation_mode: 'MONETARY', purpose: 'MONTHLY_CASH', opening_balance: '500', opening_date: '2020-01-01'});
    await post(page, '/categories/create/', {name: categoryName, transaction_type: 'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: accountName}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: categoryName}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10), month = today.slice(0, 7);
    for (let i = 0; i < 2; i++) await post(page, '/transactions/create/', {title: categoryName,
        amount: '50', category, transaction_type: 'EXPENSE', payment_channel: 'ACCOUNT', bank_account: account, date: today});
    await post(page, '/planning/budgets/create/', {month, category, currency: 'BRL', amount: '80'});
    const goal = await post(page, '/planning/goals/create/', {name: goalName, target_amount: '2000',
        currency: 'BRL', target_date: '2031-12-24', reserve_now: 'on', source: `account:${account}`, reserved_amount: '1000'});
    await page.goto(`${goal}reserve/`);
    const pot = await page.locator('#id_source option').filter({hasText: potName}).getAttribute('value');
    await post(page, `${goal}reserve/`, {source: pot, amount: '200'});
    const longGoal = await post(page, '/planning/goals/create/', {name: 'META'.repeat(30), target_amount: '1000', currency: 'BRL'});
    const archived = await post(page, '/planning/goals/create/', {name: 'Meta arquivada para filtros', target_amount: '1000', currency: 'BRL'});
    await post(page, `${archived}archive/`, {}, archived);
    await page.goto('/planning/');
    return {goal, longGoal, account, category, pot, month, goalName, categoryName, potName, bankName};
}

async function record(page, info, name, observations) {
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
    observations.push({name, ...await page.evaluate(() => ({
        width: innerWidth, documentWidth: document.documentElement.scrollWidth,
        overflowing: [...document.querySelectorAll('main *')].filter(element => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && (rect.right > innerWidth + 1 || rect.left < -1);
        }).slice(0, 12).map(element => ({tag: element.tagName, class: element.className,
            text: element.textContent.trim().slice(0, 150)})),
    }))});
    await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
}

for (const theme of ['light', 'dark']) {
test(`planning long-name screens, choices and short-mobile actions (${theme})`, async ({page}, info) => {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const departures = {native: 0, custom: 0};
    page.on('dialog', dialog => {departures.native++; return dialog.accept();});
    await page.addLocatorHandler(page.locator('#departure-confirm[open]'), () => {
        departures.custom++; return page.locator('[data-departure-leave]').click();
    });
    const data = await seed(page, info), observations = [];
    for (const [width, height, language] of [[1440, 900, 'en'], [360, 640, 'pt-br']]) {
        await page.setViewportSize({width, height});
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        for (const [name, route] of [
            ['month', `/planning/?month=${data.month}`], ['goals', '/planning/goals/'],
            ['goal-detail', data.goal], ['goal-unbroken', data.longGoal],
            ['tools', '/planning/tools/'], ['signals', '/planning/signals/?reviewed=1'],
            ['settings', '/planning/signals/settings/'], ['budget-create', `/planning/budgets/create/?month=${data.month}`],
            ['reserve', `${data.goal}reserve/`],
        ]) {
            await page.goto(route); await record(page, info, `${width}-${name}`, observations);
            if (name === 'goal-detail' || name === 'goal-unbroken') {
                const title = await page.locator('main h1').boundingBox();
                expect(title.x + title.width).toBeLessThanOrEqual(width - 16);
                const edit = page.locator('main header.workspace-header').first().getByRole('link');
                expect((await edit.boundingBox()).height).toBeLessThanOrEqual(48);
            }
            if (name === 'goals') {
                const oldDepartures = {...departures};
                await page.locator('#goal-query').pressSequentially('internacional', {delay: 10});
                await expect(page.locator('#goal-results article')).toHaveCount(1);
                await record(page, info, `${width}-goals-filtered`, observations);
                await page.locator('#goal-query').press('Control+A');
                await page.locator('#goal-query').press('Backspace');
                await expect(page.locator('#goal-results article')).toHaveCount(2);
                await page.locator('#goal-extra-filters > summary').press('Enter');
                await page.locator('input[name="archived"]').press('Space');
                await expect(page.locator('#goal-results article')).toHaveCount(3);
                await page.locator('[data-live-reset]').press('Enter');
                await expect(page.locator('#goal-results article')).toHaveCount(2);
                expect(departures).toEqual(oldDepartures);
            }
            if (name === 'reserve') {
                const search = page.locator('#source-search');
                await search.fill(data.potName.slice(0, 30));
                const result = page.locator('#source-search-results [role="option"]');
                await expect(result).toHaveCount(1);
                await expect(result).toContainText(data.potName);
                await expect(result).toContainText(data.bankName);
                await expect(result).toContainText('BRL 300.00');
                const bounds = await result.boundingBox();
                expect(bounds.x).toBeGreaterThanOrEqual(12);
                expect(bounds.x + bounds.width).toBeLessThanOrEqual(width - 12);
                expect(await result.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
                await record(page, info, `${width}-source-results`, observations);
                await search.press('ArrowDown'); await search.press('Enter');
                await expect(page.locator('#id_source')).toHaveValue(data.pot);
                await expect(search).toHaveValue(await page.locator('#id_source option:checked').textContent());
                await expect(page.locator('#id_amount')).toBeVisible();
            }
            if (name === 'signals') {
                const signal = page.locator('#signal-results article').first();
                await signal.locator('button[value="ACK"]').press('Enter');
                await expect(page).toHaveURL(url => url.pathname + url.search === '/planning/signals/?reviewed=1');
                await expect(signal.locator('.status-badge')).toBeVisible();
                await signal.locator('button[value="REOPEN"]').press('Enter');
                await expect(signal.locator('.status-badge')).toHaveCount(0);
            }
        }
        await page.goto('/planning/goals/create/');
        await page.locator('#id_name').fill(data.goalName);
        await page.locator('#id_target_amount').fill('2000');
        await page.locator('#id_reserve_now').press('Space');
        await selectChoice(page.locator('#id_source'), data.pot);
        await page.locator('#id_reserved_amount').fill('300.01');
        await page.locator('button[type="submit"]').filter({hasText: language === 'en' ? /^Save$/ : /^Salvar$/}).press('Enter');
        await expect(page.locator('#id_reserved_amount-error-1')).toBeVisible();
        await record(page, info, `${width}-complete-goal-invalid`, observations);
        await page.locator('#id_reserved_amount').focus();
        await page.keyboard.press('Tab');
        await expect(page.locator('main button[type="submit"]')).toBeFocused();
        const save = await page.locator('main button[type="submit"]').boundingBox();
        expect(save.y).toBeGreaterThanOrEqual(64);
        if (width < 640) {
            const dock = await page.locator('.app-bottom-navigation').boundingBox();
            expect(save.y + save.height).toBeLessThanOrEqual(dock.y);
        }
        await page.screenshot({path: info.outputPath(`${width}-save-focus.png`)});
    }
    await fs.writeFile(info.outputPath('current-layout-observations.json'), JSON.stringify(observations, null, 2));
    expect(observations.filter(row => row.documentWidth > row.width)).toEqual([]);
    await info.attach('current-layout-observations', {body: JSON.stringify(observations, null, 2), contentType: 'application/json'});
});
}
