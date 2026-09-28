// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const { test, expect } = require('@playwright/test');

// Only the repository runner supplies an owned disposable database. Never seed
// a developer installation when Playwright is invoked directly or via Docker.
const isolated = path.basename(process.env.TUXEDO_DATA_DIR || '').startsWith('tuxedo-e2e-');

for (const language of ['pt', 'en']) {
    test(`optional ${language} demo supports the presentation tour in both themes`, async ({ page, context, baseURL }, testInfo) => {
        test.skip(!isolated, 'Run with npm run test:e2e to own a disposable local database.');
        test.setTimeout(90000);
        const username = `tour_${language}_${testInfo.workerIndex}_${Date.now()}`;
        const output = execFileSync('uv', [
            'run', 'python', 'manage.py', 'insert_demo', language, '--username', username,
        ], { cwd: path.resolve(__dirname, '../..'), encoding: 'utf8', env: process.env });
        const password = output.match(/^Password: (.+)$/m)[1];
        const locale = language === 'pt' ? 'pt-br' : 'en';
        await context.addCookies([{ name: 'django_language', value: locale, url: baseURL }]);
        await page.goto('/accounts/login/');
        await page.locator('#id_username').fill(username);
        await page.locator('#id_password').fill(password);
        await page.locator('#id_password').press('Enter');
        await expect(page).not.toHaveURL(/login/);

        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        for (const theme of ['light', 'dark']) {
            await page.evaluate(value => localStorage.setItem('theme', value), theme);
            for (const route of [
                '/dashboard/', '/dashboard/reports/', '/transactions/', '/banking/',
                '/banking/exchange-rates/', '/investments/', '/investments/charts/',
                '/investments/operations/', '/sandbox/drafts/',
            ]) {
                const response = await page.goto(route);
                expect(response.status(), route).toBe(200);
                await expect(page.locator('html')).toHaveAttribute('lang', locale);
                await expect(page.locator('main')).toBeVisible();
                if (route === '/banking/') {
                    await expect(page.locator('main')).toContainText(language === 'pt' ? 'Banco Aurora Demo' : 'Aurora Demo Bank');
                }
                if (route === '/sandbox/drafts/') {
                    const links = page.locator('main a[href]').filter({ hasText: language === 'pt' ? 'Mês atual:' : 'Current month:' });
                    await expect(links).toHaveCount(2);
                    await links.first().press('Enter');
                    await expect(page.locator('#id_gross_salary')).toHaveValue(/\d/);
                }
            }
            await page.goto('/dashboard/');
            await page.screenshot({ path: testInfo.outputPath(`demo-${language}-${theme}.png`), fullPage: true });
        }
        expect(errors).toEqual([]);
    });
}
