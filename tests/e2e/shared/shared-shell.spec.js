// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const username = `shell-${info.workerIndex}-${Date.now()}`;
    const form = await page.request.get('/accounts/signup/');
    const token = (await form.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post('/accounts/signup/', {
        form:{csrfmiddlewaretoken:token, username, email:`${username}@example.test`, password1:'Tuxedo-E2E-2026!', password2:'Tuxedo-E2E-2026!'},
        headers:{Referer:form.url()}, maxRedirects:0,
    });
    expect(saved.status()).toBe(302);
}

function brand(page, width) {
    return page.locator(width >= 1024 ? '.app-brand' : '.app-mobile-brand');
}

function workspaceHome(page, width) {
    return page.locator(`[data-app-navigation="${width >= 1024 ? 'desktop' : 'mobile'}"]`)
        .getByRole('link', {name:'Home', exact:true});
}

async function expectDashboard(page, width, owner) {
    await expect(page).toHaveURL(url => url.pathname === '/dashboard/');
    await expect(page.getByRole('heading', {name:'Dashboard', exact:true})).toBeVisible();
    await expect(page.locator('main')).toHaveAttribute('data-workspace-user', owner);
    await expect(workspaceHome(page, width)).toHaveAttribute('href', '/dashboard/');
    await expect(workspaceHome(page, width)).toHaveAttribute('aria-current', 'page');
    await expect(brand(page, width)).toHaveAttribute('href', '/dashboard/');
    await expect(page.locator('#landing-title')).toHaveCount(0);
}

async function expectLogoutCover(page) {
    const settings = await page.request.get('/accounts/settings/');
    const token = (await settings.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post('/accounts/logout/', {
        form:{csrfmiddlewaretoken:token}, headers:{Referer:settings.url()}, maxRedirects:0,
    });
    expect(response.status()).toBe(302);
    expect(response.headers().location).toBe('/');
    await page.goto('/');
    await expect(page.locator('#landing-title')).toBeVisible();
    const publicBrand = page.locator('.public-navbar').getByRole('link', {name:'Tuxedo Finance', exact:true});
    await expect(publicBrand).toHaveAttribute('href', '/');
    await publicBrand.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === '/');
    await expect(page.locator('.app-brand, .app-mobile-brand')).toHaveCount(0);
    await expect(page.locator('.public-navbar').getByRole('link', {name:'Log in', exact:true})).toBeVisible();
}

for (const theme of ['light', 'dark']) {
    test(`shared footer stays quiet on public and workspace pages (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.goto('/');
        async function checkFooter(width, language) {
            await page.setViewportSize({width, height:844});
            const footer = page.locator('footer.site-footer');
            await expect(footer).toHaveCount(1);
            await expect(footer.locator('img')).toHaveCount(0);
            await expect(footer).toContainText(language === 'pt-br' ? 'Todos os direitos reservados.' : 'All rights reserved.');
            await expect(footer).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
            await footer.scrollIntoViewIfNeeded();
            const box = await footer.boundingBox();
            expect(box.height).toBeLessThan(width < 640 ? 100 : 75);
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.x + box.width).toBeLessThanOrEqual(width);
            const author = footer.getByRole('link', {name:'HenriqueMayer', exact:true});
            await author.focus();
            await expect(author).toBeFocused();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        await checkFooter(1440, 'en');
        await signup(page, info);
        await page.goto('/categories/');
        await checkFooter(1440, 'en');
        await page.screenshot({path:info.outputPath(`category-footer-${theme}.png`)});
        await page.context().addCookies([{name:'django_language', value:'pt-br', url:info.project.use.baseURL}]);
        await page.reload();
        await checkFooter(390, 'pt-br');
        await page.screenshot({path:info.outputPath(`category-footer-mobile-${theme}.png`)});
    });
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    test(`workspace brand opens the dashboard and preserves Home, logout and departure recovery (${theme}, ${width})`, async ({page}, info) => {
        await signup(page, info);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height:844});
        await page.goto('/categories/');
        const owner = await page.locator('main').getAttribute('data-workspace-user');
        const link = brand(page, width);
        await expect(link).toBeVisible();
        await expect(link).toHaveAttribute('href', '/dashboard/');
        await link.focus();
        await page.keyboard.press('Tab');
        await expect(link).not.toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(link).toBeFocused();
        await expect(link).toHaveCSS('outline-style', 'solid');
        await expect(link).toHaveCSS('outline-width', '2px');
        await page.screenshot({path:info.outputPath(`brand-focus-${theme}-${width}.png`)});
        await page.keyboard.press('Enter');
        await expectDashboard(page, width, owner);
        await page.screenshot({path:info.outputPath(`brand-dashboard-${theme}-${width}.png`)});
        await workspaceHome(page, width).press('Enter');
        await expectDashboard(page, width, owner);
        await page.goto('/categories/');
        await brand(page, width).click();
        await expectDashboard(page, width, owner);
        await page.goto('/');
        await expectDashboard(page, width, owner);

        await page.goto('/transactions/create/');
        await page.locator('#id_title').fill('Keep this draft when leaving through the brand');
        await brand(page, width).press('Enter');
        const dialog = page.getByRole('dialog', {name:'Leave this page?', exact:true});
        await expect(dialog).toBeVisible();
        const stay = dialog.getByRole('button', {name:'Keep editing', exact:true});
        await expect(stay).toBeFocused();
        await stay.press('Enter');
        await expect(dialog).toBeHidden();
        await expect(page).toHaveURL(url => url.pathname === '/transactions/create/');
        await expect(page.locator('#id_title')).toHaveValue('Keep this draft when leaving through the brand');
        await expect(brand(page, width)).toBeFocused();
        await brand(page, width).press('Enter');
        await dialog.getByRole('button', {name:'Leave page', exact:true}).press('Enter');
        await expectDashboard(page, width, owner);
        await expectLogoutCover(page);
    });
}

test('workspace brand and Home retain native navigation without JavaScript', async ({browser}, info) => {
    for (const width of [1440, 390]) {
        const context = await browser.newContext({baseURL:info.project.use.baseURL, javaScriptEnabled:false,
            hasTouch:width < 1024, viewport:{width, height:844}});
        try {
            const page = await context.newPage();
            await signup(page, info);
            await page.goto('/categories/');
            const owner = await page.locator('main').getAttribute('data-workspace-user');
            await expect(brand(page, width)).toHaveAttribute('href', '/dashboard/');
            await brand(page, width).press('Enter');
            await expectDashboard(page, width, owner);
            await workspaceHome(page, width).press('Enter');
            await expectDashboard(page, width, owner);
            await page.goto('/categories/');
            if (width < 1024) await brand(page, width).tap();
            else await brand(page, width).click();
            await expectDashboard(page, width, owner);
            await page.goto('/');
            await expectDashboard(page, width, owner);
            await expectLogoutCover(page);
        } finally {
            await context.close();
        }
    }
});
