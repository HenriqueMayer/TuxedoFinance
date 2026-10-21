// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, fields) {
    const source = await page.request.get(path);
    const csrf = (await source.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: source.url()}, maxRedirects: 0,
    });
    const html = await response.text();
    const errors = [...html.matchAll(/id="[^"]+-error-\d"[^>]*>(.*?)<\/p>/gs)]
        .map(match => match[1].replace(/<[^>]+>/g, ''));
    expect(response.status(), `${path}: ${errors.join('; ')}`).toBe(302);
}

async function fixture(page, info) {
    const username = `card-dial-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-Dial-2026!', password2: 'Tuxedo-Dial-2026!'});
    await post(page, '/banking/create/', {name: 'Studio bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Everyday account', currency: 'BRL',
        opening_balance: '0', opening_date: '2020-01-01'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    return {account};
}

async function fillCard(page, kind, account, name) {
    await page.goto(`/banking/${kind}-cards/create/`);
    await selectChoice(page.locator('#id_account'), account);
    await page.locator('#id_name').fill(name);
    if (kind === 'credit') {
        await page.locator('#id_card_type').selectOption('PHYSICAL');
        await page.locator('#id_closing_day').fill('20');
        await page.locator('#id_due_day').fill('28');
    }
    // The native custom input works with and without progressive preset buttons.
    await page.locator('#id_color').fill('#820ad1');
}

async function recordId(page, kind, name) {
    await page.goto('/transactions/create/');
    return page.locator(`#id_${kind}_card option`).filter({hasText: new RegExp(`^${name} -`)})
        .getAttribute('value');
}

function dial(page) { return page.locator('[data-card-angle-dial]'); }
function preview(page) { return page.locator('[data-card-appearance-preview]'); }

async function angle(page, value) {
    await expect(dial(page)).toHaveAttribute('aria-valuenow', String(value));
    await expect(dial(page)).toHaveAttribute('aria-valuetext', `${value}°`);
    await expect(page.locator('#id_gradient_angle')).toHaveValue(String(value));
    await expect(preview(page)).toHaveCSS('--card-angle', `${value}deg`);
}

async function point(page, degrees) {
    const box = await dial(page).boundingBox();
    expect(box).not.toBeNull();
    const radius = Math.min(box.width, box.height) * .36;
    const radians = degrees * Math.PI / 180;
    return {x: box.x + box.width / 2 + Math.sin(radians) * radius,
        y: box.y + box.height / 2 - Math.cos(radians) * radius};
}

for (const theme of ['light', 'dark']) {
    test(`card gradient crank preserves keyboard focus, native POST and error recovery (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1280, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account} = await fixture(page, info);
        const name = 'Studio credit';
        await fillCard(page, 'credit', account, name);
        const toggle = page.locator('#id_use_gradient');
        const group = page.locator('[data-card-gradient-fields]');
        const native = page.locator('#id_gradient_angle');
        await expect(toggle).not.toBeChecked();
        await expect(group).toBeHidden();
        await expect(native).toBeDisabled();
        await toggle.focus();
        await page.keyboard.press('Space');
        await expect(group).toBeVisible();
        await expect(toggle).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(page.locator('#id_gradient_end')).toBeFocused();
        await page.locator('#id_gradient_end').fill('#c6a173');
        await page.keyboard.press('Tab');
        await expect(dial(page)).toBeFocused();
        await expect(dial(page)).toHaveRole('slider');
        await expect(dial(page)).toHaveAccessibleName('Gradient angle');
        await expect(dial(page)).toHaveAttribute('aria-valuemin', '0');
        await expect(dial(page)).toHaveAttribute('aria-valuemax', '359');
        await expect(native).toBeHidden();
        expect(await dial(page).evaluate(element => {
            const style = getComputedStyle(element);
            return element.matches(':focus-visible') && parseFloat(style.outlineWidth) > 0
                && style.outlineStyle !== 'none';
        })).toBe(true);
        await angle(page, 135);
        await page.keyboard.press('Home');
        await angle(page, 0);
        await page.keyboard.press('ArrowLeft');
        await angle(page, 0);
        await page.keyboard.press('End');
        await page.keyboard.press('ArrowRight');
        await angle(page, 359);
        await page.keyboard.press('Home');
        await page.keyboard.press('Shift+ArrowUp');
        await angle(page, 15);
        await page.keyboard.press('PageUp');
        await angle(page, 30);
        await page.keyboard.press('PageDown');
        await angle(page, 15);
        await page.keyboard.press('End');
        await angle(page, 359);
        await page.keyboard.press('Home');
        await page.keyboard.press('Shift+ArrowRight');
        await page.keyboard.press('Shift+ArrowRight');
        await page.keyboard.press('Shift+ArrowRight');
        await angle(page, 45);
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/credit-cards\/create\/$/);
        await expect(dial(page)).toBeFocused();
        // Repeated HTMX initialization must not multiply keyboard listeners.
        await page.evaluate(() => {
            window.TuxedoCardAppearance.initialize();
            window.TuxedoCardAppearance.initialize();
            document.dispatchEvent(new CustomEvent('htmx:afterSwap', {
                detail: {target: document.querySelector('[data-card-appearance-form]'),
                    elt: document.querySelector('[data-card-appearance-form]')},
            }));
        });
        await page.keyboard.press('ArrowRight');
        await angle(page, 46);
        await page.keyboard.press('ArrowLeft');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(/\/credit-cards\/create\/$/);
        const card = await recordId(page, 'credit', name);
        const editor = `/banking/credit-cards/${card}/edit/`;
        await page.goto(editor);
        await expect(toggle).toBeChecked();
        await angle(page, 45);
        await expect(page.locator('#id_account')).toHaveValue(account);
        await expect(page.locator('#id_closing_day')).toHaveValue('20');
        await expect(page.locator('#id_due_day')).toHaveValue('28');
        await dial(page).press('ArrowRight');
        await angle(page, 46);
        // Turning a crank is a local preview, not an implicit financial write.
        const original = await page.request.get(editor);
        expect(await original.text()).toMatch(/name="gradient_angle"[^>]*value="45"/);
        // A forged retained native value deliberately exercises server errors;
        // the accessible crank itself can only produce valid angles.
        await native.evaluate(input => { input.value = '400'; });
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(native).toBeVisible();
        await expect(native).toHaveValue('400');
        await expect(native).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_gradient_angle-error-1')).toBeVisible();
        await expect(page.locator('#id_gradient_end')).toHaveValue('#c6a173');
        await expect(page.locator('#id_name')).toHaveValue(name);
        await native.fill('90');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(url => url.pathname === editor);
        await page.goto(editor);
        await angle(page, 90);
        await toggle.press('Space');
        await expect(group).toBeHidden();
        await expect(native).toBeDisabled();
        await expect(toggle).toBeFocused();
        await toggle.press('Tab');
        await expect(page.getByRole('button', {name: 'Save', exact: true})).toBeFocused();
        await toggle.press('Space');
        await expect(group).toBeVisible();
        await angle(page, 135);
        await page.locator('#id_gradient_end').fill('#c6a173');
        // A private draft can restore a temporarily invalid numeric value. Keep
        // that value editable instead of replacing it with a valid default.
        await native.evaluate(input => {
            input.value = '400';
            input.form.dispatchEvent(new Event('tuxedo:restore'));
        });
        await expect(native).toBeVisible();
        await expect(native).toHaveValue('400');
        await expect(dial(page)).toBeHidden();
        await native.fill('90');
        await expect(native).toBeFocused();
        await expect(native).toBeVisible();
        await native.press('Tab');
        await expect(dial(page)).toBeVisible();
        await angle(page, 90);
        await page.locator('.card-appearance').screenshot({path: info.outputPath(`card-angle-dial-${theme}.png`)});
    });

    test(`debit card crank follows mouse quadrants and wraps across north (${theme})`, async ({page}, info) => {
        await page.setViewportSize({width: 1280, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {account} = await fixture(page, info);
        const name = 'Studio debit';
        await fillCard(page, 'debit', account, name);
        await page.locator('#id_use_gradient').check();
        await page.locator('#id_gradient_end').fill('#c6a173');
        await dial(page).scrollIntoViewIfNeeded();
        const first = await point(page, 90);
        await page.mouse.move(first.x, first.y);
        await page.mouse.down();
        for (const target of [90, 180, 270, 359, 1, 90]) {
            const position = await point(page, target);
            await page.mouse.move(position.x, position.y, {steps: 4});
            const actual = Number(await dial(page).getAttribute('aria-valuenow'));
            const distance = Math.min(Math.abs(actual - target), 360 - Math.abs(actual - target));
            expect(distance, `Pointer direction ${target}° follows the crank`).toBeLessThanOrEqual(2);
        }
        await page.mouse.up();
        const stopped = await dial(page).getAttribute('aria-valuenow');
        const away = await point(page, 270);
        await page.mouse.move(away.x, away.y);
        await expect(dial(page)).toHaveAttribute('aria-valuenow', stopped);
        await page.getByRole('button', {name: 'Save', exact: true}).click();
        await expect(page).not.toHaveURL(/\/debit-cards\/create\/$/);
        const card = await recordId(page, 'debit', name);
        await page.goto(`/banking/debit-cards/${card}/edit/`);
        await angle(page, Number(stopped));
        await expect(page.locator('#id_color')).toHaveValue('#820ad1');
        await expect(page.locator('#id_gradient_end')).toHaveValue('#c6a173');
    });
}

for (const width of [320, 390]) {
    test(`card crank accepts touch drag and fits mobile ${width}`, async ({browser}, info) => {
        const context = await browser.newContext({baseURL: process.env.E2E_BASE_URL,
            viewport: {width, height: 844}, hasTouch: true});
        const page = await context.newPage();
        try {
            await page.addInitScript(value => localStorage.setItem('theme', value), width === 390 ? 'dark' : 'light');
            const {account} = await fixture(page, info);
            await fillCard(page, 'debit', account, 'Touch card');
            await page.locator('#id_use_gradient').check();
            await dial(page).scrollIntoViewIfNeeded();
            const cdp = await context.newCDPSession(page);
            const start = await point(page, 45);
            await cdp.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{...start, id: 0}]});
            for (const degrees of [60, 90, 120, 150, 180]) {
                const position = await point(page, degrees);
                await cdp.send('Input.dispatchTouchEvent', {type: 'touchMove', touchPoints: [{...position, id: 0}]});
            }
            await cdp.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
            const actual = Number(await dial(page).getAttribute('aria-valuenow'));
            expect(Math.abs(actual - 180)).toBeLessThanOrEqual(2);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            expect(await dial(page).evaluate(element => {
                const box = element.getBoundingClientRect();
                return box.width >= 44 && box.height >= 44 && box.left >= 0 && box.right <= innerWidth;
            })).toBe(true);
            const before = await dial(page).getAttribute('aria-valuenow');
            await page.touchscreen.tap(8, 8);
            await expect(dial(page)).toHaveAttribute('aria-valuenow', before);
        } finally {
            await context.close();
        }
    });
}

test.describe('card gradient native fallback', () => {
    test.use({javaScriptEnabled: false});
    for (const kind of ['credit', 'debit']) {
        test(`native ${kind} angle input creates and edits a gradient without JavaScript`, async ({page}, info) => {
            const {account} = await fixture(page, info);
            const name = `Native ${kind}`;
            await fillCard(page, kind, account, name);
            const native = page.locator('#id_gradient_angle');
            await expect(dial(page)).toHaveCount(0);
            await expect(native).toBeVisible();
            await expect(native).toBeEnabled();
            await expect(native).toHaveAttribute('type', 'number');
            await page.locator('#id_use_gradient').check();
            await page.locator('#id_gradient_end').fill('#c6a173');
            await native.fill('400');
            await page.getByRole('button', {name: 'Save', exact: true}).click();
            await expect(page.locator('#id_gradient_angle-error-1')).toBeVisible();
            await expect(native).toHaveValue('400');
            await expect(page.locator('#id_name')).toHaveValue(name);
            await expect(page.locator('#id_account')).toHaveValue(account);
            await native.fill('270');
            await page.getByRole('button', {name: 'Save', exact: true}).click();
            await expect(page).not.toHaveURL(new RegExp(`/${kind}-cards/create/$`));
            const card = await recordId(page, kind, name);
            const editor = `/banking/${kind}-cards/${card}/edit/`;
            await page.goto(editor);
            await expect(native).toHaveValue('270');
            await expect(page.locator('#id_use_gradient')).toBeChecked();
            await expect(page.locator('#id_gradient_end')).toHaveValue('#c6a173');
            await native.fill('0');
            await page.getByRole('button', {name: 'Save', exact: true}).click();
            await expect(page).not.toHaveURL(url => url.pathname === editor);
            await page.goto(editor);
            await expect(native).toHaveValue('0');
            await expect(page.locator('#id_account')).toHaveValue(account);
        });
    }
});
