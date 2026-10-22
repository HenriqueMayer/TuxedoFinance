// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `workspace-review-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Workspace bank'});
    await page.goto('/investments/add/');
    const institution = await page.locator('#id_institution option').last().getAttribute('value');
    await post(page, '/investments/add/', {institution, name: 'Workspace units',
        valuation_mode: 'UNITS', currency: 'BRL', opening_quantity: '2',
        opening_unit_price: '50', opening_date: '2025-01-01'});
    await page.goto('/investments/prices/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    await post(page, '/investments/prices/create/', {asset, date: '2026-10-17',
        unit_price: '118.23456789', source: 'Workspace statement'});
    await page.goto('/investments/prices/');
    const quoteDelete = await page.locator('main').getByRole('link', {name: 'Delete', exact: true}).getAttribute('href');
    const draft = await post(page, '/sandbox/simulation/', {initial_balance: '1000',
        currency: 'BRL', start_month: '2026-10', rate_period: 'monthly', rate: '0.823456',
        months: '2', contribution: '0', withdrawal: '0', action: 'save', draft_name: 'Workspace scenario'});
    return {quoteDelete, draft};
}

async function noOverflow(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) {
    for (const width of [1440, 390]) {
    test(`workspace action groups, aligned fields and recovery remain consistent (${width}, ${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {quoteDelete, draft} = await seed(page, info);
            await page.setViewportSize({width, height: 900});
            await page.goto('/investments/operations/');
            const header = page.locator('main .workspace-header');
            const add = await header.getByRole('link', {name: 'Add investment', exact: true}).boundingBox();
            const operation = await header.getByRole('link', {name: 'New operation', exact: true}).boundingBox();
            expect(Math.abs(add.y - operation.y)).toBeLessThan(2);
            expect(operation.x - add.x - add.width).toBeGreaterThanOrEqual(8);
            expect(operation.x - add.x - add.width).toBeLessThanOrEqual(16);
            await noOverflow(page);

            await page.goto('/sandbox/');
            const salary = page.locator('#id_gross_salary');
            const month = page.locator('#id_planning_month');
            const salaryBox = await salary.boundingBox();
            const monthBox = await month.boundingBox();
            if (width > 767) {
                // Month arrows belong below the month input; they must not push
                // the adjacent salary input away from its row's reading order.
                expect(Math.abs(salaryBox.y - monthBox.y)).toBeLessThanOrEqual(4);
            } else {
                expect(monthBox.y).toBeGreaterThan(salaryBox.y + salaryBox.height);
                expect(Math.abs(monthBox.width - salaryBox.width)).toBeLessThanOrEqual(2);
            }
            await salary.press('Tab');
            await page.keyboard.press('Shift+Tab');
            await expect(salary).toBeFocused();
            expect(await salary.evaluate(element => element.matches(':focus-visible'))).toBe(true);
            await salary.fill('-1');
            await page.locator('#budget-calculate').press('Enter');
            await expect(page.locator('#sandbox-workspace [data-field-error]').first()).toBeVisible();
            await expect(page.locator('#id_gross_salary')).toHaveValue('-1');
            await noOverflow(page);

            const origin = '/planning/goals/?q=Workspace';
            await page.goto(`/planning/goals/create/?next=${encodeURIComponent(origin)}`);
            const cancel = page.locator('main form .form-actions').getByRole('link', {name: 'Cancel', exact: true});
            await expect(cancel).toHaveCSS('border-radius', '8px');
            await cancel.press('Enter');
            await expect(page).toHaveURL(new RegExp('/planning/goals/\\?q=Workspace$'));
            await noOverflow(page);

            for (const [path, destination] of [[quoteDelete, '/investments/prices/'], [`${draft}delete/`, draft]]) {
                await page.goto(path);
                const panel = page.locator('main .surface-panel');
                await expect(panel).toHaveCSS('border-radius', '14px');
                await expect(panel.getByRole('button', {name: /^Delete/})).toBeVisible();
                const cancelDelete = panel.getByRole('link', {name: 'Cancel', exact: true});
                await expect(cancelDelete).toHaveCSS('border-radius', '8px');
                // Cancel uses native navigation; reviewing a confirmation never
                // submits its destructive POST or loses the original destination.
                const response = page.waitForResponse(value => value.request().method() === 'GET'
                    && new URL(value.url()).pathname === destination.split('?')[0]);
                await cancelDelete.press('Enter');
                expect((await response).status()).toBe(200);
                await expect(page).toHaveURL(new RegExp(destination.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
            }
    });
    }
}
