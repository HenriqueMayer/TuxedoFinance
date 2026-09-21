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
        test(`desktop navigation retains one aligned row and a single chevron (${language}, ${theme})`, async ({ page }, testInfo) => {
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            await signUp(page, testInfo);
            const csrf = await page.locator('[name="csrfmiddlewaretoken"]').first().inputValue();
            await page.request.post('/i18n/setlang/', {
                form: { csrfmiddlewaretoken: csrf, language, next: '/banking/' }, headers: { Referer: page.url() },
            });
            await page.reload();
            await expect(page.locator('html')).toHaveAttribute('lang', language);
            for (const width of [1280, 1440, 1920]) {
                await page.setViewportSize({ width, height: 900 });
                const items = page.locator('body > header [data-nav-item]');
                await expect(items).toHaveCount(5);
                const geometry = await items.evaluateAll(elements => elements.map(item => {
                    const link = item.querySelector(':scope > a');
                    const toggle = item.querySelector('summary');
                    const a = link.getBoundingClientRect();
                    const b = toggle.getBoundingClientRect();
                    return { top: a.y, bottom: a.bottom, left: a.x, right: b.right,
                        centerDifference: Math.abs(a.y + a.height / 2 - b.y - b.height / 2),
                        display: getComputedStyle(item).display, marker: getComputedStyle(toggle).listStyleType,
                        svgCount: toggle.querySelectorAll('svg').length,
                        text: toggle.textContent.trim() };
                }));
                const header = await page.locator('body > header').boundingBox();
                for (const item of geometry) {
                    expect(item.display).toBe('flex');
                    expect(item.marker).toBe('none');
                    expect(item.svgCount).toBe(1);
                    expect(item.text).toBe('');
                    expect(item.centerDifference).toBeLessThan(1);
                    expect(item.top).toBeGreaterThanOrEqual(header.y);
                    expect(item.bottom).toBeLessThanOrEqual(header.y + header.height);
                    expect(item.left).toBeGreaterThan(0);
                    expect(item.right).toBeLessThan(width);
                }
                expect(new Set(geometry.map(item => item.top)).size).toBe(1);
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            }
            await page.setViewportSize({ width: 1440, height: 900 });
            await page.screenshot({ path: testInfo.outputPath(`navigation-${language}-${theme}.png`) });
        });
    }
}
