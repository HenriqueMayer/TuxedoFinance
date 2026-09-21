// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, route, fields) {
    const response = await page.request.get(route);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(route, {
        form: { csrfmiddlewaretoken: csrf, ...fields },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

async function prepare(page, testInfo) {
    const username = `category-tree-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    for (const name of ['Living costs', 'Transport', 'Salary']) {
        await post(page, '/categories/create/', { name, transaction_type: 'EXPENSE' });
    }
    await page.goto('/categories/create/');
    const optionValue = text => page.locator('#id_parent_category option')
        .filter({ hasText: new RegExp(`^${text}$`) }).getAttribute('value');
    const living = await optionValue('Living costs');
    const transport = await optionValue('Transport');
    const salary = await optionValue('Salary');
    await post(page, '/categories/create/', { name: 'Heating', transaction_type: 'EXPENSE', parent_category: living });
    await post(page, '/categories/create/', { name: 'Water', transaction_type: 'EXPENSE', parent_category: living });
    await post(page, '/categories/create/', { name: 'Fuel', transaction_type: 'EXPENSE', parent_category: transport });
    await page.goto('/categories/create/');
    const heating = await optionValue('Living costs > Heating');
    const water = await optionValue('Living costs > Water');
    const fuel = await optionValue('Transport > Fuel');
    await post(page, '/categories/create/', { name: 'Solar servicing', transaction_type: 'EXPENSE', parent_category: heating });
    await page.goto('/categories/create/');
    const solar = await optionValue('Heating > Solar servicing');
    await page.goto('/categories/');
    return { living, transport, salary, heating, water, fuel, solar };
}

function toggle(page, id) {
    return page.locator(`button[data-category-toggle][aria-controls="category-children-${id}"]`);
}
function children(page, id) { return page.locator(`#category-children-${id}`); }
function edit(page, id) { return page.locator(`a[href="/categories/${id}/edit/"]`); }
async function allExpanded(page, ids) {
    for (const id of [ids.living, ids.heating, ids.transport]) {
        await expect(toggle(page, id)).toHaveAttribute('aria-expanded', 'true');
        await expect(children(page, id)).toBeVisible();
    }
    for (const id of Object.values(ids)) await expect(edit(page, id)).toBeVisible();
}

async function screenshot(page, testInfo, name) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.mouse.move(0, 0);
    await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

for (const [theme, width] of [['light', 1440], ['dark', 390]]) {
    test(`category groups support individual and global keyboard controls (${theme}, ${width}px)`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const ids = await prepare(page, testInfo);
        await expect(page.locator('[data-category-tree]')).toBeVisible();
        await allExpanded(page, ids);

        const living = toggle(page, ids.living);
        await living.click();
        await expect(living).toHaveAttribute('aria-expanded', 'false');
        await expect(living).toBeFocused();
        await expect(children(page, ids.living)).toBeHidden();
        await expect(edit(page, ids.fuel)).toBeVisible();
        await living.press('Enter');
        await expect(living).toHaveAttribute('aria-expanded', 'true');
        await expect(edit(page, ids.solar)).toBeVisible();
        await living.press('Space');
        await expect(children(page, ids.living)).toBeHidden();
        await living.press('Space');
        await expect(children(page, ids.living)).toBeVisible();

        const heating = toggle(page, ids.heating);
        await heating.click();
        await expect(edit(page, ids.solar)).toBeHidden();
        await expect(edit(page, ids.water)).toBeVisible();
        await expect(living).toHaveAttribute('aria-expanded', 'true');

        const collapse = page.locator('button[data-category-action="collapse"]');
        const expand = page.locator('button[data-category-action="expand"]');
        await collapse.focus();
        await page.keyboard.press('Enter');
        await expect(collapse).toBeFocused();
        for (const id of [ids.living, ids.heating, ids.transport]) {
            await expect(toggle(page, id)).toHaveAttribute('aria-expanded', 'false');
        }
        await expect(edit(page, ids.solar)).toBeHidden();
        await expect(edit(page, ids.fuel)).toBeHidden();
        await expect(edit(page, ids.salary)).toBeVisible();
        await expand.focus();
        await page.keyboard.press('Space');
        await expect(expand).toBeFocused();
        await allExpanded(page, ids);

        // Row actions do not act as disclosure triggers.
        await page.locator(`a[href="/categories/create/?parent=${ids.living}"]`).click();
        await expect(page).toHaveURL(new RegExp(`/categories/create/\\?parent=${ids.living}$`));
        await expect(page.locator('#id_parent_category')).toHaveValue(ids.living);
        await page.goBack();
        await allExpanded(page, ids);
        const options = page.locator('summary[aria-label="More options: Living costs"]');
        await options.click();
        await expect(options.locator('..')).toHaveAttribute('open', '');
        await expect(living).toHaveAttribute('aria-expanded', 'true');
        await expect(edit(page, ids.heating)).toBeVisible();
        await page.keyboard.press('Escape');
        await living.click();
        await edit(page, ids.living).click();
        await expect(page).toHaveURL(new RegExp(`/categories/${ids.living}/edit/$`));
        await expect(page.locator('#id_name')).toHaveValue('Living costs');
        await page.goBack();
        await expect(living).toHaveAttribute('aria-expanded', 'false');
        await expect(edit(page, ids.heating)).toBeHidden();
        await expect(edit(page, ids.fuel)).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await screenshot(page, testInfo, `category-groups-${theme}.png`);
        if (theme === 'dark') {
            await page.context().addCookies([{ name: 'django_language', value: 'pt-br', url: testInfo.project.use.baseURL }]);
            await page.reload();
            await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
            await expect(page.getByRole('button', { name: 'Recolher tudo', exact: true })).toBeVisible();
            await expect(page.getByRole('button', { name: 'Expandir tudo', exact: true })).toBeVisible();
            await living.click();
            await expect(children(page, ids.living)).toBeHidden();
            await screenshot(page, testInfo, 'category-groups-pt-br-dark-mobile.png');
        }
    });
}

test('category filtering exposes matching descendants and history restores disclosure state', async ({ page }, testInfo) => {
    const ids = await prepare(page, testInfo);
    await page.evaluate(() => { window.categoryHistoryMarker = 'same-document'; });
    await page.locator('#filter-search').fill('Heating');
    await page.getByRole('button', { name: 'Filter', exact: true }).click();
    await expect(page).toHaveURL(/q=Heating/);
    expect(await page.evaluate(() => window.categoryHistoryMarker)).toBe('same-document');
    await expect(edit(page, ids.heating)).toBeVisible();
    await expect(page.getByText('Subcategory of Living costs', { exact: true })).toBeVisible();
    await expect(edit(page, ids.living)).toHaveCount(0);
    await expect(edit(page, ids.solar)).toHaveCount(0);
    await expect(page.locator('button[data-category-toggle]')).toHaveCount(0);

    await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
    await allExpanded(page, ids);
    const living = toggle(page, ids.living);
    await living.click();
    await expect(edit(page, ids.heating)).toBeHidden();
    await page.locator('main nav').getByRole('link', { name: 'Transactions', exact: true }).click();
    await expect(page).toHaveURL(/\/transactions\/$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/categories\/$/);
    await expect(living).toHaveAttribute('aria-expanded', 'false');
    await expect(edit(page, ids.heating)).toBeHidden();
    await living.press('Enter');
    await expect(edit(page, ids.solar)).toBeVisible();
    await living.press('Space');
    await expect(edit(page, ids.heating)).toBeHidden();
    await page.reload();
    await allExpanded(page, ids);
});

test('all category levels stay readable and searchable without JavaScript on mobile', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    try {
        const ids = await prepare(page, testInfo);
        for (const id of Object.values(ids)) await expect(edit(page, id)).toBeVisible();
        await expect(page.locator('button[data-category-toggle]')).toHaveCount(3);
        for (const button of await page.locator('button[data-category-toggle], button[data-category-action]').all()) {
            await expect(button).toBeHidden();
        }
        const solarName = page.locator(`#category-name-${ids.solar}`);
        await expect(solarName).toBeVisible();
        await expect(solarName).toContainText('Solar servicing');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await screenshot(page, testInfo, 'category-groups-nojs-mobile.png');
        await edit(page, ids.solar).click();
        await expect(page.locator('#id_name')).toHaveValue('Solar servicing');
        await page.goBack();
        await page.locator('#filter-search').fill('Solar servicing');
        await page.getByRole('button', { name: 'Filter', exact: true }).click();
        await expect(edit(page, ids.solar)).toBeVisible();
        await expect(edit(page, ids.heating)).toHaveCount(0);
        await expect(page.getByText('Subcategory of Heating', { exact: true })).toBeVisible();
    } finally {
        await context.close();
    }
});
