// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, form) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    return page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...form},
        headers: {Referer: response.url()}, maxRedirects: 0});
}

async function seed(page, info) {
    const username = `position-icon-${info.workerIndex}-${Date.now()}`;
    const signed = await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    expect(signed.status()).toBe(302);
    const saved = await post(page, '/investments/add/', {new_institution: 'on', institution_name: 'Icon institution',
        name: 'Emergency application', valuation_mode: 'MONETARY', purpose: 'MONTHLY_CASH',
        currency: 'BRL', opening_balance: '100', opening_date: '2026-01-01', icon: 'reserve'});
    expect(saved.status(), await saved.text()).toBe(302);
    const target = saved.headers().location;
    const [, product, asset] = target.match(/positions\/(\d+)\/(\d+)\//);
    return {target, product, asset};
}

for (const width of [320, 1440]) for (const theme of ['light', 'dark']) {
    test(`position icon native keyboard, invalid recovery and filtered return (${width}, ${theme})`, async ({page}, info) => {
        test.setTimeout(60000);
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {product, asset} = await seed(page, info);
        const origin = '/investments/?scope=cash&q=Emergency';
        await page.goto(origin);
        await expect(page.locator('.investment-sections')).toHaveCSS('margin-bottom', '24px');
        const anchor = `position-${product}-${asset}${width < 640 ? '-mobile' : ''}`;
        const row = page.locator(`[id="${anchor}"]`);
        const icon = row.getByRole('link', {name: 'Customize icon for Emergency application', exact: true});
        await expect(icon).toContainText('🛟');
        const bounds = await icon.boundingBox();
        expect(bounds.width).toBeGreaterThanOrEqual(44);
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        await icon.press('Enter');
        await expect(page).toHaveURL(url => url.hash === '#position-personalization');
        const settings = page.locator('#position-personalization');
        const reserve = settings.locator('input[value="reserve"]');
        await expect(reserve).toBeChecked();
        await reserve.focus();
        await page.keyboard.press('ArrowRight');
        const home = settings.locator('input[value="home"]');
        await expect(home).toBeChecked();
        await expect(home).toBeFocused();
        await home.evaluate(input => { input.value = 'unsupported-icon'; });
        await settings.getByRole('button', {name: 'Save icon', exact: true}).press('Enter');
        await expect(settings.getByRole('alert')).toBeVisible();
        await expect(settings.locator('input[aria-invalid="true"]')).toHaveCount(12);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`appearance-invalid-${width}-${theme}.png`), fullPage: true});
        await settings.locator('input[value="home"]').press('Space');
        await settings.getByRole('button', {name: 'Save icon', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/investments/' && url.searchParams.get('scope') === 'cash'
            && url.searchParams.get('q') === 'Emergency' && url.hash === `#${anchor}`);
        await expect(icon).toContainText('🏠');
        await expect(row).toContainText(/BRL 100[,.]00/);
        await page.reload();
        await expect(icon).toContainText('🏠');
        await expect(page.locator('.investment-sections > a')).toHaveText(['My investments', 'History', 'Prices', 'Setup']);
        await page.screenshot({path: info.outputPath(`appearance-saved-${width}-${theme}.png`), fullPage: true});
    });
}

for (const theme of ['light', 'dark']) {
    test(`position icon persists in Portuguese without JavaScript (${theme})`, async ({browser}, info) => {
        const context = await browser.newContext({javaScriptEnabled: false, locale: 'pt-BR',
            viewport: {width: 390, height: 900}});
        try {
            const page = await context.newPage();
            const {target} = await seed(page, info);
            await page.goto(target);
            // Inspect both static palettes while the application's scripts remain disabled.
            await page.evaluate(value => document.documentElement.classList.toggle('dark', value === 'dark'), theme);
            // Native controls retain the same POST contract without enhancement.
            const settings = page.locator('#position-personalization');
            await settings.locator('input[value="piggy"]').press('Space');
            await settings.getByRole('button', {name: 'Salvar ícone', exact: true}).press('Enter');
            // Guided creation retains the list as its explicit return origin.
            // Verify the saved identity there, then reauthorize the details GET
            // and inspect its checked radio rather than expecting a stale form.
            await expect(page).toHaveURL(url => url.pathname === '/investments/');
            const icon = page.locator('.investment-position-row:visible .investment-icon-action');
            await expect(icon).toContainText('🐷');
            await page.reload();
            await expect(icon).toContainText('🐷');
            await expect(page.locator('.investment-sections > a')).toHaveText(['Minhas aplicações', 'Histórico', 'Preços', 'Cadastros']);
            await icon.press('Enter');
            await expect(settings.locator('input[value="piggy"]')).toBeChecked();
            await expect(page.locator('main > div > header h1')).toContainText('🐷');
            await page.evaluate(value => document.documentElement.classList.toggle('dark', value === 'dark'), theme);
            await page.screenshot({path: info.outputPath(`appearance-native-pt-${theme}.png`), fullPage: true});
        } finally { await context.close(); }
    });
}
