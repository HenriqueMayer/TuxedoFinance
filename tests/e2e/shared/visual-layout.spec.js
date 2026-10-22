// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function signUp(page, testInfo) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `layout-${testInfo.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {
        form: { csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status()).toBe(302);
    await page.goto('/banking/');
}

for (const language of ['en', 'pt-br']) {
    for (const theme of ['light', 'dark']) {
        test(`six destinations fit desktop sidebar and mobile dock (${language}, ${theme})`, async ({ page }, testInfo) => {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await signUp(page, testInfo);
            const csrf = await page.locator('[name="csrfmiddlewaretoken"]').first().inputValue();
            await page.request.post('/i18n/setlang/', {
                form: { csrfmiddlewaretoken: csrf, language, next: '/banking/' }, headers: { Referer: page.url() },
            });
            await page.reload();
            await expect(page.locator('html')).toHaveAttribute('lang', language);
            const navigation = page.getByRole('navigation', { name: language === 'en' ? 'Main navigation' : 'Navegação principal', exact: true });
            const labels = language === 'en'
                ? {desktop: ['Home', 'Transactions', 'Accounts', 'Investments', 'Plan', 'Analytics'], mobile: ['Home', 'Entries', 'Accounts', 'Invest', 'Plan', 'Analytics']}
                : {desktop: ['Início', 'Transações', 'Contas', 'Investimentos', 'Planejar', 'Análises'], mobile: ['Início', 'Transações', 'Contas', 'Investir', 'Planejar', 'Análises']};
            for (const width of [320, 390, 768, 1023, 1024, 1280, 1440, 1920]) {
                await page.setViewportSize({ width, height: 900 });
                await expect(navigation).toHaveCount(1);
                await expect(navigation).toHaveAttribute('data-app-navigation', width < 1024 ? 'mobile' : 'desktop');
                await expect(navigation.locator('.app-navigation-label')).toHaveText(width < 1024 ? labels.mobile : labels.desktop);
                await expect(navigation.locator('summary, details')).toHaveCount(0);
                const geometry = await navigation.getByRole('link').evaluateAll(elements => elements.map(link => {
                    const box = link.getBoundingClientRect();
                    const label = link.querySelector('span').getBoundingClientRect();
                    return { x: box.x, y: box.y, right: box.right, bottom: box.bottom, width: box.width, height: box.height,
                        labelWidth: label.width, labelHeight: label.height, lineHeight: parseFloat(getComputedStyle(link).lineHeight),
                        svgCount: link.querySelectorAll('svg').length };
                }));
                for (const item of geometry) {
                    expect(item.svgCount).toBe(1);
                    expect(item.labelWidth).toBeLessThanOrEqual(item.width);
                    if (width < 1024) expect(item.labelHeight).toBeLessThanOrEqual(item.lineHeight + 1);
                    expect(item.width).toBeGreaterThanOrEqual(44);
                    expect(item.height).toBeGreaterThanOrEqual(44);
                    expect(item.x).toBeGreaterThanOrEqual(0);
                    expect(item.right).toBeLessThanOrEqual(width);
                    expect(item.y).toBeGreaterThanOrEqual(0);
                    expect(item.bottom).toBeLessThanOrEqual(900);
                }
                if (width >= 1024) {
                    expect(new Set(geometry.map(item => item.x)).size).toBe(1);
                    for (let index = 1; index < geometry.length; index++) expect(geometry[index].y).toBeGreaterThan(geometry[index - 1].bottom);
                    const content = await page.locator('main').boundingBox();
                    expect(content.x).toBeGreaterThanOrEqual(208);
                } else {
                    expect(new Set(geometry.map(item => item.y)).size).toBe(1);
                    for (let index = 1; index < geometry.length; index++) expect(geometry[index].x).toBeGreaterThanOrEqual(geometry[index - 1].right);
                }
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
                if (language === 'pt-br' && width === 320) {
                    // Real navigation must fit the longest Portuguese label
                    // when active, as well as when inactive.
                    for (let index = 0; index < 6; index++) {
                        await navigation.getByRole('link').nth(index).click();
                        await expect(navigation.getByRole('link').nth(index)).toHaveAttribute('aria-current', 'page');
                        await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1);
                        const bounds = await navigation.getByRole('link').evaluateAll(links => links.map(link => {
                            const box = link.getBoundingClientRect();
                            const label = link.querySelector('span').getBoundingClientRect();
                            return { width: box.width, height: box.height, labelWidth: label.width,
                                labelHeight: label.height, lineHeight: parseFloat(getComputedStyle(link).lineHeight) };
                        }));
                        for (const box of bounds) {
                            expect(box.width).toBeGreaterThanOrEqual(44);
                            expect(box.height).toBeGreaterThanOrEqual(44);
                            expect(box.labelWidth).toBeLessThanOrEqual(box.width);
                            expect(box.labelHeight).toBeLessThanOrEqual(box.lineHeight + 1);
                        }
                    }
                }
            }
            for (const width of [1440, 390]) {
                await page.setViewportSize({ width, height: 900 });
                await page.screenshot({ path: testInfo.outputPath(`navigation-${width}-${language}-${theme}.png`) });
                const before = await navigation.boundingBox();
                await page.locator('main').evaluate(el => { el.style.minHeight = '1800px'; });
                await page.evaluate(() => window.scrollTo(0, 500));
                expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
                const after = await navigation.boundingBox();
                expect(after.y).toBeCloseTo(before.y, 0);
                expect(after.x).toBeCloseTo(before.x, 0);
                await page.evaluate(() => window.scrollTo(0, 0));
            }
        });
    }
}
