const { test, expect } = require('@playwright/test');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const browserErrors = new WeakMap();
const workspaces = ['dashboard', 'reports', 'transactions', 'banking', 'investments', 'planning', 'new-entry'];
const primary = ['dashboard', 'transactions', 'banking', 'investments', 'planning'];

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

async function setTheme(page, theme) {
    if (await page.locator('html').getAttribute('data-theme') !== theme) {
        await page.locator('[data-theme-toggle]').click();
    }
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

async function expectScreenshots(page, language) {
    const initialURL = page.url();
    const initialTheme = await page.locator('html').getAttribute('data-theme');
    await expect(page.locator('[data-lightbox] img')).toHaveCount(14);
    for (const workspace of workspaces) {
        const url = new URL(initialURL);
        url.hash = workspace;
        await page.goto(url.href);
        await expect(page.locator('html')).toHaveAttribute('data-workspace', workspace);
        for (const theme of ['light', 'dark']) {
            await setTheme(page, theme);
            const image = page.locator(`#${workspace} .screen-${theme} [data-lightbox] img`);
            await image.scrollIntoViewIfNeeded();
            await expect(image).toBeVisible();
            await expect.poll(() => image.evaluate(element => (
                element.complete && element.naturalWidth === 1440 && element.naturalHeight === 1000
            ))).toBe(true);
            await expect(image).toHaveAttribute('src', new RegExp(`images/${language}/${workspace}-${theme}\\.png$`));
        }
    }
    const records = await page.locator('[data-lightbox] img').evaluateAll(images => images.map(image => ({
        alt: image.alt, source: image.getAttribute('src'), width: image.getAttribute('width'), height: image.getAttribute('height'),
    })));
    for (const record of records) {
        expect(record.alt.length).toBeGreaterThan(24);
        expect(record.source).toContain(`images/${language}/`);
        expect(record.width).toBe('1440');
        expect(record.height).toBe('1000');
    }
    await page.goto(initialURL);
    await setTheme(page, initialTheme);
}


async function openEntryFrom(page, owner, theme) {
    const action = page.locator(`#${owner} [data-workspace-link="new-entry"]`);
    await expect(action).toBeVisible();
    const bounds = await action.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    await action.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/#new-entry$/);
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'new-entry');
    await expect(page.locator('#new-entry-title')).toBeVisible();
    await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(1);
    await expect(page.locator('[data-primary-navigation] [data-workspace-link="transactions"]')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator(`#new-entry .screen-${theme} [data-lightbox] img`)).toBeVisible();
}

async function expectInternalLinks(page) {
    const links = await page.locator('a[href]').evaluateAll(anchors => [...new Set(anchors.map(anchor => anchor.href))]);
    for (const link of links) {
        const target = new URL(link);
        if (target.origin !== new URL(page.url()).origin) continue;
        const response = await page.request.get(target.href);
        expect(response.ok(), `Expected ${target.href} to load`).toBe(true);
        if (target.hash && target.pathname === new URL(page.url()).pathname) {
            expect(await page.evaluate(id => document.getElementById(id) !== null, decodeURIComponent(target.hash.slice(1)))).toBe(true);
        }
    }
}

test('English and Portuguese tours use localized pages and image sets', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('#dashboard-title')).toHaveText('Home');
    await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(1);
    await expectScreenshots(page, 'en');
    await expectInternalLinks(page);
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'pt-BR');
    await expect(page.locator('[data-primary-navigation]').getByRole('link', { name: 'Transações', exact: true })).toBeVisible();
    await expectScreenshots(page, 'pt-br');
    await expectInternalLinks(page);
    await page.getByRole('link', { name: 'EN', exact: true }).click();
    await expect(page).toHaveURL(/\/index\.html$/);
});

test('local HTML files support language navigation without JavaScript', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        const englishURL = pathToFileURL(path.resolve(__dirname, '../../preview/index.html')).href;
        const portugueseURL = pathToFileURL(path.resolve(__dirname, '../../preview/pt-br/index.html')).href;
        await page.goto(englishURL);
        await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(7);
        await page.locator('#dashboard [data-workspace-link="new-entry"]').focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(`${englishURL}#new-entry`);
        await expect(page.locator('#new-entry-title')).toBeVisible();
        await expect(page.locator('#new-entry .screen-light [data-lightbox]')).toHaveAttribute('href', 'images/en/new-entry-light.png');
        await page.locator('[data-primary-navigation] [data-workspace-link="planning"]').focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(`${englishURL}#planning`);
        await page.getByRole('link', { name: 'PT', exact: true }).click();
        await expect(page).toHaveURL(portugueseURL);
        await expect(page.locator('html')).toHaveAttribute('lang', 'pt-BR');
        await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(7);
        await page.getByRole('link', { name: 'PT', exact: true }).click();
        await expect(page).toHaveURL(portugueseURL);
        await page.getByRole('link', { name: 'EN', exact: true }).click();
        await expect(page).toHaveURL(englishURL);
        await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    } finally { await context.close(); }
});

test('theme toggle persists the selected preview theme', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/#planning');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(250, 248, 243)');
    await expect(page.locator('#planning .screen-light')).toBeVisible();
    await page.getByRole('button', { name: 'Toggle light and dark theme' }).click();
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 16, 16)');
    await expect(page.locator('#planning .screen-dark')).toBeVisible();
    await expect(page.locator('#planning .screen-light')).toBeHidden();
    await expect(page.locator('[data-theme-toggle]')).toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'planning');
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html#planning$/);
    await expect(page.locator('#planning .screen-dark')).toBeVisible();
    await page.getByRole('button', { name: 'Alternar entre os temas claro e escuro' }).click();
    await expect(page.locator('#planning .screen-light')).toBeVisible();
});

test('expanded screenshots close accessibly and restore focus', async ({ page }) => {
    await page.goto('/');
    const trigger = page.locator('[data-lightbox]:visible').first();
    const dialog = page.getByRole('dialog', { name: 'Expanded interface screenshot' });
    await trigger.click();
    await expect(dialog).toBeVisible();
    await expect(page.getByRole('button', { name: 'Close expanded screenshot' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.mouse.click(2, 2);
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole('button', { name: 'Close expanded screenshot' }).click();
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
});

test('mobile tour remains readable without horizontal overflow', async ({ page }) => {
    for (const width of [1024, 390]) {
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/pt-br/');
        await expect(page.locator('#dashboard h1')).toBeVisible();
        const links = page.locator('[data-primary-navigation] a');
        await expect(links).toHaveCount(5);
        for (const link of await links.all()) {
            await expect(link).toBeVisible();
            const bounds = await link.boundingBox();
            expect(bounds.height).toBeGreaterThanOrEqual(44);
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const entry = page.locator('#dashboard [data-workspace-link="new-entry"]');
        await expect(entry).toHaveText(/Nova transação/);
        await expect(entry).toBeVisible();
        const bounds = await entry.boundingBox();
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    }
    await expectScreenshots(page, 'pt-br');
});

for (const [language, url] of [['en', '/'], ['pt-br', '/pt-br/']]) {
    for (const width of [1440, 390]) {
        for (const theme of ['light', 'dark']) {
            test(`editorial tour keeps keyboard actions and viewport bounds (${language}, ${width}, ${theme})`, async ({ page }, testInfo) => {
                await page.setViewportSize({ width, height: 900 });
                await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
                await page.goto(url);
                await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
                await expect(page.locator('#dashboard-title')).toHaveText(language === 'en' ? 'Home' : 'Início');
                await page.screenshot({ path: testInfo.outputPath('editorial-tour.png') });
                await openEntryFrom(page, 'dashboard', theme);
                await page.goBack();
                await expect(page.locator('html')).toHaveAttribute('data-workspace', 'dashboard');
                const links = page.locator('[data-primary-navigation] a');
                await expect(links).toHaveCount(5);
                for (let index = 0; index < primary.length; index += 1) {
                    const link = links.nth(index);
                    await link.focus();
                    await page.keyboard.press('Enter');
                    await expect(page.locator('html')).toHaveAttribute('data-workspace', primary[index]);
                    await expect(link).toHaveAttribute('aria-current', 'page');
                    await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(1);
                    const bounds = await link.boundingBox();
                    expect(bounds.x).toBeGreaterThanOrEqual(0);
                    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
                    expect(bounds.height).toBeGreaterThanOrEqual(44);
                    await expect(page.locator(`#${primary[index]} .screen-${theme}`)).toBeVisible();
                    if (primary[index] === 'transactions') {
                        await openEntryFrom(page, 'transactions', theme);
                        await page.goBack();
                        await expect(page.locator('html')).toHaveAttribute('data-workspace', 'transactions');
                    }
                }
                await page.screenshot({ path: testInfo.outputPath('plan-workspace.png') });
                const screenshot = page.locator('[data-lightbox]:visible').first();
                await screenshot.focus();
                await page.keyboard.press('Enter');
                await expect(page.locator('#image-dialog')).toBeVisible();
                await expect(page.locator('[data-dialog-close]')).toBeFocused();
                await page.keyboard.press('Escape');
                await expect(page.locator('#image-dialog')).toBeHidden();
                await expect(screenshot).toBeFocused();
                const original = page.locator('#planning .capture-original:visible');
                await original.focus();
                const bounds = await original.boundingBox();
                const dock = await page.locator('[data-primary-navigation]').boundingBox();
                if (width === 390) expect(bounds.y + bounds.height).toBeLessThanOrEqual(dock.y);
            });
        }
    }
}

test('workspace hashes preserve history, Reports and entry ownership, and language context', async ({ page }) => {
    await page.goto('/');
    await page.locator('#dashboard [data-workspace-link="reports"]').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'reports');
    await expect(page.locator('[data-primary-navigation] [data-workspace-link="dashboard"]')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('#reports [data-workspace-link="reports"]')).toHaveAttribute('aria-current', 'page');
    await page.locator('[data-primary-navigation] [data-workspace-link="transactions"]').click();
    await page.goBack();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'reports');
    await page.goForward();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'transactions');
    await openEntryFrom(page, 'transactions', await page.locator('html').getAttribute('data-theme'));
    await page.goBack();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'transactions');
    await page.goForward();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'new-entry');
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html#new-entry$/);
    await expect(page.locator('#new-entry-title')).toHaveText('Nova transação');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'new-entry');
    await expect(page.locator('[data-primary-navigation] [data-workspace-link="transactions"]')).toHaveAttribute('aria-current', 'page');
    await setTheme(page, 'dark');
    await expect(page.locator('#new-entry .screen-dark')).toBeVisible();
    await page.getByRole('link', { name: 'EN', exact: true }).click();
    await expect(page).toHaveURL(/\/index\.html#new-entry$/);
    await expect(page.locator('#new-entry .screen-dark')).toBeVisible();
    await page.goto('/#unknown-workspace');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'dashboard');
    await page.goto('/#dashboard-preview');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'dashboard');
    await expect(page.locator('#dashboard-title')).toBeVisible();
    await page.goto('/#top');
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'dashboard');
});

test('history navigation closes a replaced screenshot without focusing its hidden owner', async ({ page }) => {
    await page.goto('/');
    await page.locator('[data-primary-navigation] [data-workspace-link="transactions"]').click();
    await page.locator('[data-lightbox]:visible').click();
    await expect(page.locator('#image-dialog')).toBeVisible();
    await page.goBack();
    await expect(page.locator('#image-dialog')).toBeHidden();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'dashboard');
    await expect(page.locator('#dashboard h1')).toBeFocused();
});

test('skip navigation preserves the selected workspace and moves keyboard focus', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    await expect(page.locator('.skip-link')).toBeFocused();
    await page.locator('[data-primary-navigation] [data-workspace-link="banking"]').click();
    await page.locator('.skip-link').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main')).toBeFocused();
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'banking');
    await expect(page).toHaveURL(/#banking$/);
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html#banking$/);
    await expect(page.locator('html')).toHaveAttribute('data-workspace', 'banking');
});

test('embedded tours open repository links outside their sandbox without leaving the preview', async ({ page }) => {
    await page.context().route('https://github.com/HenriqueMayer/TuxedoFinance**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Repository destination</h1>' }));
    for (const source of ['/index.html', '/pt-br/index.html']) {
        // Match an embedded tour viewport; the HTML default is only 150px tall.
        await page.route('**/embedded-tour-test.html', route => route.fulfill({ contentType: 'text/html', body: `<style>body{margin:0}iframe{display:block;width:100%;height:720px;border:0}</style><iframe title="Tour" src="${source}" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>` }));
        await page.goto('/embedded-tour-test.html');
        const tour = page.frameLocator('iframe');
        const links = tour.locator('.header-external a');
        await expect(links).toHaveCount(2);
        for (let index = 0; index < 2; index += 1) {
            const popupPromise = page.waitForEvent('popup');
            await links.nth(index).click();
            const popup = await popupPromise;
            await expect(popup.getByRole('heading')).toHaveText('Repository destination');
            expect(popup.url()).toContain('https://github.com/HenriqueMayer/TuxedoFinance');
            expect(await popup.evaluate(() => window.opener === null)).toBe(true);
            await expect(tour.locator('#dashboard h1')).toBeVisible();
            await expect(page).toHaveURL(/embedded-tour-test\.html$/);
            await popup.close();
        }
        await page.unroute('**/embedded-tour-test.html');
    }
});
