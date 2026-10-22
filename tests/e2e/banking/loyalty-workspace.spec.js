// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, fields) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), (await saved.text()).match(/role="alert"[^>]*>[^<]+/g)?.join(' ')).toBe(302);
}

async function fixture(page, info) {
    const username = `loyalty-workspace-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Loyalty-E2E-2026!', password2: 'Loyalty-E2E-2026!'});
    await post(page, '/banking/create/', {name: 'Cedar reward bank', color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Everyday account', currency: 'BRL', opening_balance: '500', opening_date: '2020-01-01'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    const cardName = 'Travel ' + 'C'.repeat(70);
    await post(page, '/banking/credit-cards/create/', {account, name: cardName, color: '#65418C',
        card_type: 'PHYSICAL', closing_day: '20', due_day: '28'});
    await page.goto('/banking/loyalty/create/');
    const card = await page.locator('#id_cards option').last().getAttribute('value');
    await post(page, '/banking/loyalty/create/', {bank, cards: card, name: 'Travel points ' + 'P'.repeat(65), unit_name: 'Miles'});
    await post(page, '/banking/loyalty/create/', {name: 'Independent club', unit_name: 'Points'});
    await page.goto('/banking/loyalty-entries/create/');
    const program = await page.locator('#id_program option').filter({hasText: /^Travel points/}).getAttribute('value');
    const today = new Date().toISOString().slice(0, 10);
    for (let index = 0; index < 11; index++) {
        await post(page, '/banking/loyalty-entries/create/', {program, kind: 'ADJUSTMENT', direction: 'CREDIT',
            amount: '10.25', date: today, notes: `Local points entry ${index}`});
    }
    return {program, cardName};
}

for (const theme of ['light', 'dark']) {
    for (const width of [320, 1280]) {
        test(`loyalty overview and complete history preserve keyboard and origin (${theme}, ${width})`, async ({page}, info) => {
            test.setTimeout(90000);
            await page.setViewportSize({width, height: 900});
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            const data = await fixture(page, info);
            const language = theme === 'light' ? 'en' : 'pt-br';
            await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
            await page.goto('/banking/loyalty/');
            await expect(page.locator('html')).toHaveAttribute('lang', language);
            await expect(page.locator('.loyalty-program')).toHaveCount(2);
            const program = page.locator(`#loyalty-program-${data.program}`);
            await expect(program.locator('.loyalty-program-balance')).toContainText(/112[,.]75/);
            await expect(program.locator('.card-miniature')).toHaveCount(1);
            const menu = program.locator('details.compact-menu');
            await menu.locator(':scope > summary').press('Enter');
            const panel = menu.locator('.secondary-actions-panel');
            await expect(panel.getByRole('link',{name:language === 'en' ? 'Edit' : 'Editar',exact:true})).toBeVisible();
            await expect(panel.getByRole('link',{name:language === 'en' ? 'Delete' : 'Excluir',exact:true})).toBeVisible();
            const menuBounds = await panel.boundingBox();
            expect(menuBounds.x).toBeGreaterThanOrEqual(0);
            expect(menuBounds.x + menuBounds.width).toBeLessThanOrEqual(width);
            await menu.locator(':scope > summary').press('Escape');
            await expect(menu).not.toHaveAttribute('open','');
            await expect(program.locator('.loyalty-program-cards')).toContainText(data.cardName);
            await page.locator('#loyalty-filter-q').pressSequentially('Cedar', {delay: 35});
            await expect(page.locator('.loyalty-program')).toHaveCount(1);
            await expect(page.locator('#loyalty-filter-q')).toBeFocused();
            await expect(page).toHaveURL(/q=Cedar/);
            const origin = '/banking/loyalty/?q=Cedar';
            const recent = program.locator('.loyalty-history');
            await expect(recent).not.toHaveAttribute('open', '');
            await recent.locator('summary').press('Space');
            await expect(recent.locator('li[id^="loyalty-entry-"]')).toHaveCount(10);
            for (const control of [recent.locator('summary'), program.locator('a[href*="loyalty-entries/create"]').first()]) {
                const box = await control.boundingBox();
                expect(box.height).toBeGreaterThanOrEqual(44);
            }
            await page.evaluate(() => window.scrollTo(0,0));
            await page.screenshot({path: info.outputPath(`loyalty-${theme}-${width}.png`), fullPage: true});
            await page.screenshot({path: info.outputPath(`loyalty-top-${theme}-${width}.png`)});
            await recent.locator('a[href*="loyalty-entries/"][href*="/edit/"]').first().press('Enter');
            await expect(page.locator('#id_amount')).toHaveValue(/10[,.]25/);
            await page.locator('#id_amount').fill('-1');
            await page.getByRole('button', {name: language === 'en' ? 'Save' : 'Salvar', exact: true}).press('Enter');
            await expect(page.locator('#id_amount-error-1')).toBeVisible();
            const cancel = page.getByRole('link', {name: language === 'en' ? 'Cancel' : 'Cancelar', exact: true});
            await expect(cancel).toHaveAttribute('href', origin);
            await cancel.press('Enter');
            await expect(page).toHaveURL(url => url.pathname + url.search === origin);
            if (await recent.getAttribute('open') === null) await recent.locator('summary').press('Space');
            await recent.locator(`a[href="/banking/loyalty/${data.program}/entries/"]`).press('Enter');
            await expect(page.locator('#loyalty-results li[id^="loyalty-entry-"]')).toHaveCount(11);
            await page.locator('#loyalty-filter-q').fill('Local points entry 10');
            await expect(page.locator('#loyalty-results li[id^="loyalty-entry-"]')).toHaveCount(1);
            await page.locator('#loyalty-clear-control a').press('Enter');
            await expect(page.locator('#loyalty-results li[id^="loyalty-entry-"]')).toHaveCount(11);
            await page.goBack();
            await expect(page.locator('#loyalty-filter-q')).toHaveValue('Local points entry 10');
            await expect(page.locator('#loyalty-results li[id^="loyalty-entry-"]')).toHaveCount(1);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        });
    }
}

test('loyalty search, disclosures and editor cancellation remain native without JavaScript', async ({page, browser}, info) => {
    test.setTimeout(90000);
    const data = await fixture(page, info);
    const context = await browser.newContext({javaScriptEnabled: false, storageState: await page.context().storageState(), viewport: {width: 320, height: 844}});
    try {
        const native = await context.newPage();
        await native.goto('/banking/loyalty/');
        await native.locator('#loyalty-filter-q').fill('Cedar');
        await native.locator('#loyalty-filter-form button[type="submit"]').press('Enter');
        await expect(native.locator('.loyalty-program')).toHaveCount(1);
        const menu = native.locator(`#loyalty-program-${data.program} details.compact-menu`);
        await menu.locator(':scope > summary').press('Enter');
        const menuBounds = await menu.locator('.secondary-actions-panel').boundingBox();
        expect(menuBounds.x).toBeGreaterThanOrEqual(0);
        expect(menuBounds.x + menuBounds.width).toBeLessThanOrEqual(320);
        await menu.locator(':scope > summary').press('Enter');
        const recent = native.locator(`#loyalty-recent-${data.program}`);
        await recent.locator('summary').press('Enter');
        await expect(recent.locator('li[id^="loyalty-entry-"]')).toHaveCount(10);
        await recent.locator(`a[href="/banking/loyalty/${data.program}/entries/"]`).press('Enter');
        await expect(native.locator('#loyalty-results li[id^="loyalty-entry-"]')).toHaveCount(11);
        const origin = `/banking/loyalty/${data.program}/entries/`;
        await native.locator('#loyalty-results a[href*="loyalty-entries/"][href*="/edit/"]').first().press('Enter');
        await expect(native.getByRole('link', {name: 'Cancel', exact: true})).toHaveAttribute('href', origin);
        await native.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(native).toHaveURL(url => url.pathname === origin);
        expect(await native.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally { await context.close(); }
});
