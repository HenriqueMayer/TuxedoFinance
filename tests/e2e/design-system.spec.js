const { test, expect } = require('@playwright/test');

const browserErrors = new WeakMap();

test.beforeEach(async ({ page }) => {
    const errors = [];
    browserErrors.set(page, errors);
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text());
    });
});

test.afterEach(async ({ page }) => {
    expect(browserErrors.get(page)).toEqual([]);
});

async function createAccount(page, testInfo) {
    const username = `e2e-${testInfo.workerIndex}-${Date.now()}`;
    await page.goto('/accounts/signup/');
    await page.getByLabel('Username').fill(username);
    await page.getByLabel('Email').fill(`${username}@example.test`);
    await page.locator('#id_password1').fill('Tuxedo-E2E-2026!');
    await page.locator('#id_password2').fill('Tuxedo-E2E-2026!');
    await page.getByRole('button', { name: 'Sign up' }).click();
    await expect(page).toHaveURL(/\/dashboard\/$/);
}

test('landing keeps concise translated copy and local frontend dependencies', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Understand your cash flow');
    await expect(page.getByText('Tuxedo Finance replaces the single column')).toHaveCount(0);
    await expect(page.locator('script[src*="unpkg.com"]')).toHaveCount(0);
    await expect(page.locator('script[src*="/static/js/vendor/htmx.min.js"]')).toHaveCount(1);

    await page.locator('#language-select-public').selectOption('pt-br');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Entenda seu fluxo de caixa');
    await expect(page.getByText('Understand your cash flow')).toHaveCount(0);
});

test('category CSV is downloaded without replacing the page', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/categories/');

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Export CSV' }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe('categories.csv');
    await expect(page).toHaveURL(/\/categories\/$/);
    await expect(page.getByRole('heading', { name: 'Categories' })).toBeVisible();
});

test('authenticated navigation remains usable at tablet widths', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.setViewportSize({ width: 1024, height: 900 });
    await page.reload();

    await expect(page.getByRole('button', { name: 'Toggle menu' })).toBeVisible();
    await expect(page.locator('nav').getByRole('link', { name: 'Reports' })).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('mobile navigation traps focus and restores it on Escape', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();

    const openButton = page.getByRole('button', { name: 'Toggle menu' });
    await openButton.click();
    const menu = page.locator('#mobile-menu');
    const dialog = page.getByRole('dialog', { name: 'Navigation menu' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(page.locator('header')).toHaveAttribute('inert', '');
    await expect(page.locator('body')).toHaveCSS('overflow', 'hidden');

    for (let index = 0; index < 14; index += 1) {
        await page.keyboard.press('Tab');
        expect(await page.evaluate(() => document.querySelector('#mobile-menu').contains(document.activeElement))).toBe(true);
    }

    await page.keyboard.press('Escape');
    await expect(menu).toHaveAttribute('aria-hidden', 'true');
    await expect(openButton).toBeFocused();
    await expect(page.locator('header')).not.toHaveAttribute('inert', '');
});

test('salary sandbox progresses from one income to variables and comparison without duplicating the page', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/sandbox/clt-pj/');

    await expect(page.getByRole('heading', { name: 'CLT × PJ Sandbox' })).toBeVisible();
    await expect(page.getByRole('button', { name: /I know the gross salary/ })).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByRole('button', { name: /I know the monthly invoice/ })).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByLabel('Gross monthly salary', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Calculate scenario' })).toHaveCount(0);

    await page.getByRole('button', { name: /I know the gross salary/ }).click();
    await expect(page.getByLabel('Gross monthly salary', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Monthly invoice', { exact: true })).toBeHidden();
    await expect(page.getByLabel('Employer tax profile', { exact: true })).toHaveCount(0);
    await page.getByLabel('Gross monthly salary', { exact: true }).fill('6000');

    await page.getByRole('button', { name: 'Add variable' }).click();
    const variableRows = page.locator('[data-variable-row]');
    await expect(variableRows).toHaveCount(1);
    await variableRows.nth(0).locator('input[name="variable_label"]').fill('Temporary');
    await page.getByRole('button', { name: 'Clear estimates' }).click();
    await expect(page.getByLabel('Fixed costs target', { exact: true })).toHaveValue('');
    await expect(variableRows).toHaveCount(0);
    await page.getByLabel('Fixed costs unit', { exact: true }).selectOption('currency');
    await page.getByLabel('Fixed costs target', { exact: true }).fill('1500');
    await page.getByLabel('Emergency reserve target (%)', { exact: true }).fill('10');
    await page.getByLabel('Investments target (%)', { exact: true }).fill('20');

    const grossHelp = page.getByRole('button', { name: 'Explain Gross monthly salary' });
    await grossHelp.hover();
    const grossTooltip = page.getByRole('tooltip').filter({ hasText: 'Salary before INSS' });
    await expect(grossTooltip).toBeVisible();
    const grossTriggerBox = await grossHelp.boundingBox();
    const grossTooltipBox = await grossTooltip.boundingBox();
    expect(Math.min(
        Math.abs(grossTooltipBox.y - (grossTriggerBox.y + grossTriggerBox.height)),
        Math.abs(grossTriggerBox.y - (grossTooltipBox.y + grossTooltipBox.height)),
    )).toBeLessThanOrEqual(12);
    const fixedHelp = page.getByRole('button', { name: 'Explain Fixed costs target' });
    await fixedHelp.click();
    await expect(grossTooltip).toBeHidden();
    await expect(page.getByRole('tooltip').filter({ hasText: 'fixed amount in reais' })).toBeVisible();
    await page.locator('#planning-title').click();
    await expect(page.getByRole('tooltip').filter({ hasText: 'fixed amount in reais' })).toBeHidden();
    await grossHelp.click();
    await page.keyboard.press('Escape');
    await expect(grossTooltip).toBeHidden();
    await expect(grossHelp).toBeFocused();

    await page.getByRole('button', { name: 'Add variable' }).click();
    await expect(variableRows).toHaveCount(1);
    await variableRows.nth(0).locator('input[name="variable_label"]').fill('Leisure');
    await variableRows.nth(0).locator('input[name="variable_value"]').fill('250');
    await page.getByRole('button', { name: 'Calculate scenario' }).click();

    await expect(page.locator('#sandbox-workspace')).toHaveCount(1);
    await expect(page.locator('html')).toHaveCount(1);
    await expect(page.locator('#sandbox-workspace main')).toHaveCount(0);
    await expect(page.locator('#sandbox-workspace footer')).toHaveCount(0);
    await expect(page.locator('body > footer')).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'CLT income after payroll' })).toBeVisible();
    await expect(page.getByText('Net 13th salary', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Pró-labore for comparison', { exact: true })).toHaveValue('1621.00');
    await page.getByRole('button', { name: 'See comparison with PJ' }).click();

    await expect(page.locator('#sandbox-workspace')).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'CLT and PJ side by side' })).toBeVisible();
    const monthlyPlan = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Monthly plan with current inputs' }) });
    await expect(monthlyPlan.getByRole('row', { name: /Leisure/ })).toContainText('250');
    await expect(monthlyPlan.getByRole('row', { name: /Fixed costs target/ })).toContainText('1.500,00');
    await expect(monthlyPlan.getByRole('row', { name: /Fixed costs target/ })).toContainText('%');
    const comparisonHelp = page.getByRole('button', { name: 'Explain Comparable annual package' });
    await comparisonHelp.click();
    const comparisonTooltip = page.getByRole('tooltip').filter({ hasText: 'CLT annual net plus FGTS' });
    await expect(comparisonTooltip).toBeVisible();
    const comparisonTriggerBox = await comparisonHelp.boundingBox();
    const comparisonTooltipBox = await comparisonTooltip.boundingBox();
    expect(Math.min(
        Math.abs(comparisonTooltipBox.y - (comparisonTriggerBox.y + comparisonTriggerBox.height)),
        Math.abs(comparisonTriggerBox.y - (comparisonTooltipBox.y + comparisonTooltipBox.height)),
    )).toBeLessThanOrEqual(12);
    await comparisonHelp.click();
    await expect(comparisonTooltip).toBeHidden();
    await expect(page.getByText('Official rule sources')).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    const mobileDocumentWidthBeforeHelp = await page.evaluate(() => document.documentElement.scrollWidth);
    await comparisonHelp.click();
    await expect(comparisonTooltip).toBeVisible();
    const mobileTooltipBox = await comparisonTooltip.boundingBox();
    expect(mobileTooltipBox.x).toBeGreaterThanOrEqual(12);
    expect(mobileTooltipBox.x + mobileTooltipBox.width).toBeLessThanOrEqual(378);
    expect(mobileTooltipBox.y).toBeGreaterThanOrEqual(12);
    expect(mobileTooltipBox.y + mobileTooltipBox.height).toBeLessThanOrEqual(832);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(mobileDocumentWidthBeforeHelp);
    await comparisonHelp.click();
    await page.setViewportSize({ width: 1280, height: 720 });

    await page.getByRole('button', { name: /I know the monthly invoice/ }).click();
    await expect(page.getByLabel('Monthly invoice', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'CLT and PJ side by side' })).toHaveCount(0);
    await expect(page.getByLabel('Fixed costs unit', { exact: true })).toHaveValue('currency');
    await expect(page.getByLabel('Fixed costs target', { exact: true })).toHaveValue('1500');
    await expect(page.locator('input[name="variable_label"]')).toHaveValue('Leisure');

    await page.getByRole('button', { name: 'Toggle color theme' }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole('heading', { name: 'CLT × PJ Sandbox' })).toBeVisible();
});

test('salary sandbox reveals only the selected PJ inputs', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/sandbox/clt-pj/');
    await page.getByRole('button', { name: /I know the monthly invoice/ }).click();
    await expect(page.getByLabel('Monthly invoice', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Gross monthly salary', { exact: true })).toBeHidden();
    await page.getByLabel('Monthly invoice', { exact: true }).fill('10000');
    await page.getByRole('button', { name: 'Calculate scenario' }).click();
    await expect(page.getByRole('heading', { name: 'PJ income after taxes and costs' })).toBeVisible();
    await expect(page.getByLabel('CLT employer profile for comparison', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'See comparison with CLT' })).toBeVisible();
    await expect(page.locator('#sandbox-workspace')).toHaveCount(1);
});
