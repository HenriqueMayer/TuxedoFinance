// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
test.setTimeout(60000);

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(302);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `tools-audit-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    const monthly = await post(page, '/sandbox/', {action: 'save', draft_name: 'Monthly household plan',
        gross_salary: '7000', planning_month: '2026-10', clt_dependents: '1',
        clt_pension: '25.50', clt_transport: '100', clt_food: '20', clt_health: '70', clt_other: '0',
        variable_label: 'A complete fixed expense', variable_type: 'currency', variable_value: '150'});
    const yieldDraft = await post(page, '/sandbox/simulation/', {action: 'save', draft_name: 'Long yield scenario',
        initial_balance: '1000', currency: 'BRL', start_month: '2026-10', months: '120', rate_period: 'monthly',
        rate: '0.123456', contribution: '10', withdrawal: '0'});
    const third = await post(page, '/sandbox/simulation/', {action: 'save', draft_name: 'Annual yield scenario',
        initial_balance: '1000', currency: 'USD', start_month: '2026-10', months: '12', rate_period: 'annual',
        rate: '2.123456', contribution: '0', withdrawal: '0'});
    return {monthly, yieldDraft, third};
}

async function capture(page, info, name, owner) {
    await owner.scrollIntoViewIfNeeded();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({path: info.outputPath(`${name}.png`)});
    expect.soft(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name).toBe(true);
}

async function settled(page) {
    await expect(page.locator('.htmx-request, .htmx-swapping, .htmx-settling')).toHaveCount(0);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

for (const theme of ['light', 'dark']) {
for (const width of [1280, 390, 360]) {
test(`planning tools expose usable actions in short viewports (${width}, ${theme})`, async ({page}, info) => {
    await page.setViewportSize({width, height: width < 640 ? 560 : 800});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    page.on('dialog', dialog => dialog.accept());
    const {monthly, yieldDraft} = await seed(page, info);
    const portuguese = width < 640;
    await page.context().addCookies([{name: 'django_language', value: portuguese ? 'pt-br' : 'en', url: info.project.use.baseURL}]);
    await page.goto(monthly);
    await capture(page, info, '00-draft-toolbar', page.locator('[data-draft-toolbar]'));
    expect((await page.locator('#id_draft_name').boundingBox()).width, 'Draft name remains an editable full field').toBeGreaterThanOrEqual(160);
    await capture(page, info, '01-salary-month', page.locator('#id_planning_month'));
    await page.locator('#budget-next-month').press('Enter');
    await expect(page.locator('#id_planning_month')).toHaveValue('2026-11');
    await settled(page);
    await page.locator('#budget-previous-month').press('Space');
    await expect(page.locator('#id_planning_month')).toHaveValue('2026-10');
    await settled(page);
    // Saved payroll parameters intentionally reopen their native disclosure.
    if (!(await page.locator('#clt-settings').evaluate(element => element.open))) {
        await page.locator('#clt-settings > summary').press('Enter');
    }
    await page.locator('#id_clt_other').focus();
    await expect(page.locator('#id_clt_other')).toBeFocused();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('12.34');
    await expect(page.locator('#id_clt_other')).toHaveValue('12.34');
    await capture(page, info, '02-clt-last-field', page.locator('#id_clt_other'));
    await page.locator('#budget-tax-bands').press('Enter');
    await expect(page.locator('#clt-tax-brackets')).toBeVisible();
    await capture(page, info, '03-tax-brackets', page.locator('#clt-tax-brackets'));
    await page.locator('#budget-add-variable').press('Enter');
    await page.keyboard.type('Another complete fixed expense');
    await page.getByRole('button', {name: portuguese ? 'Remover despesa fixa' : 'Remove fixed expense', exact: true}).last().press('Enter');
    await expect(page.locator('[data-variable-row]')).toHaveCount(1);
    await capture(page, info, '04-expense-row', page.locator('[data-variable-row]'));

    await page.goto(yieldDraft);
    await page.locator('#yield-month-overrides > summary').press('Enter');
    await page.locator('[name="contribution_119"]').focus();
    await page.keyboard.type('0');
    await page.keyboard.press('Tab');
    await expect(page.locator('[name="withdrawal_119"]')).toBeFocused();
    await capture(page, info, '05-last-month-override', page.locator('[name="withdrawal_119"]'));
    const finalBounds = await page.locator('[name="withdrawal_119"]').boundingBox();
    const dock = await page.locator('.app-bottom-navigation').boundingBox();
    if (width < 640) expect.soft(finalBounds.y + finalBounds.height, 'Last monthly override stays above fixed navigation').toBeLessThanOrEqual(dock.y);
    await page.getByRole('button', {name: portuguese ? 'Calcular' : 'Calculate', exact: true}).press('Enter');
    await expect(page.locator('#simulation-result')).toContainText(portuguese ? 'Resultado projetado' : 'Projected result');
    await page.locator('#yield-monthly-results > summary').press('Enter');
    await capture(page, info, '06-monthly-breakdown', page.getByRole('region', {name: portuguese ? 'Detalhamento mensal' : 'Monthly breakdown', exact: true}));
    await page.locator('#scenario-save').press('Enter');
    await expect(page).toHaveURL(url => url.pathname === yieldDraft);

    await page.goto('/sandbox/drafts/');
    await capture(page, info, '07-saved-drafts', page.getByRole('region', {name: portuguese ? 'Rascunhos salvos' : 'Saved drafts', exact: true}));
    await page.getByRole('button', {name: portuguese ? 'Duplicar' : 'Duplicate', exact: true}).first().press('Enter');
    await expect(page.locator('#id_draft_name')).toHaveValue(/^(Copy of|Cópia de) /);
    const copied = new URL(page.url()).pathname;
    await page.goto('/sandbox/drafts/');
    for (const checkbox of (await page.getByRole('checkbox').all()).slice(0, 3)) {
        await checkbox.focus();
        await page.keyboard.press('Space');
    }
    await page.getByRole('button', {name: portuguese ? 'Comparar rascunhos selecionados' : 'Compare selected drafts', exact: true}).press('Enter');
    await capture(page, info, '08-compare-three', page.getByRole('region', {name: portuguese ? 'Comparar rascunhos' : 'Compare drafts', exact: true}));
    await expect(page.locator('main table thead th')).toHaveCount(4);
    await page.goto(`${copied}delete/`);
    await capture(page, info, '09-delete-confirmation', page.getByRole('button', {name: portuguese ? 'Excluir rascunho' : 'Delete draft', exact: true}));
    await page.getByRole('link', {name: portuguese ? 'Cancelar' : 'Cancel', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => url.pathname === copied);
    await page.goto(`${copied}delete/`);
    await page.getByRole('button', {name: portuguese ? 'Excluir rascunho' : 'Delete draft', exact: true}).press('Enter');
    await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
    await expect(page.getByRole('checkbox')).toHaveCount(3);
});
}
}

test.describe('small planning tools without JavaScript', () => {
    test.use({javaScriptEnabled: false, viewport: {width: 360, height: 560}});
    test('native draft name, explicit save and delete cancellation remain usable', async ({page}, info) => {
        const {monthly} = await seed(page, info);
        await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: info.project.use.baseURL}]);
        await page.goto(monthly);
        const name = page.locator('#id_draft_name');
        await name.scrollIntoViewIfNeeded();
        expect((await name.boundingBox()).width).toBeGreaterThanOrEqual(160);
        await name.focus();
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('Plano mensal revisado');
        await page.locator('#scenario-save').press('Enter');
        await expect(name).toHaveValue('Plano mensal revisado');
        await expect(page).toHaveURL(url => url.pathname === monthly);
        await page.getByRole('link', {name: 'Excluir rascunho', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === `${monthly}delete/`);
        await page.getByRole('link', {name: 'Cancelar', exact: true}).press('Enter');
        await expect(name).toHaveValue('Plano mensal revisado');
        await page.screenshot({path: info.outputPath('native-saved-draft-mobile.png')});
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
});
