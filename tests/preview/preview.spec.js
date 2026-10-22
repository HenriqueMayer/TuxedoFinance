const { test, expect } = require('@playwright/test');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const browserErrors = new WeakMap();
const workspaces = ['dashboard', 'transactions', 'banking', 'investments', 'planning', 'analytics', 'analytics-investments', 'new-entry'];
const primary = workspaces.slice(0, 6);
const workspaceParents = { 'analytics-investments': 'analytics', 'new-entry': 'transactions' };
const languages = [
    { code: 'en', url: '/', lang: 'en', home: 'The month, at a glance.', search: 'rent', result: 'Rent' },
    { code: 'pt-br', url: '/pt-br/', lang: 'pt-BR', home: 'Seu mês, em um olhar.', search: 'aluguel', result: 'Aluguel' },
];

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

async function openPreview(page, url) {
    await page.goto(url);
    await expect(page.locator('html')).toHaveAttribute('data-preview-ready', 'true');
    await page.evaluate(() => document.fonts.ready);
}

async function setTheme(page, theme) {
    if (await page.locator('html').getAttribute('data-theme') !== theme) {
        await page.locator('[data-theme-toggle]').click();
    }
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect(page.locator('[data-theme-toggle]')).toHaveAttribute('aria-pressed', String(theme === 'dark'));
}

async function expectWorkspace(page, workspace) {
    await expect(page.locator('html')).toHaveAttribute('data-workspace', workspace);
    await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(1);
    await expect(page.locator(`#${workspace}-title`)).toBeVisible();
    const owner = workspaceParents[workspace] || workspace;
    await expect(page.locator('[data-primary-navigation] [aria-current="page"]')).toHaveCount(1);
    await expect(page.locator(`[data-primary-navigation] [data-workspace-link="${owner}"]`)).toHaveAttribute('aria-current', 'page');
}

async function activateWithKeyboard(page, locator, key = 'Enter') {
    await locator.focus();
    await expect(locator).toBeFocused();
    await page.keyboard.press(key);
}

async function captureScrollAtLink(page, locator) {
    await locator.evaluate(link => {
        const top = window.scrollY + link.getBoundingClientRect().top - 280;
        window.scrollTo({ top, behavior: 'instant' });
        link.focus({ preventScroll: true });
    });
    await expect(locator).toBeInViewport({ ratio: 1 });
    const position = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
    expect(position.y).toBeGreaterThan(0);
    return position;
}

async function expectScrollUnchanged(page, position) {
    // Check painted frames after the content and focus update, not just the
    // synchronous click handler. Native anchors and scroll anchoring run later.
    const positions = await page.evaluate(() => new Promise(resolve => {
        requestAnimationFrame(() => {
            const first = { x: window.scrollX, y: window.scrollY };
            requestAnimationFrame(() => resolve([first, { x: window.scrollX, y: window.scrollY }]));
        });
    }));
    for (const current of positions) {
        expect(Math.abs(current.x - position.x)).toBeLessThanOrEqual(1);
        expect(Math.abs(current.y - position.y)).toBeLessThanOrEqual(1);
    }
}

async function clickWithoutScrolling(page, locator) {
    // A raw pointer click avoids Playwright scrolling a target into place and
    // accidentally hiding a page-location regression in the application.
    const bounds = await locator.boundingBox();
    await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
}

async function expectActionBounds(page, locator) {
    await expect(locator).toBeVisible();
    const bounds = await locator.boundingBox();
    const width = page.viewportSize().width;
    expect(bounds.x).toBeGreaterThanOrEqual(-0.5);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 0.5);
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(bounds.width).toBeGreaterThanOrEqual(44);
}

async function expectNoOverflow(page) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function expectInternalLinks(page) {
    const current = new URL(page.url());
    const links = await page.locator('a[href]').evaluateAll(anchors => [...new Set(anchors.map(anchor => anchor.href))]);
    const checkedPages = new Set();
    for (const link of links) {
        const target = new URL(link);
        if (target.origin !== current.origin) continue;
        const documentURL = `${target.origin}${target.pathname}${target.search}`;
        if (!checkedPages.has(documentURL)) {
            const response = await page.request.get(documentURL);
            expect(response.ok(), `Expected ${documentURL} to load`).toBe(true);
            checkedPages.add(documentURL);
        }
        if (target.hash && target.pathname === current.pathname) {
            expect(await page.evaluate(id => document.getElementById(id) !== null, decodeURIComponent(target.hash.slice(1))), `Expected anchor ${target.hash} to exist`).toBe(true);
        }
    }
}

for (const language of languages) {
    test(`the ${language.code} presentation introduces the product with native demo content`, async ({ page }) => {
        await openPreview(page, language.url);
        await expect(page.locator('html')).toHaveAttribute('lang', language.lang);
        await expect(page.locator('#hero-title')).toBeVisible();
        await expect(page.locator('#demo-title')).toBeVisible();
        await expect(page.locator('#assistant-title')).toBeVisible();
        await expect(page.locator('#how-title')).toBeVisible();
        await expect(page.locator('#dashboard-title')).toHaveText(language.home);
        await expect(page.locator('[data-workspace-view]')).toHaveCount(8);
        await expect(page.locator('[data-primary-navigation] a')).toHaveCount(6);
        await expectWorkspace(page, 'dashboard');
        // Interface content stays sharp and inspectable; raster screenshots no longer carry the tour.
        await expect(page.locator('[data-lightbox], #image-dialog, .workspace-content img')).toHaveCount(0);
        await expect(page.locator('.line-chart svg[role="img"]')).toHaveCount(1);
        await expect(page.locator('.line-chart svg')).toHaveAttribute('aria-label', /12[,.]400/);
        for (const image of await page.locator('img').all()) {
            expect(await image.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
        }
        await expectInternalLinks(page);
        for (const workspace of primary) {
            const link = page.locator(`[data-primary-navigation] [data-workspace-link="${workspace}"]`);
            await activateWithKeyboard(page, link);
            await expectWorkspace(page, workspace);
            await expect(page.locator(`#${workspace}-title`)).toBeFocused();
        }
        await activateWithKeyboard(page, page.locator('#analytics [data-workspace-link="analytics-investments"]'));
        await expectWorkspace(page, 'analytics-investments');
        await expect(page.locator('#analytics-investments-title')).toBeFocused();
        await activateWithKeyboard(page, page.locator('#analytics-investments [data-workspace-link="analytics"]'));
        await expectWorkspace(page, 'analytics');
        await activateWithKeyboard(page, page.locator('[data-primary-navigation] [data-workspace-link="transactions"]'));
        await activateWithKeyboard(page, page.locator('#transactions [data-workspace-link="new-entry"]'));
        await expectWorkspace(page, 'new-entry');
        await expect(page.locator('#new-entry-title')).toBeFocused();
    });

    test(`${language.code} example search handles keyboard input, no results and recovery`, async ({ page }) => {
        await openPreview(page, `${language.url}#transactions`);
        await expect(page.locator('#transactions-title')).toBeInViewport();
        const search = page.locator('#demo-search');
        const rows = page.locator('[data-demo-transaction]:visible');
        await expect(rows).toHaveCount(4);
        await search.focus();
        await page.keyboard.type(language.search.toUpperCase());
        await expect(rows).toHaveCount(1);
        await expect(rows).toContainText(language.result);
        await expect(search).toBeFocused();
        await expect(search).toHaveJSProperty('selectionStart', language.search.length);
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('no-such-example');
        await expect(rows).toHaveCount(0);
        await expect(page.locator('#demo-no-results')).toBeVisible();
        await expect(search).toBeFocused();
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.press('Backspace');
        await expect(rows).toHaveCount(4);
        await expect(page.locator('#demo-no-results')).toBeHidden();
        if (language.code === 'pt-br') {
            // The sample search accepts accent-free keyboard queries as well.
            await page.keyboard.type('salario');
            await expect(rows).toHaveCount(1);
            await expect(rows).toContainText('Salário mensal');
        }
    });

    test(`${language.code} assistant examples are keyboard operated and confirmation stays local`, async ({ page }) => {
        await openPreview(page, `${language.url}#assistant`);
        await expect(page.locator('[data-chat-view]:visible')).toHaveCount(1);
        await expect(page.locator('#chat-overview')).toBeVisible();
        const storageBefore = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
        const requests = [];
        page.on('request', request => requests.push({ url: request.url(), method: request.method() }));
        const originalURL = page.url();
        const simulate = page.locator('[data-chat-example="simulate"]');
        await activateWithKeyboard(page, simulate, 'Space');
        await expect(simulate).toBeFocused();
        await expect(simulate).toHaveAttribute('aria-pressed', 'true');
        await expect(page.locator('#chat-simulate')).toBeVisible();
        await expect(page.locator('#chat-simulate')).toContainText(/3[,.]040/);
        await expect(page.locator('#chat-simulate')).toContainText(/5[,.]460/);
        const budget = page.locator('[data-chat-example="budget"]');
        await activateWithKeyboard(page, budget);
        await expect(page.locator('#chat-budget')).toBeVisible();
        await expect(page.locator('#demo-confirmation')).toBeHidden();
        await activateWithKeyboard(page, page.locator('#demo-confirm'), 'Space');
        await expect(page.locator('#demo-confirmation')).toBeVisible();
        await expect(page.locator('#demo-confirmation')).toBeFocused();
        await expect(page.locator('#demo-confirmation')).toContainText(language.code === 'en' ? 'Nothing was saved here.' : 'Nada foi salvo aqui.');
        await expect(page.locator('#demo-confirm')).toBeHidden();
        await expect(page).toHaveURL(originalURL);
        expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }))).toEqual(storageBefore);
        expect(requests).toEqual([]);
        const overview = page.locator('[data-chat-example="overview"]');
        await activateWithKeyboard(page, overview);
        await expect(page.locator('#chat-overview')).toBeVisible();
        await expect(page.locator('[data-chat-view]:visible')).toHaveCount(1);
        await activateWithKeyboard(page, budget, 'Space');
        await expect(page.locator('#demo-confirm')).toBeVisible();
        await expect(page.locator('#demo-confirmation')).toBeHidden();
        await activateWithKeyboard(page, overview);
        await activateWithKeyboard(page, page.locator('#chat-overview [data-workspace-link="transactions"]'));
        await expectWorkspace(page, 'transactions');
        await expect(page).toHaveURL(/#transactions$/);
        await expect(page.locator('#transactions-title')).toBeInViewport();
    });
}

test('local HTML remains complete and navigable without JavaScript in both languages', async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
        const englishURL = pathToFileURL(path.resolve(__dirname, '../../preview/index.html')).href;
        const portugueseURL = pathToFileURL(path.resolve(__dirname, '../../preview/pt-br/index.html')).href;
        for (const [url, lang] of [[englishURL, 'en'], [portugueseURL, 'pt-BR']]) {
            await page.goto(url);
            await page.evaluate(() => document.fonts.ready);
            await expect(page.locator('html')).toHaveAttribute('lang', lang);
            await expect(page.locator('[data-workspace-view]:visible')).toHaveCount(8);
            await expect(page.locator('[data-chat-view]:visible')).toHaveCount(3);
            for (const selector of ['.search-field', '[data-theme-toggle]', '.assistant-examples', '#demo-confirm']) {
                await expect(page.locator(selector)).toBeHidden();
            }
            await expect(page.locator('.line-chart svg[role="img"]')).toBeVisible();
            // Reach each source before Enter; overlapping native smooth scrolls
            // from a distant programmatic focus do not represent keyboard use.
            await captureScrollAtLink(page, page.locator('#dashboard [data-workspace-link="new-entry"]'));
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(`${url}#new-entry`);
            await expect(page.locator('#new-entry-title')).toBeInViewport();
            await captureScrollAtLink(page, page.locator('[data-primary-navigation] [data-workspace-link="planning"]'));
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(`${url}#planning`);
            await expect(page.locator('#planning-title')).toBeInViewport();
            await page.getByRole('link', { name: lang === 'en' ? 'PT' : 'EN', exact: true }).click();
            await expect(page).toHaveURL(lang === 'en' ? portugueseURL : englishURL);
        }
    } finally { await context.close(); }
});

test('theme and selected workspace persist through reload and language navigation', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await openPreview(page, '/#planning');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await setTheme(page, 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-preview-ready', 'true');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expectWorkspace(page, 'planning');
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html#planning$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'pt-BR');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expectWorkspace(page, 'planning');
    await setTheme(page, 'light');
    await page.getByRole('link', { name: 'EN', exact: true }).click();
    await expect(page).toHaveURL(/\/index\.html#planning$/);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await expectWorkspace(page, 'planning');
});

test('workspace history recovers focus from hidden views and preserves parent navigation', async ({ page }) => {
    await openPreview(page, '/');
    // Reach visible links before keyboard activation, so browser history stores
    // a real demo location rather than an unfinished programmatic focus scroll.
    await captureScrollAtLink(page, page.locator('#dashboard [data-workspace-link="analytics"]'));
    await page.keyboard.press('Enter');
    await expectWorkspace(page, 'analytics');
    await expect(page.locator('#analytics-title')).toBeFocused();
    await captureScrollAtLink(page, page.locator('[data-primary-navigation] [data-workspace-link="transactions"]'));
    await page.keyboard.press('Enter');
    await page.locator('#demo-search').focus();
    await page.goBack();
    await expectWorkspace(page, 'analytics');
    await expect(page.locator('#analytics-title')).toBeFocused();
    await expect(page.locator('#analytics-title')).toBeInViewport();
    await page.goForward();
    await expectWorkspace(page, 'transactions');
    await expect(page.locator('#transactions-title')).toBeFocused();
    await expect(page.locator('#transactions-title')).toBeInViewport();
    await activateWithKeyboard(page, page.locator('#transactions [data-workspace-link="new-entry"]'));
    await expectWorkspace(page, 'new-entry');
    await expect(page.locator('#new-entry-title')).toBeFocused();
    await page.goBack();
    await expectWorkspace(page, 'transactions');
    await expect(page.locator('#transactions-title')).toBeFocused();
    await page.goForward();
    await expectWorkspace(page, 'new-entry');
    await page.getByRole('link', { name: 'PT', exact: true }).click();
    await expect(page).toHaveURL(/\/pt-br\/index\.html#new-entry$/);
    await expectWorkspace(page, 'new-entry');
});

test('legacy, landing and unknown fragments resolve predictably', async ({ page }) => {
    for (const [hash, workspace] of [['reports', 'analytics'], ['dashboard-preview', 'dashboard'], ['top', 'dashboard'], ['unknown-workspace', 'dashboard'], ['%E0%A4%A', 'dashboard']]) {
        await openPreview(page, `/#${hash}`);
        await expectWorkspace(page, workspace);
    }
    await openPreview(page, '/#investments');
    await activateWithKeyboard(page, page.locator('#investments [data-workspace-link="analytics-investments"]'));
    await expectWorkspace(page, 'analytics-investments');
    await activateWithKeyboard(page, page.locator('.page-nav a[href="#assistant"]'));
    await expect(page).toHaveURL(/#assistant$/);
    await expectWorkspace(page, 'analytics-investments');
    await expect(page.getByRole('link', { name: 'PT', exact: true })).toHaveAttribute('href', 'pt-br/index.html#assistant');
    await page.goBack();
    await expect(page).toHaveURL(/#analytics-investments$/);
    await expectWorkspace(page, 'analytics-investments');
    await activateWithKeyboard(page, page.locator('[data-primary-navigation] [data-workspace-link="analytics"]'));
    await expectWorkspace(page, 'analytics');
    const currentLink = page.locator('[data-primary-navigation] [data-workspace-link="analytics"]');
    const position = await captureScrollAtLink(page, currentLink);
    await clickWithoutScrolling(page, currentLink);
    await expectWorkspace(page, 'analytics');
    await expectScrollUnchanged(page, position);
});

for (const width of [1440, 390, 320]) {
    for (const theme of ['light', 'dark']) {
        test(`workspace changes preserve the current page position (${width}, ${theme})`, async ({ page }) => {
            await page.setViewportSize({ width, height: 900 });
            await page.emulateMedia({ colorScheme: theme });
            await openPreview(page, '/pt-br/');
            const paneHeights = new Set();
            // The tour contains short and long workspaces, so both replacement
            // and layout-height changes must preserve the user's page position.
            for (const workspace of ['banking', 'dashboard', 'transactions', 'investments', 'planning', 'analytics']) {
                const link = page.locator(`[data-primary-navigation] [data-workspace-link="${workspace}"]`);
                const position = await captureScrollAtLink(page, link);
                await clickWithoutScrolling(page, link);
                await expectWorkspace(page, workspace);
                await expect(page).toHaveURL(new RegExp(`#${workspace}$`));
                await expect(link).toBeFocused();
                await expectScrollUnchanged(page, position);
                paneHeights.add(Math.round((await page.locator('.demo-window').boundingBox()).height));
            }
            expect(paneHeights.size).toBeGreaterThan(1);

            // Re-selecting the active workspace must not realign the demo.
            const currentLink = page.locator('[data-primary-navigation] [data-workspace-link="analytics"]');
            let position = await captureScrollAtLink(page, currentLink);
            await clickWithoutScrolling(page, currentLink);
            await expectScrollUnchanged(page, position);
            await expect(currentLink).toBeFocused();

            // Nested transitions move focus out of the view being hidden while
            // leaving the outer document at its current position.
            for (const [source, destination] of [['analytics', 'analytics-investments'], ['analytics-investments', 'analytics']]) {
                const link = page.locator(`#${source} [data-workspace-link="${destination}"]`);
                position = await captureScrollAtLink(page, link);
                await clickWithoutScrolling(page, link);
                await expectWorkspace(page, destination);
                await expect(page.locator(`#${destination}-title`)).toBeFocused();
                await expectScrollUnchanged(page, position);
            }

            for (const workspace of ['transactions', 'transactions']) {
                const link = page.locator(`[data-primary-navigation] [data-workspace-link="${workspace}"]`);
                position = await captureScrollAtLink(page, link);
                await page.keyboard.press('Enter');
                await expectWorkspace(page, workspace);
                await expect(page.locator(`#${workspace}-title`)).toBeFocused();
                await expectScrollUnchanged(page, position);
            }
            const entryLink = page.locator('#transactions [data-workspace-link="new-entry"]');
            position = await captureScrollAtLink(page, entryLink);
            await page.keyboard.press('Enter');
            await expectWorkspace(page, 'new-entry');
            await expect(page.locator('#new-entry-title')).toBeFocused();
            await expectScrollUnchanged(page, position);
        });
    }
}

test('skip navigation moves keyboard focus without replacing the workspace fragment', async ({ page }) => {
    await openPreview(page, '/');
    await page.keyboard.press('Tab');
    await expect(page.locator('.skip-link')).toBeFocused();
    await activateWithKeyboard(page, page.locator('[data-primary-navigation] [data-workspace-link="banking"]'));
    await expectWorkspace(page, 'banking');
    await expect(page.locator('#banking-title')).toBeFocused();
    await activateWithKeyboard(page, page.locator('.skip-link'));
    await expect(page.locator('#main')).toBeFocused();
    await expectWorkspace(page, 'banking');
    await expect(page).toHaveURL(/#banking$/);
});

for (const language of languages) {
    for (const width of [1440, 768, 390, 320]) {
        for (const theme of ['light', 'dark']) {
            test(`presentation keeps readable actions and viewport bounds (${language.code}, ${width}, ${theme})`, async ({ page }, testInfo) => {
                await page.setViewportSize({ width, height: 900 });
                await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
                await openPreview(page, language.url);
                await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
                await expectNoOverflow(page);
                await page.screenshot({ path: testInfo.outputPath('landing.png'), animations: 'disabled' });
                for (const workspace of primary) {
                    const link = page.locator(`[data-primary-navigation] [data-workspace-link="${workspace}"]`);
                    await activateWithKeyboard(page, link);
                    await expectWorkspace(page, workspace);
                    await expect(page.locator(`#${workspace}-title`)).toBeFocused();
                    await expectActionBounds(page, link);
                    const linkBounds = await link.boundingBox();
                    for (const label of await link.locator('span:visible').all()) {
                        const labelBounds = await label.boundingBox();
                        expect(labelBounds.x).toBeGreaterThanOrEqual(linkBounds.x);
                        expect(labelBounds.x + labelBounds.width).toBeLessThanOrEqual(linkBounds.x + linkBounds.width + 0.5);
                    }
                    await expectNoOverflow(page);
                }
                await activateWithKeyboard(page, page.locator('#analytics [data-workspace-link="analytics-investments"]'));
                await expectWorkspace(page, 'analytics-investments');
                await expectNoOverflow(page);
                await activateWithKeyboard(page, page.locator('[data-primary-navigation] [data-workspace-link="transactions"]'));
                const entry = page.locator('#transactions [data-workspace-link="new-entry"]');
                await expectActionBounds(page, entry);
                await activateWithKeyboard(page, entry);
                await expectWorkspace(page, 'new-entry');
                await expect(page.locator('#new-entry-title')).toBeInViewport();
                await expectNoOverflow(page);
                await page.screenshot({ path: testInfo.outputPath('workspace.png'), animations: 'disabled' });
                for (const [index, example] of ['overview', 'simulate', 'budget'].entries()) {
                    const button = page.locator(`[data-chat-example="${example}"]`);
                    await activateWithKeyboard(page, button, index % 2 ? 'Space' : 'Enter');
                    await expect(button).toBeFocused();
                    await expectActionBounds(page, button);
                    await expect(page.locator(`#chat-${example}`)).toBeVisible();
                    await expect(page.locator('[data-chat-view]:visible')).toHaveCount(1);
                    await expectNoOverflow(page);
                }
                const confirm = page.locator('#demo-confirm');
                await confirm.focus();
                await expectActionBounds(page, confirm);
                await expect(confirm).toBeInViewport();
                await page.screenshot({ path: testInfo.outputPath('assistant.png'), animations: 'disabled' });
                await page.keyboard.press('Enter');
                await expect(page.locator('#demo-confirmation')).toBeVisible();
                await expect(page.locator('#demo-confirmation')).toBeFocused();
                await expectNoOverflow(page);
                const finalAction = page.locator('.closing-actions a').last();
                await finalAction.focus();
                await expectActionBounds(page, finalAction);
                await expect(finalAction).toBeInViewport();
            });
        }
    }
}

test('embedded presentations open repository links safely and retain the preview', async ({ page }) => {
    await page.context().route('https://github.com/HenriqueMayer/TuxedoFinance**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Repository destination</h1>' }));
    for (const source of ['/index.html', '/pt-br/index.html']) {
        await page.route('**/embedded-tour-test.html', route => route.fulfill({ contentType: 'text/html', body: `<style>body{margin:0}iframe{display:block;width:100%;height:720px;border:0}</style><iframe title="Tour" src="${source}" sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>` }));
        await page.goto('/embedded-tour-test.html');
        const tour = page.frameLocator('iframe');
        const links = tour.locator('.header-external a');
        await expect(links).toHaveCount(2);
        for (let index = 0; index < 2; index += 1) {
            await expect(links.nth(index)).toHaveAttribute('target', '_blank');
            await expect(links.nth(index)).toHaveAttribute('rel', /noopener/);
            const popupPromise = page.waitForEvent('popup');
            await links.nth(index).click();
            const popup = await popupPromise;
            await expect(popup.getByRole('heading')).toHaveText('Repository destination');
            expect(popup.url()).toContain('https://github.com/HenriqueMayer/TuxedoFinance');
            expect(await popup.evaluate(() => window.opener === null)).toBe(true);
            await expect(tour.locator('#hero-title')).toBeVisible();
            await expect(page).toHaveURL(/embedded-tour-test\.html$/);
            await popup.close();
        }
        await page.unroute('**/embedded-tour-test.html');
    }
});
