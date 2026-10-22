// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(result.status(), await result.text()).toBe(302);
    return result.headers().location;
}

async function seed(page, info) {
    const username = `plan-presentation-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Presentation bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Available cash', currency: 'BRL',
        opening_balance: '1000', opening_date: '2020-01-01', planning_enabled: 'on'});
    await page.goto('/planning/goals/create/');
    const source = await page.locator('#id_source option').filter({hasText: 'Available cash'}).getAttribute('value');
    const goal = await post(page, '/planning/goals/create/', {name: 'Family reserve', currency: 'BRL',
        target_amount: '500', target_date: '2030-12-31', reserve_now: 'on', source, reserved_amount: '200'});
    const longName = 'Planejamento' + 'x'.repeat(75);
    await post(page, '/planning/goals/create/', {name: longName, currency: 'BRL', target_amount: '250'});
    return {goal, longName};
}

for (const language of ['en', 'pt-br']) for (const theme of ['light', 'dark']) {
    test(`planning summaries and divided goals remain readable (${language}, ${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const data = await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        for (const width of [1440, 320]) {
            await page.setViewportSize({width, height: 844});
            await page.goto('/planning/');
            await expect(page.locator('[data-monthly-available]')).toContainText(/BRL 800[,.]00/);
            await expect(page.locator('.monthly-outlook-metrics')).toContainText(/BRL 200[,.]00/);
            await expect(page.locator('[data-planning-navigation]')).toHaveCSS('margin-bottom', '24px');
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path: info.outputPath(`month-${language}-${theme}-${width}.png`), fullPage: true});
            await page.locator('[data-planning-navigation] a[href="/planning/goals/"]').press('Enter');
            await expect(page).toHaveURL(/\/planning\/goals\/$/);
            await expect(page.locator('.goal-row')).toHaveCount(2);
            const funded = page.locator('.goal-row').filter({hasText: 'Family reserve'});
            await expect(funded.locator('progress')).toHaveAttribute('value', '40');
            await expect(funded).toContainText(/BRL 200[,.]00/);
            await expect(page.locator('.goal-row').filter({hasText: data.longName})).toBeVisible();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path: info.outputPath(`goals-${language}-${theme}-${width}.png`), fullPage: true});
            const search = page.locator('#goal-query');
            await search.focus(); await search.pressSequentially('No matching goal');
            await expect(page.locator('#goal-results')).toContainText(language === 'en'
                ? 'No goals match these filters.' : 'Nenhuma meta corresponde a estes filtros.');
            await expect(page.locator('.goal-row')).toHaveCount(0);
            await expect(search).toBeFocused();
            await search.press('ControlOrMeta+A'); await search.press('Backspace');
            await expect(page.locator('.goal-row')).toHaveCount(2);
            const link = funded.locator('.investment-name');
            await link.focus();
            const bounds = await link.boundingBox();
            expect(bounds.height).toBeGreaterThanOrEqual(44);
            await link.press('Enter');
            await expect(page).toHaveURL(data.goal);
            await expect(page.locator('.monthly-outlook .money-highlight')).toContainText(/BRL 200[,.]00/);
        }
        expect(errors).toEqual([]);
    });
}
