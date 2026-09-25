// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function createAccount(page, testInfo) {
    const signup = await page.request.get('/accounts/signup/');
    const csrf = (await signup.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `navigation-${testInfo.workerIndex}-${Date.now()}`;
    const response = await page.request.post('/accounts/signup/', {
        form: { csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!' },
        headers: { Referer: signup.url() }, maxRedirects: 0,
    });
    expect(response.status(), await response.text()).toBe(302);
    await page.goto('/banking/');
}

for (const dark of [false, true]) {
    test(`main navigation opens by hover and preserves direct links and keyboard (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await createAccount(page, testInfo);
        await page.evaluate(value => {
            document.documentElement.classList.toggle('dark', value);
            localStorage.setItem('theme', value ? 'dark' : 'light');
        }, dark);
        const navigation = page.locator('header nav').first();
        for (const [area, label] of [['overview', 'Reports'], ['activity', 'Categories'],
            ['banks', 'Exchange rates'], ['investments', 'Configuration'], ['planning', 'Saved drafts']]) {
            const item = navigation.locator(`[data-nav-item="${area}"]`);
            await item.locator('summary').hover();
            await expect(item.locator('details')).not.toHaveAttribute('open', '');
            await item.locator(':scope > a').hover();
            await expect(item.locator('details')).toHaveAttribute('open', '');
            await expect(item.getByRole('link', { name: label, exact: true })).toBeVisible();
            await item.getByRole('link', { name: label, exact: true }).hover();
            const bounds = await item.locator('.nav-disclosure-panel').boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(1440);
            await expect(page).toHaveURL(/\/banking\/$/);
            await page.locator('main h1').hover();
            await expect(item.locator('details')).not.toHaveAttribute('open', '');
        }
        await navigation.locator(':scope > a').focus();
        await page.keyboard.press('Tab');
        const overview = navigation.locator('[data-nav-item="overview"]');
        await expect(overview.locator(':scope > a')).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await expect(page.locator('#nav-desktop-overview-toggle')).toBeVisible();
        const activity = navigation.locator('[data-nav-item="activity"]');
        await activity.locator(':scope > a').focus();
        await page.keyboard.press('Tab');
        await expect(activity.locator('summary')).toBeFocused();
        await page.keyboard.press('Space');
        await expect(activity.locator('details')).toHaveAttribute('open', '');
        await page.keyboard.press('Tab');
        await expect(activity.getByRole('link', { name: 'Transactions', exact: true })).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(activity.getByRole('link', { name: 'Categories', exact: true })).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(activity.locator('summary')).toBeFocused();
        await expect(activity.locator('details')).not.toHaveAttribute('open', '');
        await page.keyboard.press('ArrowDown');
        await expect(activity.getByRole('link', { name: 'Transactions', exact: true })).toBeFocused();
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await expect(navigation.locator('[data-nav-item="banks"] > a')).toBeFocused();
        await expect(activity.locator('details')).not.toHaveAttribute('open', '');
        await navigation.locator('[data-nav-item="planning"] > a').hover();
        await page.screenshot({ path: testInfo.outputPath(`navigation-${dark ? 'dark' : 'light'}.png`) });
        await navigation.locator('[data-nav-item="planning"]').getByRole('link', { name: 'Saved drafts', exact: true }).click();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
        await expect(page.locator('header [data-nav-menu][open]')).toHaveCount(0);
        await page.goBack();
        await navigation.locator('[data-nav-item="overview"] > a').hover();
        await expect(navigation.locator('[data-nav-item="overview"] details')).toHaveAttribute('open', '');
    });
}

test('option buttons require activation, retain portal help and leave content accordions explicit', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await createAccount(page, testInfo);
    const account = page.locator('body > header .secondary-actions');
    await account.locator('summary').hover();
    await expect(account).not.toHaveAttribute('open', '');
    await account.locator('summary').click();
    await expect(account).toHaveAttribute('open', '');
    await page.locator('main h1').click();
    await expect(account).not.toHaveAttribute('open', '');
    const project = page.locator('header [data-project-menu]').filter({ visible: true });
    await project.locator(':scope > summary').hover();
    await expect(project).not.toHaveAttribute('open', '');
    await project.locator(':scope > summary').click();
    await expect(project).toHaveAttribute('open', '');
    const roadmap = project.locator('details');
    await roadmap.locator('summary').hover();
    await expect(roadmap).not.toHaveAttribute('open', '');
    await page.locator('main h1').hover();
    await expect(project).toHaveAttribute('open', '');
    await page.locator('main h1').click();
    await expect(project).not.toHaveAttribute('open', '');

    await page.goto('/categories/');
    const options = page.locator('main details.secondary-actions').first();
    await options.locator(':scope > summary').hover();
    await expect(options).not.toHaveAttribute('open', '');
    await options.locator(':scope > summary').click();
    await expect(options).toHaveAttribute('open', '');
    const help = options.locator('[data-help-trigger]').first();
    await expect(help).toBeVisible();
    await help.hover();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    await tooltip.hover();
    await expect(options).toHaveAttribute('open', '');
    await expect(tooltip).toBeVisible();
    await page.locator('main h1').hover();
    await expect(options).toHaveAttribute('open', '');
    await page.locator('main h1').click();
    await expect(options).not.toHaveAttribute('open', '');
    await expect(tooltip).toBeHidden();
    await page.goto('/transactions/create/');
    const advanced = page.locator('main details').first();
    await advanced.locator('summary').hover();
    await expect(advanced).not.toHaveAttribute('open', '');
});

test('Escape dismisses focused page help before a menu opened elsewhere by hover', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await createAccount(page, testInfo);
    await page.goto('/categories/');
    const help = page.getByRole('button', { name: 'Explain Categories', exact: true });
    await help.press('Enter');
    const tooltip = page.locator('#categories-help');
    await expect(tooltip).toBeVisible();
    const planning = page.locator('body > header [data-nav-item="planning"]');
    await planning.locator(':scope > a').hover();
    await expect(planning.locator('details')).toHaveAttribute('open', '');
    await expect(help).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(tooltip).toBeHidden();
    await expect(help).toBeFocused();
    await expect(planning.locator('details')).toHaveAttribute('open', '');
    await page.keyboard.press('Escape');
    await expect(planning.locator('details')).not.toHaveAttribute('open', '');
});

test('mobile menus support touch, direct destinations and nested Escape', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 740 }, hasTouch: true, isMobile: true });
    const page = await context.newPage();
    try {
        await createAccount(page, testInfo);
        await page.getByRole('button', { name: 'Toggle menu', exact: true }).tap();
        const dialog = page.getByRole('dialog');
        const planning = dialog.locator('[data-nav-item="planning"]');
        await planning.locator('summary').tap();
        await expect(planning.getByRole('link', { name: 'Saved drafts', exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await planning.locator('summary').tap();
        await expect(planning.locator('details')).not.toHaveAttribute('open', '');
        await planning.locator('summary').tap();
        await page.keyboard.press('Escape');
        await expect(planning.locator('details')).not.toHaveAttribute('open', '');
        await expect(dialog).toHaveAttribute('aria-hidden', 'false');
        await page.keyboard.press('Escape');
        await expect(page.locator('#mobile-menu')).toHaveAttribute('aria-hidden', 'true');
        await page.getByRole('button', { name: 'Toggle menu', exact: true }).tap();
        await dialog.locator('[data-nav-item="overview"] > a').tap();
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await page.getByRole('button', { name: 'Toggle menu', exact: true }).tap();
        await planning.locator('summary').tap();
        await planning.getByRole('link', { name: 'Saved drafts', exact: true }).tap();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
        await expect(page.locator('#mobile-menu')).toHaveAttribute('aria-hidden', 'true');
        await page.goto('/categories/');
        const options = page.locator('main details.secondary-actions').first();
        await options.locator(':scope > summary').tap();
        await options.locator('[data-help-trigger]').tap();
        const tooltip = page.getByRole('tooltip');
        await expect(tooltip).toBeVisible();
        await tooltip.tap();
        await expect(options).toHaveAttribute('open', '');
        await expect(tooltip).toBeVisible();
        await page.locator('main h1').tap();
        await expect(options).not.toHaveAttribute('open', '');
        await expect(tooltip).toBeHidden();
    } finally { await context.close(); }
});

for (const width of [1440, 390]) {
    test(`navigation submenus work without JavaScript at ${width}px`, async ({ browser }, testInfo) => {
        const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width, height: 840 } });
        const page = await context.newPage();
        try {
            await createAccount(page, testInfo);
            const variant = width < 1280 ? 'native' : 'desktop';
            const toggle = page.locator(`#nav-${variant}-overview-toggle`);
            await toggle.press('Enter');
            const reports = page.locator(`#nav-${variant}-overview-panel`).getByRole('link', { name: 'Reports', exact: true });
            await expect(reports).toBeVisible();
            await reports.click();
            await expect(page).toHaveURL(/\/dashboard\/reports\/$/);
            await page.locator(`#nav-${variant}-planning-toggle`).press('Space');
            await page.locator(`#nav-${variant}-planning-panel`).getByRole('link', { name: 'Saved drafts', exact: true }).click();
            await expect(page).toHaveURL(/\/sandbox\/drafts\/$/);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        } finally { await context.close(); }
    });
}
