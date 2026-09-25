// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `history-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {
        form: {csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

for (const theme of ['light', 'dark']) {
    test(`browser Back restores an edited form and confirmation can cancel departure (${theme})`, async ({page}, info) => {
        await signup(page, info);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.goto('/transactions/');
        await page.getByRole('link', {name: 'New Transaction', exact: true}).first().click();
        await expect(page).toHaveURL(/\/transactions\/create\/$/);
        const formUrl = page.url();
        const title = page.locator('#id_title');
        await title.fill('Unsent transaction');
        await title.focus();
        await expect(page.locator('[data-previous-workspace]')).toHaveCount(0);
        page.once('dialog', dialog => dialog.dismiss());
        await page.getByRole('link', {name: 'Cancel', exact: true}).click();
        await expect(page).toHaveURL(formUrl);
        await expect(title).toHaveValue('Unsent transaction');
        const top = await page.evaluate(() => window.scrollY);
        page.once('dialog', dialog => dialog.accept());
        await page.getByRole('link', {name: 'Cancel', exact: true}).click();
        await expect(page).toHaveURL(/\/transactions\/$/);
        await page.goBack();
        await expect(page).toHaveURL(formUrl);
        await expect(title).toHaveValue('Unsent transaction');
        await expect(title).toBeFocused();
        expect(Math.abs(await page.evaluate(() => window.scrollY) - top)).toBeLessThan(4);
        await expect(page.locator('[data-workspace-restored]')).toBeVisible();
        await page.screenshot({path: info.outputPath(`history-${theme}.png`)});
    });
}

test('browser Back confirmation preserves edited form when canceled', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/transactions/');
    await page.getByRole('link', {name: 'New Transaction', exact: true}).first().click();
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await page.locator('#id_title').fill('Stay here');
    page.once('dialog', dialog => dialog.dismiss());
    await page.goBack();
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await expect(page.locator('#id_title')).toHaveValue('Stay here');
    page.once('dialog', dialog => dialog.accept());
    await page.goBack();
    await expect(page).toHaveURL(/\/transactions\/$/);
});

test('browser history restores repeated simulation rows and warns on leaving a result', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/sandbox/simulation/');
    await page.locator('#id_months').fill('24');
    await page.locator('summary').filter({hasText: 'Change individual months'}).click();
    await page.getByRole('button', {name: 'Update month rows'}).click();
    await expect(page.locator('[name="contribution_23"]')).toHaveCount(1);
    await page.locator('summary').filter({hasText: 'Change individual months'}).click();
    await page.locator('[name="contribution_23"]').fill('456.78');
    await page.locator('#id_initial_balance').fill('1000');
    await page.locator('#id_rate').fill('1');
    await expect(page.locator('#simulation-result .panel-heading')).toBeVisible();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('link', {name: 'Saved drafts', exact: true}).click();
    await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
    const snapshot = await page.evaluate(() => JSON.parse(sessionStorage.getItem('tuxedo.history-workspace.v2')));
    expect(snapshot.entries['/sandbox/simulation/'].forms.some(form => form.fields.some(field =>
        field.name === 'contribution_23' && field.value === '456.78'))).toBe(true);
    await page.goBack();
    await expect(page.locator('[data-workspace-restored]')).toBeVisible();
    await expect(page.locator('#id_months')).toHaveValue('24');
    await expect(page.locator('[name="contribution_23"]')).toHaveValue('456.78');
});

test('history snapshots stay in the current tab and user scope', async ({page, context}, info) => {
    await signup(page, info);
    await page.goto('/transactions/');
    await page.getByRole('link', {name: 'New Transaction', exact: true}).first().click();
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await page.locator('#id_title').fill('Private draft');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('link', {name: 'Cancel', exact: true}).click();
    const state = await page.evaluate(() => JSON.parse(sessionStorage.getItem('tuxedo.history-workspace.v2')));
    expect(state.entries['/transactions/create/'].forms.some(form => form.fields.some(field => field.value === 'Private draft'))).toBe(true);
    const other = await context.newPage();
    await other.goto('/transactions/');
    expect(await other.evaluate(() => sessionStorage.getItem('tuxedo.history-workspace.v2'))).toBeNull();
    await other.close();
});

test('native page departure warns before discarding an edited form', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/transactions/create/');
    await page.locator('#id_title').fill('Not saved');
    let warned = false;
    page.once('dialog', async dialog => {
        warned = dialog.type() === 'beforeunload';
        await dialog.dismiss();
    });
    await page.goto('/dashboard/').catch(() => null);
    expect(warned).toBe(true);
    await expect(page).toHaveURL(/\/transactions\/create\/$/);
    await expect(page.locator('#id_title')).toHaveValue('Not saved');
    page.once('dialog', dialog => dialog.accept());
    await page.goto('/dashboard/');
    await expect(page).toHaveURL(/\/dashboard\/$/);
});
