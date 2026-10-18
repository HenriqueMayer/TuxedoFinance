// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');
const { selectChoice } = require('./helpers/forms');

async function openCatalogue(page, theme = 'light') {
    // Freeze Date only: native events, animation frames and timers stay real.
    await page.clock.setFixedTime('2026-10-17T15:00:00Z');
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const root = resolve(__dirname, '../..');
    await page.route('**/catalogue/**', async route => {
        const name = new URL(route.request().url()).pathname.slice('/catalogue/'.length);
        const documents = ['docs/design-system.html', 'docs/design-system.css', 'docs/design-system.js',
            'docs/design-system-layers.js', 'docs/design-system-calendar.js'];
        if ((!documents.includes(name) && !name.startsWith('static/')) || name.split('/').includes('..')) return route.abort();
        const types = {html: 'text/html', css: 'text/css', js: 'application/javascript',
            woff2: 'font/woff2', png: 'image/png', jpg: 'image/jpeg', ico: 'image/x-icon'};
        await route.fulfill({path: resolve(root, name), contentType: types[name.split('.').pop()]});
    });
    await page.goto('/catalogue/docs/design-system.html#forms');
    await page.evaluate(() => document.fonts.ready);
}

function calendar(page) { return page.getByRole('dialog', {name: 'Choose date', exact: true}); }
function action(page, name) { return calendar(page).locator('[data-calendar-action="' + name + '"]'); }

async function expectFits(page) {
    await expect(calendar(page)).toBeVisible();
    expect(await calendar(page).evaluate(node => {
        const box = node.getBoundingClientRect();
        return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight
            && node.scrollWidth <= node.clientWidth;
    }), 'The modal fits the viewport and scrolls content internally').toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator('dialog[open]')).toHaveCount(1);
    expect(await calendar(page).evaluate(node => node instanceof HTMLDialogElement && node.matches(':modal')),
        'The shared calendar uses a native modal dialog').toBe(true);
}

async function expectReturnedFocus(page, input) {
    await expect(calendar(page)).not.toBeVisible();
    await expect(input).toBeFocused();
    await expect.poll(() => input.evaluate(node => {
        const box = node.getBoundingClientRect();
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        return box.top >= header.bottom && box.bottom <= innerHeight;
    })).toBe(true);
}

async function expectDay(page, iso) {
    const day = calendar(page).locator('[data-date="' + iso + '"]');
    await expect(day).toBeFocused();
    expect(await day.evaluate(node => {
        const style = getComputedStyle(node);
        return node.matches(':focus-visible') && parseFloat(style.outlineWidth) > 0 && style.outlineStyle !== 'none';
    }), 'The day reached with the keyboard has visible focus').toBe(true);
    await expect(calendar(page).locator('[data-date][tabindex="0"]')).toHaveCount(1);
}

for (const theme of ['light', 'dark']) {
    test('catalogue calendar keeps explicit activation, date arithmetic and native ISO commits (' + theme + ')', async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await openCatalogue(page, theme);
        const input = page.locator('#lab-entry-date');
        await expect(input).toHaveAttribute('type', 'date');
        await expect(input).toHaveAttribute('name', 'date');
        await input.fill('2024-02-28');
        await input.focus();
        await input.press('Tab');
        await page.keyboard.press('Shift+Tab');
        await expect(input).toBeFocused();
        await expect(calendar(page)).not.toBeVisible();
        for (const fraction of [.08, .5, .92]) {
            await input.scrollIntoViewIfNeeded();
            const box = await input.boundingBox();
            await page.mouse.click(box.x + box.width * fraction, box.y + box.height / 2);
            await expectFits(page);
            await page.keyboard.press('Escape');
            await expectReturnedFocus(page, input);
        }
        await page.evaluate(() => {
            window.__calendarEvents = [];
            const input = document.getElementById('lab-entry-date');
            for (const type of ['input', 'change']) input.addEventListener(type, event => {
                window.__calendarEvents.push({type: event.type, value: input.value});
            });
        });
        await input.press('Alt+ArrowDown');
        await expectDay(page, '2024-02-28');
        await expect(calendar(page).locator('[data-date="2024-02-28"]')).toHaveAttribute('aria-selected', 'true');
        await page.keyboard.press('ArrowRight');
        await expectDay(page, '2024-02-29');
        await expect(calendar(page).locator('[data-date="2024-02-29"]')).toHaveAttribute('aria-selected', 'false');
        await expect(input).toHaveValue('2024-02-28');
        await page.keyboard.press('Enter');
        await expectReturnedFocus(page, input);
        await expect(input).toHaveValue('2024-02-29');
        expect(await page.evaluate(() => window.__calendarEvents)).toEqual([
            {type: 'input', value: '2024-02-29'}, {type: 'change', value: '2024-02-29'},
        ]);
        await input.fill('2024-01-31');
        await input.press('Space');
        await page.keyboard.press('PageDown');
        await expectDay(page, '2024-02-29');
        await page.keyboard.press('Shift+PageDown');
        await expectDay(page, '2025-02-28');
        await page.keyboard.press('Shift+PageUp');
        await expectDay(page, '2024-02-28');
        await page.keyboard.press('ArrowUp');
        await expectDay(page, '2024-02-21');
        await page.keyboard.press('ArrowDown');
        await expectDay(page, '2024-02-28');
        await page.keyboard.press('ArrowLeft');
        await expectDay(page, '2024-02-27');
        await page.keyboard.press('Home');
        await expectDay(page, '2024-02-26');
        await page.keyboard.press('End');
        await expectDay(page, '2024-03-03');
        await page.keyboard.press('PageUp');
        await expectDay(page, '2024-02-03');
        await page.keyboard.press('Escape');
        await expect(input).toHaveValue('2024-01-31');
        await expectReturnedFocus(page, input);
        await input.press('Enter');
        await action(page, 'next').click();
        await expect(page.locator('#lab-calendar-month-label')).toContainText('February 2024');
        await expect(calendar(page).locator('[data-date="2024-02-29"][tabindex="0"]')).toHaveCount(1);
        await action(page, 'prev').click();
        await expect(page.locator('#lab-calendar-month-label')).toContainText('January 2024');
        await calendar(page).getByLabel('Month', {exact: true}).selectOption({label: 'February'});
        const year = calendar(page).getByLabel('Year', {exact: true});
        await year.fill('2025');
        await year.press('Tab');
        await expect(page.locator('#lab-calendar-month-label')).toContainText('February 2025');
        await expect(calendar(page).locator('[data-date="2025-02-28"][tabindex="0"]')).toHaveCount(1);
        for (const direction of ['Tab', 'Shift+Tab']) {
            for (let index = 0; index < 10; index++) {
                await page.keyboard.press(direction);
                expect(await calendar(page).evaluate(node => node.contains(document.activeElement)),
                    'Native modal keeps keyboard focus inside').toBe(true);
            }
        }
        await action(page, 'close').press('Enter');
        await expectReturnedFocus(page, input);
        await input.press('Enter');
        await page.mouse.click(4, 896);
        await expectReturnedFocus(page, input);
        await input.evaluate(node => { node.min = '2024-02-27'; node.max = '2024-03-02'; });
        await input.fill('2024-02-28');
        await input.press('Enter');
        await page.keyboard.press('ArrowLeft');
        await expectDay(page, '2024-02-27');
        await page.keyboard.press('ArrowLeft');
        await expectDay(page, '2024-02-27');
        await expect(action(page, 'today')).toBeDisabled();
        await expect(calendar(page).locator('[data-date="2024-02-26"]')).toBeDisabled();
        for (const key of ['ArrowUp', 'PageUp', 'PageDown', 'Shift+PageDown', 'Home', 'End']) {
            await page.keyboard.press(key);
            const focused = await calendar(page).evaluate(node => node.contains(document.activeElement)
                ? document.activeElement.dataset.date : null);
            expect(focused, 'Keyboard navigation stays on an allowed calendar day').not.toBeNull();
            expect(focused >= '2024-02-27' && focused <= '2024-03-02', 'The focused date respects min/max').toBe(true);
        }
        await page.keyboard.press('Escape');
        await expect(input).toHaveValue('2024-02-28');
        await input.evaluate(node => { node.removeAttribute('min'); node.removeAttribute('max'); });
        // Calendar navigation must keep a valid focus stop at either end of
        // its four-digit year range instead of opening an unselectable year.
        for (const [date, key, limit] of [['0001-01-01', 'ArrowLeft', 'prev'], ['9999-12-31', 'ArrowRight', 'next']]) {
            await input.fill(date);
            await input.press('Enter');
            await expectDay(page, date);
            await expect(action(page, limit)).toBeDisabled();
            await page.keyboard.press(key);
            await expectDay(page, date);
            await page.keyboard.press('Escape');
            await expect(input).toHaveValue(date);
        }
        await input.press('Enter');
        await action(page, 'today').click();
        await expect(input).toHaveValue('2026-10-17');
        await input.press('Enter');
        await action(page, 'clear').click();
        await expect(input).toHaveValue('');
        expect(await page.evaluate(() => window.__calendarEvents.slice(-4))).toEqual([
            {type: 'input', value: '2026-10-17'}, {type: 'change', value: '2026-10-17'},
            {type: 'input', value: ''}, {type: 'change', value: ''},
        ]);
        expect(await input.evaluate(node => node.validity.valueMissing)).toBe(true);
        await page.locator('#lab-entry-type-expense').press('Space');
        await page.locator('#lab-entry-title').fill('Calendar recovery');
        await page.locator('#lab-entry-amount').fill('12.50');
        await selectChoice(page.locator('#lab-entry-category'), '1001');
        await page.locator('#lab-entry-payment-account').press('Space');
        await selectChoice(page.locator('#lab-entry-account'), '2001');
        await page.locator('#lab-transaction-form').getByRole('button', {name: 'Preview entry', exact: true}).press('Enter');
        await expect(input).toBeFocused();
        await expect(input).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#lab-entry-date-error')).toBeVisible();
        await expect(calendar(page)).not.toBeVisible();
        await input.press('Enter');
        await expectFits(page);
        await expect(calendar(page).locator('[data-date][aria-selected="true"]')).toHaveCount(0);
        await calendar(page).screenshot({path: info.outputPath('calendar-keyboard-' + theme + '.png')});
    });
}

test('catalogue calendar opens from the whole field and fits mobile touch and reduced motion in both themes', async ({browser}, info) => {
    for (const theme of ['light', 'dark']) {
        const context = await browser.newContext({viewport: {width: 390, height: 700}, hasTouch: true, isMobile: true,
            timezoneId: 'America/Sao_Paulo', reducedMotion: theme === 'dark' ? 'reduce' : 'no-preference'});
        try {
            const page = await context.newPage();
            await openCatalogue(page, theme);
            const input = page.locator('#lab-entry-date');
            await input.fill('2024-02-28');
            for (const width of [390, 320]) {
                await page.setViewportSize({width, height: 700});
                for (const fraction of [.08, .5, .92]) {
                    await input.scrollIntoViewIfNeeded();
                    const box = await input.boundingBox();
                    await page.touchscreen.tap(box.x + box.width * fraction, box.y + box.height / 2);
                    await expectFits(page);
                    await action(page, 'close').tap();
                    await expectReturnedFocus(page, input);
                }
                await input.tap();
                await expectFits(page);
                if (theme === 'dark') {
                    expect(await calendar(page).evaluate(node => node.getAnimations({subtree: true})
                        .filter(animation => animation.playState === 'running').length)).toBe(0);
                }
                await calendar(page).locator('[data-date="2024-02-29"]').tap();
                await expect(input).toHaveValue('2024-02-29');
                await expectReturnedFocus(page, input);
                await input.tap();
                await page.screenshot({path: info.outputPath('calendar-touch-' + width + '-' + theme + '.png')});
                await page.keyboard.press('Escape');
            }
        } finally { await context.close(); }
    }
});

test('catalogue calendar respects the separate card form and closes with an inactive editor owner', async ({page}) => {
    await page.setViewportSize({width: 390, height: 800});
    await openCatalogue(page, 'dark');
    await page.locator('#lab-entry-type-expense').press('Space');
    await page.locator('#lab-entry-payment-credit').press('Space');
    await page.locator('#lab-card-editor > summary').press('Enter');
    await page.locator('#lab-card-editor details.lab-card-cycle > summary').press('Enter');
    const manual = page.locator('#lab-card-manual');
    await expect(manual).toHaveAttribute('type', 'date');
    await expect(manual).toHaveAttribute('name', 'manual_settlement_from');
    expect(await manual.evaluate(node => node.form.id)).toBe('lab-card-form');
    await page.evaluate(() => {
        window.__calendarSubmits = [];
        for (const id of ['lab-transaction-form', 'lab-card-form']) {
            document.getElementById(id).addEventListener('submit', () => window.__calendarSubmits.push(id));
        }
    });
    const writes = [];
    page.on('request', request => {
        if (request.method() !== 'GET' || ['xhr', 'fetch'].includes(request.resourceType())) writes.push(request.url());
    });
    await manual.fill('2024-05-15');
    await manual.press('Alt+ArrowDown');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Enter');
    await expect(manual).toHaveValue('2024-05-16');
    await expectReturnedFocus(page, manual);
    expect(await page.evaluate(() => window.__calendarSubmits)).toEqual([]);
    expect(writes).toEqual([]);
    await manual.press('Enter');
    await expect(calendar(page)).toBeVisible();
    // Simulate the existing form's conditional background update while the
    // modal owns focus; underlying controls are intentionally inert to users.
    await manual.evaluate(node => { node.disabled = true; });
    await expect(calendar(page)).not.toBeVisible();
    await manual.evaluate(node => { node.disabled = false; });
    await manual.press('Enter');
    await expect(calendar(page)).toBeVisible();
    await page.locator('#lab-card-editor').evaluate(node => { node.open = false; });
    await expect(calendar(page)).not.toBeVisible();
    await expect(manual).toHaveValue('2024-05-16');
    expect(await page.evaluate(() => window.__calendarSubmits)).toEqual([]);
});

test('catalogue date fields keep native ISO and a read-only GET without JavaScript', async ({browser}) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    try {
        const page = await context.newPage();
        await openCatalogue(page);
        await expect(calendar(page)).toHaveCount(0);
        const input = page.locator('#lab-entry-date');
        await expect(input).toHaveAttribute('type', 'date');
        await expect(input).toHaveAttribute('name', 'date');
        await page.locator('#lab-entry-type-expense').press('Space');
        await page.locator('#lab-entry-title').fill('Native calendar fallback');
        await page.locator('#lab-entry-amount').fill('12.50');
        await input.fill('2024-02-29');
        await page.locator('#lab-entry-category').selectOption('1001');
        await page.locator('#lab-entry-payment-account').press('Space');
        await page.locator('#lab-entry-account').selectOption('2001');
        const submitted = page.waitForRequest(request => request.isNavigationRequest()
            && new URL(request.url()).searchParams.get('title') === 'Native calendar fallback');
        await page.locator('#lab-transaction-form').getByRole('button', {name: 'Preview entry', exact: true}).press('Enter');
        expect((await submitted).method()).toBe('GET');
        await expect(page).toHaveURL(url => url.searchParams.get('date') === '2024-02-29'
            && url.searchParams.get('type') === 'EXPENSE' && url.hash === '#forms');
        await expect(calendar(page)).toHaveCount(0);
    } finally { await context.close(); }
});
