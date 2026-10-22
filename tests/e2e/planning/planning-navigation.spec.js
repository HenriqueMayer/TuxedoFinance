// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/);
    expect(token, `CSRF token on ${path}`).not.toBeNull();
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: token[1], ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(result.status(), await result.text()).toBe(302);
    return result.headers().location;
}

async function signup(page, info) {
    const username = `plan-navigation-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
}

async function ownedNavigation(page, primary, secondary) {
    const main = page.locator('[data-planning-navigation]');
    await expect(main).toHaveCount(1);
    await expect(main.locator('a')).toHaveCount(4);
    await expect(main.locator('[aria-current="page"]')).toHaveAttribute('href', primary);
    const nested = page.locator('[data-simulation-navigation]');
    if (secondary) {
        await expect(nested).toHaveCount(1);
        await expect(nested.locator('a')).toHaveCount(3);
        await expect(nested.locator('[aria-current="page"]')).toHaveAttribute('href', secondary);
    } else await expect(nested).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const language of ['en', 'pt-br']) {
for (const theme of ['light', 'dark']) {
for (const width of [1440, 320]) {
    test(`explicit planning sections retain keyboard and page ownership (${language}, ${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 820});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await signup(page, info);
        await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
        await page.goto('/planning/');
        await ownedNavigation(page, '/planning/');
        for (const anchor of await page.locator('[data-planning-navigation] a').all()) {
            await anchor.focus();
            const size = await anchor.boundingBox();
            expect(size.width).toBeGreaterThanOrEqual(44);
            expect(size.height).toBeGreaterThanOrEqual(44);
            expect(size.x).toBeGreaterThanOrEqual(0);
            expect(size.x + size.width).toBeLessThanOrEqual(width + 1);
        }
        const goals = page.locator('[data-planning-navigation] a[href="/planning/goals/"]');
        await goals.focus(); await goals.press('Enter');
        await expect(page).toHaveURL(/\/planning\/goals\/$/);
        await ownedNavigation(page, '/planning/goals/');
        await page.locator('[data-planning-navigation] a[href="/sandbox/"]').press('Enter');
        await expect(page).toHaveURL(/\/sandbox\/$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/');
        await page.locator('[data-simulation-navigation] a[href="/sandbox/simulation/"]').press('Enter');
        await expect(page).toHaveURL(/\/sandbox\/simulation\/$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/simulation/');
        await page.locator('[data-simulation-navigation] a[href="/sandbox/drafts/"]').press('Enter');
        await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
        await page.locator('[data-planning-navigation] a[href="/planning/signals/"]').press('Enter');
        await expect(page).toHaveURL(/\/planning\/signals\/$/);
        await ownedNavigation(page, '/planning/signals/');
        await page.goBack();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
        await page.goForward();
        await expect(page).toHaveURL(/\/planning\/signals\/$/);
        await ownedNavigation(page, '/planning/signals/');
    });
}
}
}

test('saved draft detail, comparison and delete keep their own simulation section', async ({page}, info) => {
    await signup(page, info);
    // Incomplete drafts are supported and expose invalid forms without a result
    // departure warning; their location still belongs to the saved collection.
    const detail = await post(page, '/sandbox/', {action: 'save', draft_name: 'Navigation recovery scenario',
        gross_salary: '6000', planning_month: '2026-'});
    const id = detail.match(/\/drafts\/(\d+)\//)[1];
    await page.goto(detail);
    await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
    await expect(page.locator('#id_planning_month')).toHaveValue('2026-');
    await page.goto(`/sandbox/drafts/compare/?draft=${id}`);
    await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
    await page.goto(`${detail}delete/`);
    await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
    await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
    await expect(page).toHaveURL(detail);
    await ownedNavigation(page, '/sandbox/', '/sandbox/drafts/');
});

test.describe('native planning navigation', () => {
    test.use({javaScriptEnabled: false});
    test('legacy tools and explicit planning destinations remain usable without JavaScript', async ({page}, info) => {
        await signup(page, info);
        await page.goto('/planning/tools/?month=2030-03');
        await expect(page).toHaveURL(/\/sandbox\/\?month=2030-03$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/');
        await page.locator('[data-simulation-navigation] a[href="/sandbox/simulation/"]').press('Enter');
        await expect(page).toHaveURL(/\/sandbox\/simulation\/$/);
        await ownedNavigation(page, '/sandbox/', '/sandbox/simulation/');
        await page.locator('[data-planning-navigation] a[href="/planning/signals/"]').press('Enter');
        await expect(page).toHaveURL(/\/planning\/signals\/$/);
        await ownedNavigation(page, '/planning/signals/');
    });
});
