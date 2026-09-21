// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function signup(page, testInfo) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `planning-help-${testInfo.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {
        form: { csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status()).toBe(302);
}

async function readableHelp(page, selector) {
    const tooltip = page.locator(selector);
    await expect(tooltip).toBeVisible();
    const bounds = await tooltip.boundingBox();
    const viewport = page.viewportSize();
    expect(bounds.width).toBeGreaterThanOrEqual(300);
    expect(bounds.width).toBeLessThanOrEqual(352);
    expect(bounds.x).toBeGreaterThanOrEqual(11);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width - 11);
    expect(bounds.y).toBeGreaterThanOrEqual(11);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height - 11);
    return tooltip;
}

for (const theme of ['light', 'dark']) {
    test(`planning panels and contextual help preserve pointer, keyboard and refreshed behavior in ${theme}`, async ({ page }, testInfo) => {
        await signup(page, testInfo);
        await page.goto('/sandbox/');
        await page.evaluate(theme => {
            localStorage.setItem('theme', theme);
            document.documentElement.classList.toggle('dark', theme === 'dark');
        }, theme);
        await expect(page.locator('[aria-labelledby="salary-input-title"]')).toHaveClass(/surface-panel/);
        await expect(page.locator('#salary-sandbox-help')).toBeHidden();
        await expect(page.locator('#id_gross_salary-help')).toBeHidden();
        const headingHelp = page.getByRole('button', { name: 'Explain Salary Sandbox', exact: true });
        await headingHelp.hover();
        const tooltip = await readableHelp(page, '#salary-sandbox-help');
        await tooltip.hover();
        await expect(tooltip).toBeVisible();
        await headingHelp.click();
        await page.mouse.move(2, 2);
        await expect(tooltip).toBeHidden();

        // Tab into the help from the preceding section navigation.
        await page.getByRole('link', { name: 'Saved drafts', exact: true }).focus();
        await page.keyboard.press('Tab');
        await expect(headingHelp).toBeFocused();
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(tooltip).toBeHidden();
        await expect(headingHelp).toBeFocused();
        await page.keyboard.press('Space');
        await expect(tooltip).toBeVisible();
        await page.keyboard.press('Tab');
        await expect(tooltip).toBeHidden();
        await headingHelp.hover();
        await page.mouse.click(2, 2);
        await expect(tooltip).toBeHidden();

        await page.locator('#id_gross_salary').fill('5000');
        await page.getByRole('button', { name: 'Explain Future commitments', exact: true }).hover();
        await readableHelp(page, '#future-commitments-help');
        await page.locator('#budget-calculate').click();
        await expect(page.locator('#scenario-result-title')).toBeVisible();
        await expect(page.locator('#future-commitments-help')).toHaveCount(1);
        await expect(page.locator('#sandbox-workspace noscript')).toHaveCount(0);
        const refreshedHelp = page.getByRole('button', { name: 'Explain Future commitments', exact: true });
        await refreshedHelp.hover();
        await readableHelp(page, '#future-commitments-help');
        await expect(page.locator('[aria-labelledby="scenario-result-title"]')).toHaveClass(/surface-panel/);
        await page.screenshot({ path: testInfo.outputPath(`planning-panel-help-${theme}.png`), fullPage: true });

        await page.goto('/sandbox/simulation/');
        await page.locator('#id_initial_balance').fill('100');
        await page.locator('#id_rate').fill('1');
        await page.locator('#id_months').fill('2');
        await page.locator('#id_contribution').fill('100');
        await expect(page.locator('#simulation-result')).toContainText('303,01');
        const resultHelp = page.getByRole('button', { name: 'Explain Projected result', exact: true });
        await resultHelp.hover();
        await readableHelp(page, '#yield-result-help');
        await page.mouse.move(2, 2);
        await page.locator('#id_contribution').fill('50');
        await expect(page.locator('#simulation-result')).toContainText('202,51');
        await expect(page.locator('#yield-result-help')).toHaveCount(1);
        await expect(page.locator('#yield-result-help')).toBeHidden();
        await resultHelp.hover();
        await readableHelp(page, '#yield-result-help');
    });
}

test('Portuguese planning help fits mobile and toggles with touch', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 740 }, hasTouch: true, locale: 'pt-BR' });
    const page = await context.newPage();
    try {
        await signup(page, testInfo);
        await context.addCookies([{ name: 'django_language', value: 'pt-br', url: testInfo.project.use.baseURL }]);
        await page.goto('/sandbox/simulation/');
        const trigger = page.getByRole('button', { name: 'Explicar Simulação de rendimento', exact: true });
        await trigger.tap();
        const tooltip = await readableHelp(page, '#yield-simulation-help');
        await expect(tooltip).toContainText('Meses completos');
        await page.screenshot({ path: testInfo.outputPath('planning-help-mobile-pt.png'), fullPage: true });
        await trigger.tap();
        await expect(tooltip).toBeHidden();
        await trigger.tap();
        await page.touchscreen.tap(2, 2);
        await expect(tooltip).toBeHidden();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    } finally {
        await context.close();
    }
});

test('planning explanations retain native keyboard access without JavaScript', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 740 } });
    const page = await context.newPage();
    try {
        await signup(page, testInfo);
        await page.goto('/sandbox/simulation/');
        const help = page.locator('.help-fallback summary[aria-label="Explain Yield simulation"]');
        await help.focus();
        await page.keyboard.press('Enter');
        const details = help.locator('..');
        await expect(details).toHaveAttribute('open', '');
        await expect(details).toContainText('Full months');
        const bounds = await details.locator('.help-fallback-content').boundingBox();
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
        await page.keyboard.press('Enter');
        await expect(details).not.toHaveAttribute('open');
        await page.locator('#id_initial_balance').fill('1000');
        await page.locator('#id_rate').fill('1');
        await page.getByRole('button', { name: 'Calculate', exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Projected result', exact: true })).toBeVisible();
    } finally {
        await context.close();
    }
});
