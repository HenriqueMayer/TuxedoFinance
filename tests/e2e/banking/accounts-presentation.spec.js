// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form:{csrfmiddlewaretoken:token,...values},maxRedirects:0});
    expect(saved.status()).toBe(302);
    return saved.headers().location;
}

for (const width of [320, 1440]) {
for (const theme of ['light', 'dark']) {
for (const language of ['en', 'pt-br']) {
test(`accounts hierarchy and native section rail (${width}, ${theme}, ${language})`, async ({page}, info) => {
    await page.setViewportSize({width,height:900});
    await page.addInitScript(value => localStorage.setItem('theme',value),theme);
    const username = `accounts-presentation-${info.workerIndex}-${Date.now()}`;
    await post(page,'/accounts/signup/',{username,email:`${username}@example.test`,password1:'Accounts-E2E-2026!',password2:'Accounts-E2E-2026!'});
    await post(page,'/banking/create/',{name:language === 'en' ? 'Everyday institution with a complete long name' : 'Mercado Pago',color:'#24594A'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page,'/banking/accounts/create/',{bank,name:'Everyday account with a complete long name',currency:'BRL',opening_balance:'1000.25',opening_date:'2020-01-01',reserved_amount:'100',planning_enabled:'on'});
    await page.goto('/banking/credit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    await post(page,'/banking/credit-cards/create/',{account,name:'Everyday credit',card_type:'PHYSICAL',closing_day:'24',due_day:'1',color:'#263843'});
    await post(page,'/banking/accounts/create/',{bank,name:'International account',currency:'USD',opening_balance:'0',opening_date:'2020-01-01',reserved_amount:'0',planning_enabled:'on'});
    await page.context().addCookies([{name:'django_language',value:language,url:info.project.use.baseURL}]);
    await page.goto('/banking/');
    const sections = page.getByRole('navigation',{name:language === 'en' ? 'Account sections':'Seções das contas'});
    await expect(sections.getByRole('link')).toHaveCount(4);
    const bankLink = page.locator(`[data-bank-open="${bank}"]`);
    const institution = bankLink.locator('.institution-miniature');
    await expect(institution).toHaveAttribute('aria-hidden','true');
    await expect(institution).toHaveAttribute('data-choice-kind','account');
    const art = await institution.boundingBox();
    expect(art.width).toBe(54);
    expect(art.height).toBe(36);
    const name = await bankLink.locator('span.font-semibold').boundingBox();
    expect(name.x).toBeGreaterThanOrEqual(art.x + art.width);
    expect(name.x + name.width).toBeLessThanOrEqual(width);
    await bankLink.screenshot({path:info.outputPath(`institution-identity-${width}-${theme}-${language}.png`)});
    await bankLink.press('Enter');
    const row = page.locator(`#account-row-${account}`);
    const windowbar = page.locator('.bank-workspace-windowbar');
    await expect(windowbar.locator('.institution-miniature')).toHaveCount(1);
    expect((await windowbar.locator('.institution-miniature').boundingBox()).width).toBe(width < 768 ? 44 : 54);
    await expect(windowbar.locator('.bank-marker')).toHaveCount(0);
    await expect(windowbar.locator('a')).toHaveCount(1);
    const other = page.locator('.bank-account-card').filter({hasText:'International account'});
    const firstBounds = await row.boundingBox();
    const otherBounds = await other.boundingBox();
    expect(otherBounds.y - firstBounds.y - firstBounds.height).toBeGreaterThanOrEqual(19);
    await expect(row).toHaveCSS('border-top-width','1px');
    await expect(other).toHaveCSS('border-top-width','1px');
    // Deliberate interactions inside the account never activate the titlebar.
    await row.locator('.account-configuration > summary').press('Space');
    await expect(row.locator('.account-configuration')).toHaveAttribute('open','');
    await expect(page.locator('#bank-workspace-panel')).toBeVisible();
    await row.locator('.account-configuration > summary').press('Space');
    await expect(row.locator('[data-account-balance]')).toContainText(/1[.,\s]000[,.]25/);
    await expect(row.locator('[data-account-reserved]')).toContainText(/100[,.]00/);
    await expect(row.locator('[data-account-available]')).toContainText(/900[,.]25/);
    await expect(row.locator('.card-miniature')).toHaveAttribute('style',/--card-start:#263843/);
    await expect(row.locator('.institution-miniature')).toHaveCount(0);
    for (const locator of [row.locator('.action-link'),row.locator('.compact-menu > summary').first(),row.locator('.planning-visibility')]) {
        const bounds = await locator.boundingBox();
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.width).toBeGreaterThanOrEqual(44);
    }
    await page.evaluate(() => window.scrollTo(0,0));
    await page.screenshot({path:info.outputPath(`accounts-${width}-${theme}-${language}.png`),fullPage:true});
    await page.screenshot({path:info.outputPath(`accounts-top-${width}-${theme}-${language}.png`)});
    const exchange = sections.getByRole('link').last();
    await exchange.focus();
    await expect(exchange).toBeFocused();
    const bounds = await exchange.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await exchange.press('Enter');
    await expect(page).toHaveURL(/\/banking\/exchange-rates\/$/);
    await expect(page.locator('.banking-sections a[aria-current="page"]')).toHaveCount(1);
    await page.goBack();
    await expect(row).toBeVisible();
    const minimize = page.locator('[data-bank-minimize]');
    await minimize.press('Enter');
    await expect(page.locator(`[data-bank-open="${bank}"]`)).toBeFocused();
    await page.locator(`[data-bank-open="${bank}"]`).press('Enter');
    // Actual pointer input tests the title and free bar space rather than
    // dispatching clicks, which would bypass the native stretched hit area.
    for (const target of [windowbar.locator('h2'),windowbar]) {
        await target.scrollIntoViewIfNeeded();
        const box = await target.boundingBox();
        const emptyBar = target === windowbar;
        await page.mouse.click(box.x + (emptyBar ? 4 : box.width / 2), box.y + (emptyBar ? 4 : box.height / 2));
        await expect(page.locator(`[data-bank-open="${bank}"]`)).toBeFocused();
        await page.locator(`[data-bank-open="${bank}"]`).press('Enter');
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
}
}
}
