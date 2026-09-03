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

async function createMonetaryInvestment(page, testInfo) {
    await createAccount(page, testInfo);

    await page.goto('/banking/create/');
    await page.getByLabel('Name').fill('Investment bank');
    await page.getByRole('button', { name: 'Save' }).click();

    await page.goto('/investments/products/create/');
    await page.getByLabel('Bank').selectOption({ label: 'Investment bank' });
    await page.getByLabel('Name').fill('Savings');
    await page.getByRole('button', { name: 'Save' }).click();

    await page.goto('/investments/assets/create/');
    await page.getByLabel('Name').fill('Savings pot');
    await page.getByLabel('Code').fill('POT');
    await page.getByLabel('Asset class').selectOption('LIQUIDITY');
    await page.getByLabel('Currency').selectOption('BRL');
    await page.getByLabel('How this asset is valued').selectOption('MONETARY');
    await page.getByRole('spinbutton', { name: /^Opening balance/ }).fill('1000');
    await page.getByLabel('Opening balance product').selectOption({ label: 'Investment bank - Savings' });
    await page.getByRole('button', { name: 'Save' }).click();
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

test('monetary yield previews a final balance and stores only the calculated yield', async ({ page }, testInfo) => {
    await createMonetaryInvestment(page, testInfo);
    await page.goto('/investments/create/');

    await page.getByLabel('Product destination').selectOption({ label: 'Investment bank - Savings' });
    await page.getByRole('combobox', { name: /^Asset/ }).selectOption({ label: 'Savings pot (POT)' });
    await page.getByLabel('Type').selectOption('YIELD');
    await page.getByLabel('Date').fill('2026-09-02');
    await page.getByRole('radio', { name: 'Use the final balance' }).check();
    await page.getByRole('spinbutton', { name: 'New investment balance' }).fill('1200');

    const preview = page.locator('#yield-preview');
    await expect(preview.getByText('Previous balance')).toBeVisible();
    await expect(preview.getByText('Calculated yield')).toBeVisible();
    await expect(preview).toContainText('200,00');
    await expect(page.getByLabel('Investment amount')).toBeHidden();

    await page.getByRole('radio', { name: 'Enter the yield amount' }).check();
    await expect(page.getByLabel('Investment amount')).toBeVisible();
    await expect(page.getByLabel('New investment balance')).toBeHidden();

    await page.getByRole('radio', { name: 'Use the final balance' }).check();
    await page.getByRole('spinbutton', { name: 'New investment balance' }).fill('1200');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('Balance: BRL 1.200,00')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('salary sandbox supports a complete manual calculation without comparisons', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/sandbox/');

    await expect(page.getByRole('heading', { name: 'Salary Sandbox' })).toBeVisible();
    await expect(page.getByLabel('Gross monthly salary', { exact: true })).toBeVisible();
    const useClt = page.getByLabel('Calculate CLT deductions automatically', { exact: true });
    await expect(useClt).toBeChecked();
    await expect(page.locator('[data-clt-options]')).toBeVisible();
    await expect(page.locator('[data-manual-options]')).toBeHidden();
    await expect(page.getByText('PJ regime')).toHaveCount(0);
    await expect(page.getByText('CLT and PJ side by side')).toHaveCount(0);

    await page.getByLabel('Gross monthly salary', { exact: true }).fill('6000');
    await useClt.uncheck();
    await expect(page.locator('[data-clt-options]')).toBeHidden();
    await expect(page.locator('[data-manual-options]')).toBeVisible();

    const deductions = page.locator('[data-deduction-row]');
    await expect(deductions).toHaveCount(1);
    await deductions.nth(0).locator('input[name="deduction_label"]').fill('Tax');
    await deductions.nth(0).locator('select[name="deduction_type"]').selectOption('percent');
    await deductions.nth(0).locator('input[name="deduction_value"]').fill('10');
    await page.getByRole('button', { name: 'Add deduction' }).click();
    await deductions.nth(1).locator('input[name="deduction_label"]').fill('Health');
    await deductions.nth(1).locator('input[name="deduction_value"]').fill('200');

    await page.getByLabel('Fixed costs unit', { exact: true }).selectOption('currency');
    await page.getByLabel('Fixed costs target', { exact: true }).fill('1500');
    await page.getByRole('button', { name: 'Add expense' }).click();
    const expenses = page.locator('[data-variable-row]');
    await expenses.locator('input[name="variable_label"]').fill('Leisure');
    await expenses.locator('input[name="variable_value"]').fill('250');

    const grossHelp = page.getByRole('button', { name: 'Explain Gross monthly salary' });
    await grossHelp.hover();
    const grossTooltip = page.getByRole('tooltip').filter({ hasText: 'before any automatic or manually entered deductions' });
    await expect(grossTooltip).toBeVisible();
    await grossHelp.click();
    await page.keyboard.press('Escape');
    await expect(grossTooltip).toBeHidden();
    await expect(grossHelp).toBeFocused();

    await page.getByRole('button', { name: 'Calculate', exact: true }).click();
    await expect(page.locator('#sandbox-workspace')).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'Manual calculation' })).toBeVisible();
    await expect(page.getByRole('paragraph').filter({ hasText: 'R$ 5.200,00' })).toBeVisible();
    await expect(page.getByText('R$ 62.400,00')).toBeVisible();
    await expect(page.getByRole('row', { name: /Tax 10,00%/ })).toContainText('600,00');
    const monthlyPlan = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Monthly plan with current inputs' }) });
    await expect(monthlyPlan.getByRole('row', { name: /Fixed costs target/ })).toContainText('1.500,00');
    await expect(monthlyPlan.getByRole('row', { name: /Fixed costs target/ })).toContainText('28,85%');
    await expect(monthlyPlan.getByRole('row', { name: /Leisure/ })).toContainText('250,00');
    await expect(page.getByText('comparison', { exact: false })).toHaveCount(0);

    await page.setViewportSize({ width: 390, height: 844 });
    const budgetHelp = page.getByRole('button', { name: 'Explain Fixed costs target' }).last();
    await budgetHelp.click();
    const budgetTooltip = page.getByRole('tooltip').filter({ hasText: 'percentage of net income' });
    await expect(budgetTooltip).toBeVisible();
    const tooltipBox = await budgetTooltip.boundingBox();
    expect(tooltipBox.x).toBeGreaterThanOrEqual(12);
    expect(tooltipBox.x + tooltipBox.width).toBeLessThanOrEqual(378);
});

test('salary sandbox switches to automatic CLT and clears only plan estimates', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/sandbox/');
    await page.getByLabel('Gross monthly salary', { exact: true }).fill('6000');

    await page.getByRole('button', { name: 'Add expense' }).click();
    await page.locator('input[name="variable_label"]').fill('Temporary');
    await page.getByRole('button', { name: 'Clear estimates' }).click();
    await expect(page.getByLabel('Fixed costs target', { exact: true })).toHaveValue('');
    await expect(page.locator('[data-variable-row]')).toHaveCount(0);

    await page.getByLabel('Fixed costs target', { exact: true }).fill('50');
    await page.getByRole('button', { name: 'Calculate', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Automatic CLT calculation' })).toBeVisible();
    await expect(page.getByText('Net 13th salary', { exact: true })).toBeVisible();
    await expect(page.getByText('Vacation net with one-third', { exact: true })).toBeVisible();
    await expect(page.getByText('FGTS', { exact: true })).toBeVisible();
    await expect(page.getByText('See comparison with PJ')).toHaveCount(0);
    await expect(page.locator('#sandbox-workspace')).toHaveCount(1);

    await page.getByRole('button', { name: 'Toggle color theme' }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);
});

test('reports keep the next-window control stable when returning to today becomes available', async ({ page }, testInfo) => {
    await createAccount(page, testInfo);
    await page.goto('/dashboard/reports/');

    const evolution = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Balance evolution' }) });
    const nextWindow = evolution.getByRole('link', { name: 'Next window' });
    const initialBox = await nextWindow.boundingBox();

    await nextWindow.click();
    await expect(page).toHaveURL(/charts_offset=1/);
    await expect(evolution.getByRole('link', { name: 'Back to today' })).toBeVisible();

    const nextAfterFirstSwap = evolution.getByRole('link', { name: 'Next window' });
    const movedBox = await nextAfterFirstSwap.boundingBox();
    expect(movedBox.x).toBeCloseTo(initialBox.x, 0);
    expect(movedBox.y).toBeCloseTo(initialBox.y, 0);

    await nextAfterFirstSwap.click();
    await expect(page).toHaveURL(/charts_offset=2/);
    await evolution.getByRole('link', { name: 'Back to today' }).click();
    await expect(page).toHaveURL(/charts_offset=0/);
    await expect(evolution.getByRole('link', { name: 'Back to today' })).toHaveCount(0);

    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
