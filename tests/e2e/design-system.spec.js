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
