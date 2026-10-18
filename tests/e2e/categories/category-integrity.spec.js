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
}

async function prepare(page, info) {
    const username = `category-integrity-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    const ids = {};
    for (const [name, parent] of [['Integrity root', ''], ['Integrity child', 'Integrity root'],
        ['Integrity leaf', 'Integrity child'], ['Independent parent', '']]) {
        await post(page, '/categories/create/', {name, transaction_type: 'EXPENSE', parent_category: ids[parent] || ''});
        await page.goto('/categories/create/');
        ids[name] = await page.locator('#id_parent_category option').filter({hasText: new RegExp(`${name}$`)}).getAttribute('value');
    }
    return {root: ids['Integrity root'], child: ids['Integrity child'], leaf: ids['Integrity leaf'],
        independent: ids['Independent parent']};
}

async function tabToControl(page, control, expectedHelp) {
    let visitedHelp = false;
    for (let step = 0; step < 6; step++) {
        await page.keyboard.press('Tab');
        if (await control.evaluate(element => element === document.activeElement)) {
            if (expectedHelp) expect(visitedHelp).toBe(true);
            await expect(control).toBeFocused();
            return;
        }
        // Contextual question-mark help is a deliberate keyboard stop before
        // its field. Assert it rather than skipping it with programmatic focus.
        const help = page.locator('[data-help-trigger]:focus');
        await expect(help).toHaveCount(1);
        if (expectedHelp) await expect(help).toHaveAttribute('aria-controls', expectedHelp);
        const helpId = await help.getAttribute('aria-controls');
        await expect(help).toHaveAttribute('aria-expanded', 'true');
        await expect(page.locator(`[id="${helpId}"]`)).toBeVisible();
        visitedHelp = true;
    }
    throw new Error('Category control was not reachable through the expected keyboard stops');
}

async function invalidParentPost(page, editPath, parentId) {
    // Forge only the submitted identifier; the actual browser still submits
    // by keyboard and receives the server's normal invalid-form response.
    await page.route(`**${editPath}`, async route => {
        expect(route.request().method()).toBe('POST');
        const body = new URLSearchParams(route.request().postData());
        body.set('parent_category', parentId);
        await route.continue({postData: body.toString()});
    }, {times: 1});
    await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
    await expect(page.locator('#id_parent_category-error-1')).toContainText('Select a valid choice');
    await expect(page.locator('#id_name')).toHaveValue('Renamed integrity root');
    await expect(page).toHaveURL(new RegExp(`${editPath}$`));
}

async function csvRecovery(page) {
    await page.goto('/categories/import/');
    await page.locator('#id_file').setInputFiles({name: 'categories.csv', mimeType: 'text/csv',
        buffer: Buffer.from('name,transaction_type,parent_category\nCSV recovery,EXPENSE,\nBroken,EXPENSE,,extra\n')});
    await page.getByRole('button', {name: 'Import', exact: true}).press('Enter');
    await expect(page.locator('#id_file-error-1')).toContainText('exactly three columns');
    // The valid first row must not have been partially imported.
    await page.goto('/categories/create/');
    await expect(page.locator('#id_parent_category option').filter({hasText: /^CSV recovery$/})).toHaveCount(0);
    await page.goto('/categories/import/');
    await page.locator('#id_file').setInputFiles({name: 'categories.csv', mimeType: 'text/csv',
        buffer: Buffer.from('name,transaction_type,parent_category\nCSV recovery,EXPENSE,\n')});
    await page.getByRole('button', {name: 'Import', exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/categories\/$/);
    await expect(page.locator('main')).toContainText('1 categories imported');
}

for (const theme of ['light', 'dark']) {
    test(`category parent keyboard choices and invalid responses preserve hierarchy (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const ids = await prepare(page, info);
        const edit = `/categories/${ids.root}/edit/`;
        await page.goto(edit);
        for (const id of [ids.root, ids.child, ids.leaf]) {
            await expect(page.locator(`#id_parent_category option[value="${id}"]`)).toHaveCount(0);
        }
        const name = page.locator('#id_name');
        const search = page.locator('#parent-category-search');
        await name.fill('Renamed integrity root');
        await name.focus();
        await tabToControl(page, page.locator('#id_transaction_type'), 'id_transaction_type-help');
        await tabToControl(page, search);
        await page.keyboard.type('Integrity leaf');
        await expect(search.locator('..').getByRole('option')).toHaveCount(0);
        await search.press('Enter');
        await expect(page.locator('#id_parent_category')).toHaveValue('');
        await search.press('Escape');
        await search.fill('Independent parent');
        await search.press('Enter');
        await expect(page.locator('#id_parent_category')).toHaveValue('');
        await search.press('ArrowDown');
        await expect(search.locator('..').getByRole('option')).toHaveAttribute('aria-selected', 'true');
        await expect(search).toBeFocused();
        await search.press('Enter');
        await expect(page.locator('#id_parent_category')).toHaveValue(ids.independent);
        await invalidParentPost(page, edit, ids.leaf);
        await page.screenshot({path: info.outputPath(`category-invalid-${theme}.png`), fullPage: true});
        await search.fill('Independent parent');
        await search.press('ArrowDown');
        await search.press('Enter');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/categories\/$/);
        await page.goto(edit);
        await expect(page.locator('#id_parent_category')).toHaveValue(ids.independent);
        await expect(search).toHaveValue('Independent parent');
        await csvRecovery(page);
    });
}

test('category hierarchy and CSV errors recover through native forms without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false});
    const page = await context.newPage();
    try {
        const ids = await prepare(page, info);
        const edit = `/categories/${ids.root}/edit/`;
        await page.goto(edit);
        const parent = page.locator('#id_parent_category');
        await expect(parent).toBeVisible();
        await expect(page.locator('#parent-category-search')).toHaveCount(0);
        await expect(parent.locator(`option[value="${ids.leaf}"]`)).toHaveCount(0);
        await page.locator('#id_name').fill('Renamed integrity root');
        await parent.selectOption(ids.independent);
        await invalidParentPost(page, edit, ids.leaf);
        await parent.selectOption(ids.independent);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/categories\/$/);
        await page.goto(edit);
        await expect(parent).toHaveValue(ids.independent);
        await csvRecovery(page);
    } finally { await context.close(); }
});
