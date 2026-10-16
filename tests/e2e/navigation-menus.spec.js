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

const destinations = ['Home', 'Transactions', 'Accounts', 'Investments', 'Plan'];

for (const dark of [false, true]) {
    test(`five direct workspaces retain keyboard order and secondary discovery (${dark ? 'dark' : 'light'})`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await createAccount(page, testInfo);
        await page.evaluate(value => {
            document.documentElement.classList.toggle('dark', value);
            localStorage.setItem('theme', value ? 'dark' : 'light');
        }, dark);
        const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
        await expect(navigation).toHaveAttribute('data-app-navigation', 'desktop');
        await expect(navigation.getByRole('link')).toHaveText(destinations);
        await expect(navigation.locator('details, summary')).toHaveCount(0);
        for (const name of destinations) {
            await navigation.getByRole('link', { name, exact: true }).hover();
            await expect(page.locator('[data-nav-menu]')).toHaveCount(0);
            await expect(page).toHaveURL(/\/banking\/$/);
        }
        await navigation.getByRole('link', { name: 'Home', exact: true }).focus();
        for (const name of destinations) {
            const link = navigation.getByRole('link', { name, exact: true });
            await expect(link).toBeFocused();
            expect(await link.evaluate(el => getComputedStyle(el).outlineStyle)).toBe('solid');
            if (name !== 'Plan') await page.keyboard.press('Tab');
        }
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/planning\/$/);
        await expect(navigation.getByRole('link', { name: 'Plan', exact: true })).toHaveAttribute('aria-current', 'page');
        await navigation.getByRole('link', { name: 'Home', exact: true }).press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        const home = page.getByRole('navigation', { name: 'Home sections' });
        await expect(home.getByRole('link')).toHaveText(['Dashboard', 'Reports']);
        await home.getByRole('link', { name: 'Reports', exact: true }).click();
        await expect(page).toHaveURL(/\/dashboard\/reports\/$/);
        await expect(home.getByRole('link', { name: 'Reports', exact: true })).toHaveAttribute('aria-current', 'page');
        await navigation.getByRole('link', { name: 'Transactions', exact: true }).click();
        const activity = page.getByRole('navigation', { name: 'Transaction sections' });
        await expect(activity.getByRole('link')).toHaveText(['Transactions', 'Categories']);
        await activity.getByRole('link', { name: 'Categories', exact: true }).click();
        await expect(page).toHaveURL(/\/categories\/$/);
        await expect(navigation.getByRole('link', { name: 'Transactions', exact: true })).toHaveAttribute('aria-current', 'page');
        await navigation.getByRole('link', { name: 'Accounts', exact: true }).click();
        const accounts = page.getByRole('navigation', { name: 'Account sections' });
        await expect(accounts.getByRole('link')).toHaveText(['Accounts', 'Invoices', 'Exchange rates']);
        await accounts.getByRole('link', { name: 'Invoices', exact: true }).click();
        await expect(page).toHaveURL(/\/banking\/invoices\/$/);
        await expect(navigation.getByRole('link', { name: 'Accounts', exact: true })).toHaveAttribute('aria-current', 'page');
        await page.goBack();
        await expect(page).toHaveURL(/\/banking\/$/);
        await expect(navigation.getByRole('link', { name: 'Accounts', exact: true })).toHaveAttribute('aria-current', 'page');
        await page.screenshot({ path: testInfo.outputPath(`navigation-${dark ? 'dark' : 'light'}.png`) });
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
    const textBounds = await tooltip.boundingBox();
    await page.mouse.move(textBounds.x + 20, textBounds.y + 20);
    await expect(options).toHaveAttribute('open', '');
    await expect(tooltip).toBeHidden();
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

test('primary navigation hover preserves focused help and Escape retains menu activation rules', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await createAccount(page, testInfo);
    await page.goto('/categories/');
    const help = page.getByRole('button', { name: 'Explain Categories', exact: true });
    await help.press('Enter');
    const tooltip = page.locator('#categories-help');
    await expect(tooltip).toBeVisible();
    await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Plan', exact: true }).hover();
    await expect(page.locator('[data-nav-menu]')).toHaveCount(0);
    await expect(help).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(tooltip).toBeHidden();
    await expect(help).toBeFocused();
    const options = page.locator('header .secondary-actions');
    await options.locator('summary').focus();
    await expect(options).not.toHaveAttribute('open', '');
    await page.keyboard.press('Space');
    await expect(options).toHaveAttribute('open', '');
    await page.keyboard.press('Escape');
    await expect(options).not.toHaveAttribute('open', '');
    await expect(options.locator('summary')).toBeFocused();
});

test('mobile bottom destinations remain direct and account dialog preserves focus and touch', async ({ browser }, testInfo) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 740 }, hasTouch: true, isMobile: true });
    const page = await context.newPage();
    try {
        await createAccount(page, testInfo);
        const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
        await expect(navigation).toHaveAttribute('data-app-navigation', 'mobile');
        await expect(navigation.getByRole('link')).toHaveText(destinations);
        const dock = await navigation.boundingBox();
        expect(dock.y + dock.height).toBeCloseTo(740, 0);
        await navigation.getByRole('link', { name: 'Home', exact: true }).tap();
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await navigation.getByRole('link', { name: 'Plan', exact: true }).tap();
        await expect(page).toHaveURL(/\/planning\/$/);
        await page.getByRole('button', { name: 'Toggle menu', exact: true }).tap();
        const dialog = page.getByRole('dialog', { name: 'Navigation menu' });
        await expect(dialog).toHaveAttribute('aria-hidden', 'false');
        await expect(page.locator('main')).toHaveAttribute('inert', '');
        await expect(page.locator('[data-app-navigation="mobile"]')).toHaveAttribute('inert', '');
        await expect(dialog.locator('[data-nav-item]')).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Close menu', exact: true })).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(dialog.getByRole('button', { name: 'Log out', exact: true })).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(page.getByRole('button', { name: 'Close menu', exact: true })).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(page.locator('#mobile-menu')).toHaveAttribute('aria-hidden', 'true');
        await expect(page.getByRole('button', { name: 'Toggle menu', exact: true })).toBeFocused();
        await expect(page.locator('main')).not.toHaveAttribute('inert', '');
        await page.getByRole('button', { name: 'Toggle menu', exact: true }).tap();
        await dialog.getByRole('link', { name: 'Settings', exact: true }).tap();
        await expect(page).toHaveURL(/\/accounts\/settings\/$/);
        await expect(page.locator('#mobile-menu')).toHaveAttribute('aria-hidden', 'true');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath('navigation-mobile.png') });
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
    test(`workspace destinations and secondary links work without JavaScript at ${width}px`, async ({ browser }, testInfo) => {
        const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width, height: 840 } });
        const page = await context.newPage();
        try {
            await createAccount(page, testInfo);
            const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true });
            await expect(navigation.getByRole('link')).toHaveText(destinations);
            await navigation.getByRole('link', { name: 'Home', exact: true }).press('Enter');
            await page.getByRole('navigation', { name: 'Home sections' }).getByRole('link', { name: 'Reports', exact: true }).click();
            await expect(page).toHaveURL(/\/dashboard\/reports\/$/);
            await navigation.getByRole('link', { name: 'Plan', exact: true }).click();
            await expect(page).toHaveURL(/\/planning\/$/);
            await navigation.getByRole('link', { name: 'Accounts', exact: true }).click();
            await page.getByRole('navigation', { name: 'Account sections' }).getByRole('link', { name: 'Exchange rates', exact: true }).click();
            await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        } finally { await context.close(); }
    });
}

for (const width of [1440, 390]) {
    test(`explicit section anchors stay below the sticky header at ${width}px`, async ({ page }, info) => {
        await page.setViewportSize({ width, height: 800 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await createAccount(page, info);
        await page.goto('/dashboard/reports/');
        const target = page.locator('#report-summary');
        // Put a genuine report anchor below the fold, then reach it through
        // keyboard section navigation rather than scrolling it in the test.
        await target.evaluate(el => { el.style.marginTop = '32rem'; });
        const link = page.getByRole('navigation', { name: 'Home sections' }).getByRole('link', { name: 'Reports', exact: true });
        await link.evaluate(el => {
            el.href = '#report-summary';
            el.setAttribute('hx-boost', 'false');
            window.htmx.process(el);
        });
        await link.press('Enter');
        await expect.poll(async () => {
            const summary = await target.boundingBox();
            const header = await page.locator('body > header').boundingBox();
            return summary.y - header.y - header.height;
        }).toBeGreaterThanOrEqual(15);
        await expect.poll(async () => (await target.boundingBox()).y).toBeLessThan(100);
        expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    });
}
