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

async function prepare(page, info) {
    const username = `category-buttons-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    });
    // This suite only runs inside the official executor's disposable database.
    await post(page, '/categories/delete-all/');
    await post(page, '/categories/create/', {name: 'Household', transaction_type: 'EXPENSE'});
    await page.goto('/categories/create/');
    const parent = await page.locator('#id_parent_category option').filter({hasText: /^Household$/}).getAttribute('value');
    await post(page, '/categories/create/', {name: 'Utility bills', transaction_type: 'EXPENSE', parent_category: parent});
    await post(page, '/categories/create/', {name: 'Salary', transaction_type: 'INCOME'});
    await post(page, '/categories/create/', {name: 'Review later'});
    await page.goto('/categories/');
    return {parent};
}

function radio(page, id) { return page.locator(`#filter-${id}`); }

async function expectStableValues(page) {
    const values = await page.locator('#category-filters input[type="radio"]').evaluateAll(inputs =>
        inputs.map(input => [input.id, input.value]));
    expect(values).toEqual([
        ['filter-level-all', ''], ['filter-level-top', 'top'], ['filter-level-sub', 'sub'],
        ['filter-type-all', ''], ['filter-type-income', 'INCOME'],
        ['filter-type-expense', 'EXPENSE'], ['filter-type-unclassified', 'unclassified'],
    ]);
    await expect(page.locator('#filter-level input:checked')).toHaveCount(1);
    await expect(page.locator('#filter-type input:checked')).toHaveCount(1);
}

async function expectQuery(page, params) {
    await expect(page).toHaveURL(url => url.pathname === '/categories/' &&
        [...url.searchParams.entries()].length === Object.keys(params).length &&
        Object.entries(params).every(([key, value]) => url.searchParams.get(key) === value));
    await expect(page.locator('#category-results')).not.toHaveAttribute('aria-busy', 'true');
}

for (const theme of ['light', 'dark']) {
    for (const width of [1440, 320]) {
        test(`visible category filter buttons combine keyboard choices, search, Clear and history (${theme}, ${width}px)`, async ({page}, info) => {
            await page.setViewportSize({width, height: 900});
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            const {parent} = await prepare(page, info);
            const search = page.locator('#filter-search');
            await expect(page.locator('#category-extra-filters')).toHaveCount(0);
            await expect(page.locator('#filter-level')).toBeVisible();
            await expect(page.locator('#filter-type')).toBeVisible();
            await expect(radio(page, 'level-all')).toBeChecked();
            await expect(radio(page, 'type-all')).toBeChecked();
            await expectStableValues(page);
            await expect(page.locator('#category-results-status')).toHaveText('4 categories');

            await radio(page, 'level-all').focus();
            await page.keyboard.press('Space');
            await page.keyboard.press('ArrowRight');
            await expectQuery(page, {level: 'top'});
            await expect(radio(page, 'level-top')).toBeChecked();
            await expect(radio(page, 'level-top')).toBeFocused();
            await page.keyboard.press('ArrowRight');
            await expectQuery(page, {level: 'sub'});
            await expect(radio(page, 'level-sub')).toBeChecked();
            await expect(radio(page, 'level-sub')).toBeFocused();
            expect(await radio(page, 'level-sub').evaluate(input => {
                const style = getComputedStyle(input);
                const label = input.closest('label');
                return input.matches(':focus-visible') && (parseFloat(style.outlineWidth) > 0 ||
                    (label && getComputedStyle(label).outlineStyle !== 'none'));
            }), 'Native arrow navigation preserves a visible keyboard focus').toBe(true);
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(page.locator(`[data-category-group="${parent}"]`)).toHaveAttribute('data-category-context', '');

            await search.focus();
            await page.keyboard.type('Utility', {delay: 20});
            await expectQuery(page, {q: 'Utility', level: 'sub'});
            await expect(search).toBeFocused();
            expect(await search.evaluate(input => input.selectionStart)).toBe(7);
            await radio(page, 'type-all').focus();
            await page.keyboard.press('ArrowRight');
            await expectQuery(page, {q: 'Utility', level: 'sub', type: 'INCOME'});
            await expect(page.getByText('No matching categories', {exact: true})).toBeVisible();
            await page.keyboard.press('ArrowRight');
            await expectQuery(page, {q: 'Utility', level: 'sub', type: 'EXPENSE'});
            await expect(radio(page, 'type-expense')).toBeFocused();
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(page.getByRole('link', {name: 'New category', exact: true})).toHaveAttribute('href', /next=%2Fcategories%2F%3Fq%3DUtility%26level%3Dsub%26type%3DEXPENSE/);
            await expectStableValues(page);

            await page.locator('#category-clear-filters').press('Enter');
            await expectQuery(page, {});
            await expect(search).toHaveValue('');
            await expect(search).toBeFocused();
            await expect(radio(page, 'level-all')).toBeChecked();
            await expect(radio(page, 'type-all')).toBeChecked();
            await expectStableValues(page);
            await page.goBack();
            await expectQuery(page, {q: 'Utility', level: 'sub', type: 'EXPENSE'});
            await expect(search).toHaveValue('Utility');
            await expect(radio(page, 'level-sub')).toBeChecked();
            await expect(radio(page, 'type-expense')).toBeChecked();
            await expectStableValues(page);
            await page.goForward();
            await expectQuery(page, {});
            await expect(radio(page, 'level-all')).toBeChecked();
            await expect(radio(page, 'type-all')).toBeChecked();
            await expectStableValues(page);

            // Restoring an entry must not mutate native choice values or prevent
            // the next selection from composing with the restored GET state.
            await radio(page, 'type-unclassified').press('Space');
            await expectQuery(page, {type: 'unclassified'});
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(page.locator('#category-results')).toContainText('Review later');
            if (width === 320) {
                for (const label of await page.locator('#category-filters .entry-segment-options label').all()) {
                    const box = await label.boundingBox();
                    expect(box.height).toBeGreaterThanOrEqual(44);
                    expect(box.x).toBeGreaterThanOrEqual(0);
                    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
                }
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.locator('#category-clear-filters').press('Enter');
            await expectQuery(page, {});
            await page.locator('main h1').click();
            await page.locator('#category-filters').screenshot({path: info.outputPath(`category-filter-buttons-${theme}-${width}.png`)});
        });
    }
}

test('Portuguese category choices preserve canonical identifiers and localized context', async ({page}, info) => {
    await page.setViewportSize({width: 320, height: 900});
    await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
    const {parent} = await prepare(page, info);
    await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: info.project.use.baseURL}]);
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
    await expect(page.getByRole('group', {name: 'Nível', exact: true})).toBeVisible();
    await expect(page.getByRole('radio', {name: 'Todos os níveis', exact: true})).toBeChecked();
    await radio(page, 'level-sub').press('Space');
    await radio(page, 'type-expense').press('Space');
    await expectQuery(page, {level: 'sub', type: 'EXPENSE'});
    await expect(page.locator('#category-results-status')).toHaveText('1 categoria');
    await expect(page.locator(`[data-category-group="${parent}"]`)).toHaveAttribute('data-category-context', '');
    await expect(page.getByRole('radio', {name: 'Despesa', exact: true})).toBeChecked();
    await expectStableValues(page);
    await page.locator('main h1').click();
    await page.locator('#category-filters').screenshot({path: info.outputPath('category-filter-buttons-pt-br-dark-320.png')});
    await radio(page, 'type-unclassified').press('Space');
    await expectQuery(page, {level: 'sub', type: 'unclassified'});
    await expect(page.getByRole('radio', {name: 'Sem classificação', exact: true})).toBeChecked();
    await expectStableValues(page);
});

test('category choice buttons retain a complete native GET fallback without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 320, height: 900}});
    const page = await context.newPage();
    try {
        const {parent} = await prepare(page, info);
        const search = page.locator('#filter-search');
        await search.fill('Utility');
        await radio(page, 'level-sub').press('Space');
        await radio(page, 'type-expense').press('Space');
        await expect(page).toHaveURL(/\/categories\/$/);
        await page.getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expectQuery(page, {q: 'Utility', level: 'sub', type: 'EXPENSE'});
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await expect(page.locator(`[data-category-group="${parent}"]`)).toHaveAttribute('data-category-context', '');
        await expect(radio(page, 'level-sub')).toBeChecked();
        await expect(radio(page, 'type-expense')).toBeChecked();
        await expectStableValues(page);
        await page.locator('#category-clear-filters').press('Enter');
        await expectQuery(page, {});
        await expect(radio(page, 'level-all')).toBeChecked();
        await expect(radio(page, 'type-all')).toBeChecked();
        await expectStableValues(page);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally { await context.close(); }
});
