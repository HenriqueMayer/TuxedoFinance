const { test, expect } = require('@playwright/test');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

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

async function expectScreenshots(page, language) {
    const screenshots = page.locator('[data-lightbox] img');
    await expect(screenshots).toHaveCount(6);
    for (let index = 0; index < 6; index += 1) {
        const image = screenshots.nth(index);
        await image.scrollIntoViewIfNeeded();
        await expect.poll(() => image.evaluate(element => (
            element.complete && element.naturalWidth === 1440 && element.naturalHeight === 1000
        ))).toBe(true);
    }
    const records = await screenshots.evaluateAll(images => images.map(image => ({
        alt: image.alt,
        complete: image.complete,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
        source: image.getAttribute('src'),
        width: image.getAttribute('width'),
        height: image.getAttribute('height'),
    })));
    for (const record of records) {
        expect(record.alt.length).toBeGreaterThan(24);
        expect(record.complete).toBe(true);
        expect(record.naturalWidth).toBe(1440);
        expect(record.naturalHeight).toBe(1000);
        expect(record.source).toContain(`images/${language}/`);
        expect(record.width).toBe('1440');
        expect(record.height).toBe('1000');
    }
}

async function expectInternalLinks(page) {
    const links = await page.locator('a[href]').evaluateAll(anchors => (
        [...new Set(anchors.map(anchor => anchor.href))]
    ));
    for (const link of links) {
        const target = new URL(link);
        if (target.origin !== new URL(page.url()).origin) continue;
        const response = await page.request.get(target.href);
        expect(response.ok(), `Expected ${target.href} to load`).toBe(true);
        if (target.hash && target.pathname === new URL(page.url()).pathname) {
            const targetId = decodeURIComponent(target.hash.slice(1));
            expect(
                await page.evaluate(id => document.getElementById(id) !== null, targetId),
                `Expected ${target.hash} to identify an element`,
            ).toBe(true);
        }
    }
}

test('English and Portuguese tours use localized pages and image sets', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Meet your finances');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expectScreenshots(page, 'en');
    await expectInternalLinks(page);

    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'pt-BR');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Conheça suas finanças');
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
        await page.getByRole('link', { name: 'PT', exact: true }).click();
        await expect(page).toHaveURL(portugueseURL);
        await expect(page.getByRole('heading', { level: 1 })).toContainText('Conheça suas finanças');
        await page.getByRole('link', { name: 'PT', exact: true }).click();
        await expect(page).toHaveURL(portugueseURL);
        await page.getByRole('link', { name: 'EN', exact: true }).click();
        await expect(page).toHaveURL(englishURL);
        await expect(page.getByRole('heading', { level: 1 })).toContainText('Meet your finances');
    } finally {
        await context.close();
    }
});

test('theme toggle persists the selected preview theme', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(250, 248, 243)');
    await expect(page.locator('.screenshot-link').first()).toHaveCSS('background-color', 'rgb(255, 255, 255)');
    await page.getByRole('button', { name: 'Toggle light and dark theme' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 16, 16)');
    await expect(page.locator('.screenshot-link').first()).toHaveCSS('background-color', 'rgb(27, 27, 27)');
    await page.locator('.theme-toggle').hover();
    await expect(page.locator('.theme-toggle')).toHaveCSS('background-color', 'rgb(38, 38, 38)');
    await expect(page.getByRole('button', { name: 'Toggle light and dark theme' }))
        .toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 16, 16)');
    await page.getByRole('button', { name: 'Alternar entre os temas claro e escuro' }).click();
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(250, 248, 243)');
});

test('expanded screenshots close accessibly and restore focus', async ({ page }) => {
    await page.goto('/');
    const trigger = page.locator('[data-lightbox]').first();
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
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/pt-br/');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole('navigation', { name: 'Seções da prévia' })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Iniciar o tour' })).toBeVisible();
    await expectScreenshots(page, 'pt-br');
});
