// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `planning-tools-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {form: {
        csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status()).toBe(302);
}

async function noOverflow(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) {
for (const width of [1280, 390]) {
test(`planning tools keep compact entry, precise overrides and explicit drafts (${width}, ${theme})`, async ({page}, info) => {
    await page.setViewportSize({width, height: 820});
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await signup(page, info);
    await page.goto('/sandbox/');
    const salary = page.locator('#id_gross_salary');
    const month = page.locator('#id_planning_month');
    if (width > 640) {
        const first = await salary.boundingBox();
        const second = await month.boundingBox();
        expect(Math.abs(first.y - second.y)).toBeLessThanOrEqual(2);
        expect(second.x).toBeGreaterThan(first.x + first.width);
    }
    await salary.focus();
    await page.keyboard.type('5000');
    await page.keyboard.press('Tab');
    await expect(month).toBeFocused();
    await month.fill('2026-11');
    // Wait for the selected forecast to replace the form before editing it.
    await expect(page.locator('[data-planning-month]')).toHaveText('November 2026');
    await expect(page.locator('#sandbox-workspace.htmx-settling')).toHaveCount(0);
    await page.locator('#clt-settings > summary').press('Enter');
    await page.locator('#id_clt_dependents').focus();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('1');
    await page.keyboard.press('Tab');
    await expect(page.locator('#id_clt_pension')).toBeFocused();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('25.50');
    const description = page.getByLabel('Fixed expense description', {exact: true}).first();
    await description.focus();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('Utilities');
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Fixed expense unit', {exact: true}).first()).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Fixed expense monthly amount', {exact: true}).first()).toBeFocused();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type('100');
    await page.getByRole('button', {name: 'Remove fixed expense', exact: true}).last().press('Enter');
    await expect(page.locator('[data-variable-row]')).toHaveCount(1);
    await page.locator('#budget-add-variable').press('Enter');
    await expect(page.getByLabel('Fixed expense description', {exact: true}).last()).toBeFocused();
    await page.keyboard.type('Internet');
    await page.getByLabel('Fixed expense monthly amount', {exact: true}).last().fill('50');
    await page.locator('#budget-calculate').press('Enter');
    await expect(page.locator('#scenario-result-title')).toBeVisible();
    await expect(page.locator('#id_clt_pension')).toHaveValue('25.50');
    await expect(page.locator('#clt-settings')).toHaveAttribute('open', '');
    await noOverflow(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: info.outputPath(`monthly-tool-${width}-${theme}.png`), fullPage: true});
    await page.getByText('Save this plan (optional)', {exact: true}).press('Enter');
    const monthlyName = `Monthly ${width} ${theme}`;
    await page.locator('#id_draft_name').fill(monthlyName);
    await page.locator('#scenario-save').press('Enter');
    await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
    await expect(page.locator('#id_gross_salary')).toHaveValue('5000.00');

    await page.goto('/sandbox/simulation/');
    await page.locator('#id_initial_balance').fill('1000');
    await page.locator('#id_start_month').fill('2026-10');
    await page.locator('#id_months').fill('2');
    await page.locator('#id_rate_period').focus();
    await page.keyboard.press('End');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', {name: 'Explain Effective annual rate (%)', exact: true})).toBeFocused();
    await page.keyboard.press('Escape');
    await page.locator('#id_rate').fill('12.123456');
    await page.locator('#id_contribution').fill('100');
    await page.locator('#yield-month-overrides > summary').press('Enter');
    await page.locator('[name="contribution_0"]').focus();
    await page.keyboard.type('0');
    await page.keyboard.press('Tab');
    await expect(page.locator('[name="withdrawal_0"]')).toBeFocused();
    await expect(page.locator('[name="contribution_1"]')).toHaveValue('');
    await expect(page.getByRole('heading', {name: 'Projected result', exact: true})).toBeVisible();
    await expect(page.locator('[data-live-message]')).toHaveText('Simulation updated.');
    await noOverflow(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: info.outputPath(`yield-tool-${width}-${theme}.png`), fullPage: true});
    await page.getByText('Save this scenario', {exact: true}).press('Enter');
    const yieldName = `Yield ${width} ${theme}`;
    await page.locator('#id_draft_name').fill(yieldName);
    await page.locator('#scenario-save').press('Enter');
    await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
    await expect(page.locator('#id_rate')).toHaveValue('12.123456');
    await expect(page.locator('[name="contribution_0"]')).toHaveValue('0.00');
    await expect(page.locator('[name="contribution_1"]')).toHaveValue('');
    await page.goto('/sandbox/drafts/');
    await expect(page.getByRole('link', {name: monthlyName, exact: true})).toBeVisible();
    await expect(page.getByRole('link', {name: yieldName, exact: true})).toBeVisible();
    const choices = page.getByRole('checkbox');
    await choices.nth(0).focus();
    await page.keyboard.press('Space');
    await choices.nth(1).focus();
    await page.keyboard.press('Space');
    await page.getByRole('button', {name: 'Compare selected drafts', exact: true}).press('Enter');
    await expect(page.getByRole('heading', {name: 'Compare drafts', exact: true})).toBeVisible();
    await expect(page.getByRole('region', {name: 'Compare drafts', exact: true})).toContainText('12,123456%');
    await noOverflow(page);
    await page.getByRole('region', {name: 'Compare drafts', exact: true}).focus();
    expect(await page.getByRole('region', {name: 'Compare drafts', exact: true}).evaluate(element => element.matches(':focus-visible'))).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: info.outputPath(`draft-comparison-${width}-${theme}.png`), fullPage: true});
});
}
}
