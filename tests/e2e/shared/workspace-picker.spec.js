// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...fields }, headers: { Referer: response.url() }, maxRedirects: 0,
    });
    expect(saved.status(), await saved.text()).toBe(302);
}

for (const theme of ['light', 'dark']) {
    test(`mobile keyboard results fit above persistent navigation (${theme})`, async ({ page }, info) => {
        await page.setViewportSize({ width: 390, height: 640 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const username = `dock-picker-${info.workerIndex}-${Date.now()}`;
        await post(page, '/accounts/signup/', { username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' });
        for (let index = 1; index <= 8; index++) {
            await post(page, '/categories/create/', { name: `Keyboard category ${index}`, transaction_type: 'EXPENSE' });
        }
        await page.goto('/transactions/create/');
        const kind = page.locator('#id_transaction_type input[value="EXPENSE"]');
        await kind.press('Space');
        await kind.focus();
        const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
        const dockTop = (await navigation.boundingBox()).y;
        await kind.evaluate((el, bottom) => window.scrollBy(0,
            el.closest('label').getBoundingClientRect().bottom - bottom + 12), dockTop);
        const input = page.locator('#category-search');
        // The optional split checkbox and contextual help also retain Tab
        // access; reach the picker through those controls without focusing it.
        for (let index = 0; index < 8; index++) {
            if (await input.evaluate(el => el === document.activeElement)) break;
            await page.keyboard.press('Tab');
        }
        const results = page.locator('#category-search-results');
        await expect(input).toBeFocused();
        await input.pressSequentially('Keyboard category');
        await expect(results.getByRole('option')).toHaveCount(8);
        const visible = async () => input.evaluate(el => {
            const list = document.getElementById(el.getAttribute('aria-controls'));
            return el.getBoundingClientRect().top >= document.querySelector('body > header').getBoundingClientRect().bottom
                && list.getBoundingClientRect().bottom <= document.querySelector('.app-bottom-navigation').getBoundingClientRect().top - 15;
        });
        await expect.poll(visible).toBe(true);
        const top = await page.evaluate(() => window.scrollY);
        for (let index = 0; index < 8; index++) await page.keyboard.press('ArrowDown');
        const last = results.getByRole('option').last();
        await expect(last).toHaveAttribute('aria-selected', 'true');
        await expect(last).toBeInViewport({ ratio: 1 });
        expect(await results.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
        expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(top, 0);
        await expect(input).toBeFocused();
        await expect(navigation).toBeVisible();
        await page.screenshot({ path: info.outputPath(`navigation-picker-${theme}.png`) });
        await page.setViewportSize({ width: 390, height: 500 });
        await expect.poll(visible).toBe(true);
        await expect(last).toBeInViewport({ ratio: 1 });
        await expect(input).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page.locator('#id_category')).not.toHaveValue('');
        await expect(input).toHaveValue('Keyboard category 8');
        await page.keyboard.press('Escape');
        await expect(results).toBeHidden();
    });
}
