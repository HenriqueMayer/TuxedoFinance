// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');
const { selectChoice } = require('./helpers/forms');

async function openCatalogue(page, hash = '') {
    const root = resolve(__dirname, '../..');
    await page.route('**/catalogue/**', async route => {
        const name = new URL(route.request().url()).pathname.slice('/catalogue/'.length);
        const documents = ['docs/design-system.html', 'docs/design-system.css', 'docs/design-system.js', 'docs/design-system-layers.js', 'docs/design-system-calendar.js'];
        if ((!documents.includes(name) && !name.startsWith('static/')) || name.split('/').includes('..')) return route.abort();
        const types = { html: 'text/html', css: 'text/css', js: 'application/javascript',
            woff2: 'font/woff2', png: 'image/png', jpg: 'image/jpeg', ico: 'image/x-icon' };
        await route.fulfill({ path: resolve(root, name), contentType: types[name.split('.').pop()] });
    });
    await page.goto(`/catalogue/docs/design-system.html${hash}`);
}

async function submitPreview(page) {
    await page.locator('#lab-transaction-form').getByRole('button', { name: 'Preview entry', exact: true }).press('Enter');
}

async function expectAnchorBelowHeader(page, target) {
    await expect(target).toBeInViewport();
    await expect.poll(() => target.evaluate(node => {
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        return node.getBoundingClientRect().top - header.bottom;
    })).toBeGreaterThanOrEqual(-2);
}

async function ctaPresentation(button) {
    return button.evaluate(async node => {
        // Read after real pointer/keyboard events and their CSS transitions,
        // rather than sampling a potentially unchanged first animation frame.
        getComputedStyle(node).borderRadius;
        await Promise.all(node.getAnimations({subtree: true}).map(animation => animation.finished.catch(() => {})));
        const bounds = node.getBoundingClientRect();
        const arrow = node.querySelector('.lab-arrow');
        const arrowBounds = arrow.getBoundingClientRect();
        const style = getComputedStyle(node);
        const range = document.createRange();
        const label = [...node.childNodes].find(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        range.selectNodeContents(label);
        const text = range.getBoundingClientRect();
        return {
            width: bounds.width, height: bounds.height,
            layout: [node.offsetLeft, node.offsetTop, node.offsetWidth, node.offsetHeight],
            label: [text.left - bounds.left, text.top - bounds.top, text.width, text.height],
            groupCenter: (Math.min(text.left, arrowBounds.left) + Math.max(text.right, arrowBounds.right)) / 2 - bounds.left,
            radii: [style.borderTopLeftRadius, style.borderTopRightRadius,
                style.borderBottomRightRadius, style.borderBottomLeftRadius],
            transform: style.transform, arrowTransform: getComputedStyle(arrow).transform,
            arrowLeft: arrowBounds.left - bounds.left, arrowTop: arrowBounds.top - bounds.top,
            arrowWidth: arrowBounds.width, arrowHeight: arrowBounds.height,
            background: style.backgroundColor, border: style.borderColor,
            outlineWidth: parseFloat(style.outlineWidth), outlineStyle: style.outlineStyle,
            outlineColor: style.outlineColor,
        };
    });
}

function expectStableCTA(actual, baseline) {
    expect(actual.radii).toEqual(baseline.radii);
    expect(actual.layout, 'Hover and focus cannot reflow the action target').toEqual(baseline.layout);
    actual.label.forEach((value, index) => expect(value, 'CTA text does not reflow').toBeCloseTo(baseline.label[index], 1));
    for (const dimension of ['width', 'height', 'arrowWidth', 'arrowHeight']) {
        expect(actual[dimension], `Stable CTA ${dimension}`).toBeCloseTo(baseline[dimension], 1);
    }
    for (const dimension of ['arrowLeft', 'arrowTop']) {
        expect(Math.abs(actual[dimension] - baseline[dimension]), 'Subtle arrow response stays within 2px').toBeLessThanOrEqual(2);
    }
}

async function chooseType(page, kind) {
    const expense = page.locator('#lab-entry-type-expense');
    await expense.focus();
    await expense.press(kind === 'INCOME' ? 'ArrowRight' : 'Space');
    const selected = page.locator(kind === 'INCOME' ? '#lab-entry-type-income' : '#lab-entry-type-expense');
    await expect(selected).toBeChecked();
    await selected.press('Tab');
}

async function keyboardRecovery(page, info) {
    const form = page.locator('#lab-transaction-form');
    const amount = page.locator('#lab-entry-amount');
    const type = page.locator('#lab-entry-type');
    const title = page.locator('#lab-entry-title');
    const category = page.locator('#lab-entry-category');
    const categorySearch = page.locator('#lab-entry-category-search');
    const account = page.locator('#lab-entry-account');
    const accountSearch = page.locator('#lab-entry-account-search');
    const day = page.locator('#lab-entry-date');
    const payment = page.locator('#lab-entry-payment');
    const accountMethod = payment.locator('input[value="ACCOUNT"]');
    const result = page.locator('#lab-entry-result');
    await expect(form).toHaveAttribute('data-lab-enhanced', 'true');
    await expect(type.locator('input:checked')).toHaveCount(0);
    await expect(payment).toBeHidden();
    await expect(categorySearch).toBeHidden();
    await expect(accountSearch).toBeHidden();
    await expect(category).toBeDisabled();
    await expect(account).toBeDisabled();
    await submitPreview(page);
    await expect(page.locator('#lab-entry-type-expense')).toBeFocused();
    await expect(page.locator('#lab-entry-type-error')).toBeVisible();
    await expect(page.locator('#lab-entry-category-error')).toBeHidden();
    await expect(page.locator('#lab-entry-account-error')).toBeHidden();
    await chooseType(page, 'EXPENSE');
    await expect(categorySearch).toBeVisible();
    await expect(categorySearch).toHaveAttribute('role', 'combobox');
    await expect(category).toHaveValue('');
    await expect(payment.locator('input:checked')).toHaveCount(0);
    await expect(accountSearch).toBeHidden();
    await submitPreview(page);
    await expect(title).toBeFocused();
    await expect(page.locator('#lab-entry-title-error')).toBeVisible();
    await title.fill('Saturday <groceries>');
    await submitPreview(page);
    await expect(amount).toBeFocused();
    await amount.fill('-1');
    await submitPreview(page);
    await expect(amount).toBeFocused();
    await expect(page.locator('#lab-entry-amount-error')).toContainText('positive amount');
    await expect(title).toHaveValue('Saturday <groceries>');
    await amount.fill('1250,50');
    await submitPreview(page);
    await expect(day).toBeFocused();
    await expect(page.locator('#lab-entry-date-error')).toBeVisible();
    await expect(categorySearch).toHaveAttribute('aria-invalid', 'true');
    await expect(categorySearch).toHaveAttribute('aria-describedby', /lab-entry-category-error/);
    await expect(categorySearch).toHaveAttribute('aria-describedby', /lab-entry-category-search-help/);
    await day.fill('2026-10-17');
    await submitPreview(page);
    await expect(categorySearch).toBeFocused();
    await categorySearch.fill('No matching category');
    await categorySearch.press('Enter');
    await expect(category).toHaveValue('');
    await expect(result).not.toHaveAttribute('data-lab-state', 'created');
    await selectChoice(category, '1001');
    await expect(categorySearch).not.toHaveAttribute('aria-invalid', 'true');
    await expect(categorySearch).toHaveAttribute('aria-describedby', /lab-entry-category-search-help/);
    await submitPreview(page);
    await expect(accountMethod).toBeFocused();
    await accountMethod.press('Space');
    await expect(accountMethod).toBeChecked();
    await expect(accountSearch).toBeVisible();
    await expect(account).toHaveValue('');
    await submitPreview(page);
    await expect(accountSearch).toBeFocused();
    await expect(accountSearch).toHaveAttribute('aria-invalid', 'true');
    await selectChoice(account, '2001');
    await expect(accountSearch).not.toHaveAttribute('aria-invalid', 'true');
    await submitPreview(page);
    await expect(result).toHaveAttribute('data-lab-state', 'created');
    await expect(result).toContainText('Preview created: Saturday <groceries>');
    await expect(result).toContainText('BRL 1,250.50');
    await expect(result).toContainText('Account transfer');
    await expect(result).toContainText('Nothing has been saved.');
    await expect(result.locator('*')).toHaveCount(0);
    await expect(category).toHaveValue('1001');
    await expect(account).toHaveValue('2001');
    await expect(form.locator('[data-lab-error-for]:not([hidden])')).toHaveCount(0);
    expect(new URL(page.url()).search).toBe('');
    await page.screenshot({path: info.outputPath('entry-preview.png'), fullPage: true});
    const reset = form.locator('[data-lab-reset]');
    await reset.press('Enter');
    await expect(reset).toBeFocused();
    await expect(type.locator('input:checked')).toHaveCount(0);
    await expect(payment.locator('input:checked')).toHaveCount(0);
    await expect(payment).toBeHidden();
    for (const field of [amount, title, day, category, account, categorySearch, accountSearch]) {
        await expect(field).toHaveValue('');
    }
    await expect(categorySearch).toBeHidden();
    await expect(accountSearch).toBeHidden();
    await expect(form.locator('[aria-invalid="true"]')).toHaveCount(0);
    await expect(form.locator('[data-lab-error-for]:not([hidden])')).toHaveCount(0);
    await expect(result).toBeEmpty();
    await expect(page.locator('#lab-state-error')).toHaveAttribute('aria-invalid', 'true');
}

for (const theme of ['light', 'dark']) {
    test(`catalogue centered CTAs preserve targets with subtle hover and keyboard feedback (${theme})`, async ({ page }, info) => {
        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await openCatalogue(page, '#navigation');
        await page.evaluate(() => document.fonts.ready);
        const navigation = page.locator('[data-lab-navigation]');
        const accountMenu = page.locator('.lab-workspace-toolbar .lab-account-menu');
        const accountSummary = accountMenu.locator('summary');
        let homePresentation;
        for (const destination of ['home', 'transactions']) {
            const link = navigation.locator(`[data-lab-destination="${destination}"]`);
            await link.focus();
            await link.press('Enter');
            await expect(link).toBeFocused();
            const view = page.locator(`[data-lab-view="${destination}"]`);
            await expect(view).toBeVisible();
            const button = view.getByRole('link', { name: 'New entry', exact: true });
            await expect(button.locator('.lab-arrow')).toHaveCount(1);
            await page.mouse.move(0, 0);
            await button.scrollIntoViewIfNeeded();
            const resting = await ctaPresentation(button);
            expect(resting.height).toBeGreaterThanOrEqual(44);
            expect(Math.abs(resting.groupCenter - resting.width / 2), 'The label and arrow group is centered').toBeLessThanOrEqual(1.5);
            if (!homePresentation) homePresentation = resting;
            else {
                expect(resting.height).toBeCloseTo(homePresentation.height, 1);
                expect(resting.width).toBeCloseTo(homePresentation.width, 1);
                expect(resting.radii).toEqual(homePresentation.radii);
            }

            await button.hover();
            expect(await button.evaluate(node => node.matches(':hover'))).toBe(true);
            const hovered = await ctaPresentation(button);
            expectStableCTA(hovered, resting);
            expect([hovered.background, hovered.border]).not.toEqual([resting.background, resting.border]);

            await page.mouse.move(0, 0);
            await ctaPresentation(button);
            await expect(accountMenu).not.toHaveAttribute('open');
            await accountSummary.focus();
            // A real Tab reaches the first action in the selected view.
            await page.keyboard.press('Tab');
            await expect(button).toBeFocused();
            expect(await button.evaluate(node => node.matches(':focus-visible'))).toBe(true);
            const focused = await ctaPresentation(button);
            expectStableCTA(focused, resting);
            expect(focused.outlineWidth).toBeGreaterThanOrEqual(2);
            expect(focused.outlineStyle).not.toBe('none');
            expect(focused.outlineColor).not.toBe('rgba(0, 0, 0, 0)');
            await button.screenshot({ path: info.outputPath(`stable-cta-${destination}-${theme}.png`) });
        }

        await page.emulateMedia({ reducedMotion: 'reduce' });
        for (const destination of ['home', 'transactions']) {
            const link = navigation.locator(`[data-lab-destination="${destination}"]`);
            await link.focus();
            await link.press('Enter');
            await expect(link).toBeFocused();
            const view = page.locator(`[data-lab-view="${destination}"]`);
            await expect(view).toBeVisible();
            const running = await view.evaluate(node => node.getAnimations({subtree: true})
                .filter(animation => animation.playState === 'running').length);
            expect(running, 'Reduced motion disables the navigation fade').toBe(0);
        }
    });

    for (const width of [1440, 390]) {
        test(`catalogue experiment keeps five destinations and local keyboard recovery (${width}, ${theme})`, async ({ page }, info) => {
            await page.setViewportSize({ width, height: 900 });
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            if (theme === 'dark' && width === 390) await page.emulateMedia({ reducedMotion: 'reduce' });
            const browserErrors = [];
            page.on('pageerror', error => browserErrors.push(error.message));
            await openCatalogue(page);
            const writes = [];
            page.on('request', request => {
                if (request.method() !== 'GET' || ['xhr', 'fetch'].includes(request.resourceType())) writes.push(request.url());
            });
            const navigation = page.locator('[data-lab-navigation]');
            await expect(navigation.getByRole('link')).toHaveCount(5);
            await expect(navigation.locator('[role="tab"]')).toHaveCount(0);
            const historyLength = await page.evaluate(() => history.length);
            for (const destination of ['home', 'transactions', 'accounts', 'investments', 'plan']) {
                const link = navigation.locator(`[data-lab-destination="${destination}"]`);
                await link.focus();
                await link.press('Enter');
                await expect(link).toBeFocused();
                await expect(link).toHaveAttribute('aria-current', 'page');
                await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1);
                await expect(page.locator('section[data-lab-view]:not([hidden])')).toHaveCount(1);
                await expect(page.locator(`#lab-view-${destination}`)).toBeVisible();
                await expect(page).toHaveURL(new RegExp(`#lab-view-${destination}$`));
                expect(await page.evaluate(() => history.length)).toBe(historyLength);
                expect(await page.evaluate(() => scrollY)).toBeGreaterThan(100);
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({ path: info.outputPath('workspace-navigation.png'), fullPage: true });
            await keyboardRecovery(page, info);
            expect(writes).toEqual([]);
            expect(browserErrors).toEqual([]);
        });
    }

    test(`catalogue entry type changes clear incompatible categories and preserve compatible context (${theme})`, async ({ page }, info) => {
        await page.setViewportSize({ width: 390, height: 900 });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await openCatalogue(page, '#forms');
        const form = page.locator('#lab-transaction-form');
        const expense = page.locator('#lab-entry-type-expense');
        const income = page.locator('#lab-entry-type-income');
        const amount = page.locator('#lab-entry-amount');
        const title = page.locator('#lab-entry-title');
        const category = page.locator('#lab-entry-category');
        const categorySearch = page.locator('#lab-entry-category-search');
        const account = page.locator('#lab-entry-account');
        const accountSearch = page.locator('#lab-entry-account-search');
        const day = page.locator('#lab-entry-date');
        const result = page.locator('#lab-entry-result');
        await expect(form).toHaveAttribute('data-lab-enhanced', 'true');

        await chooseType(page, 'EXPENSE');
        await amount.fill('120.00');
        await title.fill('Type transition example');
        await day.fill('2026-10-16');
        await selectChoice(category, '1001');
        await page.locator('#lab-entry-payment input[value="ACCOUNT"]').press('Space');
        await selectChoice(account, '2001');
        await submitPreview(page);
        await expect(result).toHaveAttribute('data-lab-state', 'created');

        await expense.focus();
        await expense.press('ArrowRight');
        await expect(income).toBeChecked();
        await income.press('Tab');
        await expect(category).toHaveValue('');
        await expect(categorySearch).toHaveValue('');
        await expect(category.locator('option[value="1001"]')).toBeDisabled();
        await expect(category.locator('option[value="1001"]')).toHaveAttribute('hidden', '');
        await expect(category.locator('option[value="1004"]')).toBeEnabled();
        await expect(category.locator('option[value="1004"]')).not.toHaveAttribute('hidden');
        await expect(page.locator('[data-lab-account-label]')).toHaveText('Received into');
        await expect(accountSearch).toHaveAccessibleName(/Received into/);
        await expect(page.locator(`#${await accountSearch.getAttribute('aria-controls')}`)).toHaveAttribute('aria-label', /Received into/);
        await expect(accountSearch.locator('..').getByRole('button')).toHaveAccessibleName(/Received into/);
        await expect(amount).toHaveValue('120.00');
        await expect(title).toHaveValue('Type transition example');
        await expect(day).toHaveValue('2026-10-16');
        await expect(account).toHaveValue('2001');
        await expect(result).toBeEmpty();

        await submitPreview(page);
        await expect(categorySearch).toBeFocused();
        await expect(page.locator('#lab-entry-category-error')).toBeVisible();
        await categorySearch.fill('Salary');
        await expect(categorySearch.locator('..').getByRole('option')).toHaveText(['Income · Salary']);
        await categorySearch.press('ArrowDown');
        await categorySearch.press('Enter');
        await expect(category).toHaveValue('1004');
        await expect(categorySearch).not.toHaveAttribute('aria-invalid', 'true');
        await submitPreview(page);
        await expect(result).toContainText('Preview created: Type transition example');
        await expect(result).toContainText('BRL 120.00');
        await expect(result).toContainText('Account transfer');
        await expect(form.locator('[data-lab-error-for]:not([hidden])')).toHaveCount(0);

        await income.focus();
        await income.press('ArrowLeft');
        await expect(expense).toBeChecked();
        await expense.press('Tab');
        await expect(category).toHaveValue('');
        await expect(categorySearch).toHaveValue('');
        await expect(page.locator('[data-lab-account-label]')).toHaveText('Paid from');
        await expect(accountSearch).toHaveAccessibleName(/Paid from/);
        await expect(account).toHaveValue('2001');
        await selectChoice(category, '1002');
        await submitPreview(page);
        await expect(result).toHaveAttribute('data-lab-state', 'created');
        await expect(category).toHaveValue('1002');
        await expect(amount).toHaveValue('120.00');
        await expect(title).toHaveValue('Type transition example');
        await expect(day).toHaveValue('2026-10-16');
        expect(new URL(page.url()).search).toBe('');
        await page.screenshot({ path: info.outputPath('entry-type-transition.png'), fullPage: true });
    });
}

test('catalogue experiment preserves native links and a read-only GET without JavaScript', async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    try {
        const page = await context.newPage();
        await openCatalogue(page);
        await expect(page.locator('section[data-lab-view]:not([hidden])')).toHaveCount(5);
        await page.locator('[data-lab-destination="plan"]').press('Enter');
        await expect(page).toHaveURL(/#lab-view-plan$/);
        await expect(page.locator('section[data-lab-view]:not([hidden])')).toHaveCount(5);
        const type = page.locator('#lab-entry-type-expense');
        const amount = page.locator('#lab-entry-amount');
        await submitPreview(page);
        await expect(type).toBeFocused();
        expect(await type.evaluate(input => input.validity.valueMissing)).toBe(true);
        await expect(page.locator('#lab-entry-category')).toBeVisible();
        await expect(page.locator('#lab-entry-category-search')).toHaveCount(0);
        await type.press('Space');
        await expect(type).toBeChecked();
        await amount.fill('12.50');
        await page.locator('#lab-entry-title').fill('Native catalogue example');
        await page.locator('#lab-entry-category').selectOption('1001');
        await page.locator('#lab-entry-payment input[value="ACCOUNT"]').press('Space');
        await page.locator('#lab-entry-account').selectOption('2001');
        await page.locator('#lab-entry-date').fill('2026-10-16');
        const submitted = page.waitForRequest(request => request.isNavigationRequest()
            && new URL(request.url()).searchParams.get('title') === 'Native catalogue example');
        await submitPreview(page);
        expect((await submitted).method()).toBe('GET');
        await expect(page).toHaveURL(url => url.pathname === '/catalogue/docs/design-system.html'
            && url.searchParams.get('amount') === '12.50' && url.searchParams.get('category') === '1001'
            && url.searchParams.get('payment_method') === 'ACCOUNT' && url.searchParams.get('account') === '2001' && url.hash === '#forms');
        await expect(page.locator('#lab-entry-result')).not.toHaveAttribute('data-lab-state', 'created');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath('native-catalogue-form.png'), fullPage: true });
    } finally {
        await context.close();
    }
});

for (const theme of ['light', 'dark']) {
    test(`catalogue experiment keeps responsive targets, internal anchors and reduced motion (${theme})`, async ({ page }, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await openCatalogue(page);
        const homepage = page.locator('#public-homepage');
        const navigation = page.locator('[data-lab-navigation]');
        for (const width of [320, 768, 1024, 1920]) {
            await page.setViewportSize({ width, height: 1000 });
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow at ${width}px`).toBe(true);
            const art = page.locator('[data-lab-bowtie]');
            const outlineSpace = await art.getByRole('button', {name: 'Explore workspaces', exact: true}).evaluate(button => {
                const scene = button.closest('[data-lab-bowtie]').getBoundingClientRect();
                const bounds = button.getBoundingClientRect();
                // The SVG uses an inset focus ring; its frame stays contained
                // while only the printed paper moves within it.
                return {left: bounds.left - scene.left, right: scene.right - bounds.right,
                    bottom: scene.bottom - bounds.bottom, target: bounds.height};
            });
            expect(outlineSpace.target).toBeGreaterThanOrEqual(44);
            for (const edge of ['left', 'right', 'bottom']) expect(outlineSpace[edge]).toBeGreaterThanOrEqual(-1);
            const targets = await navigation.getByRole('link').evaluateAll(links => links.map(link => {
                const bounds = link.getBoundingClientRect();
                const label = link.querySelector(':scope > span').getBoundingClientRect();
                return {name: link.textContent.trim(), width: bounds.width, height: bounds.height,
                    labelSpace: {left: label.left - bounds.left, right: bounds.right - label.right,
                        top: label.top - bounds.top, bottom: bounds.bottom - label.bottom}};
            }));
            expect(targets).toHaveLength(5);
            for (const target of targets) {
                expect(target.width, `${target.name} width at ${width}px`).toBeGreaterThanOrEqual(44);
                expect(target.height, `${target.name} height at ${width}px`).toBeGreaterThanOrEqual(44);
                for (const [edge, space] of Object.entries(target.labelSpace)) {
                    expect(space, `${target.name} label ${edge} containment at ${width}px`).toBeGreaterThanOrEqual(0);
                }
            }
            const login = homepage.getByRole('link', {name: 'Log in', exact: true});
            await login.focus();
            await login.press('Enter');
            await expect(page).toHaveURL(/#lab-login$/);
            await expectAnchorBelowHeader(page, page.locator('#lab-login'));
            const closer = homepage.getByRole('link', {name: 'View features', exact: true});
            await closer.focus();
            await closer.press('Enter');
            await expect(page).toHaveURL(/#lab-home-features$/);
            await expectAnchorBelowHeader(page, page.locator('#lab-home-features'));
        }

        await page.emulateMedia({ reducedMotion: 'reduce' });
        expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
        const durations = await page.locator('.lab-button, .lab-arrow, [data-lab-navigation] a')
            .evaluateAll(nodes => nodes.map(node => getComputedStyle(node).transitionDuration));
        expect(durations.length).toBeGreaterThan(5);
        expect(durations.every(duration => duration === '0s'), JSON.stringify(durations)).toBe(true);

        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.goto('/catalogue/docs/design-system.html#public-homepage');
        await expectAnchorBelowHeader(page, homepage);
        await page.screenshot({ path: info.outputPath(`homepage-${theme}.png`) });
        await page.locator('.lab-workspace').screenshot({ path: info.outputPath(`navigation-${theme}.png`) });
        await chooseType(page, 'EXPENSE');
        await expect(page.locator('#lab-entry-category-search')).toBeVisible();
        const metadata = await page.locator('#lab-entry-title, #lab-entry-amount, #lab-entry-date, #lab-entry-category-search')
            .evaluateAll(nodes => nodes.map(node => {
                const bounds = node.getBoundingClientRect();
                return {left: bounds.left, top: bounds.top, width: bounds.width, height: bounds.height};
            }));
        expect(metadata).toHaveLength(4);
        metadata.forEach(control => {
            expect(control.height, 'Every entry detail uses the same 44px control height').toBeCloseTo(44, 1);
        });
        expect(metadata[0].top).toBeCloseTo(metadata[1].top, 1);
        expect(metadata[2].top).toBeCloseTo(metadata[3].top, 1);
        expect(metadata[2].top).toBeGreaterThan(metadata[0].top);
        expect(metadata[0].left).toBeCloseTo(metadata[2].left, 1);
        expect(metadata[1].left).toBeCloseTo(metadata[3].left, 1);
        expect(metadata[0].width).toBeCloseTo(metadata[2].width, 1);
        expect(metadata[1].width).toBeCloseTo(metadata[3].width, 1);
        await page.locator('.lab-entry-layout').screenshot({ path: info.outputPath(`form-${theme}.png`) });
    });
}
