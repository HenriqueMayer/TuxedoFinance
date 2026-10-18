// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

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
        const username = `shell-${info.workerIndex}-${Date.now()}`;
        const form = await page.request.get('/accounts/signup/');
        const token = (await form.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
        const saved = await page.request.post('/accounts/signup/', {
            form:{csrfmiddlewaretoken:token, username, email:`${username}@example.test`, password1:'Tuxedo-E2E-2026!', password2:'Tuxedo-E2E-2026!'},
            headers:{Referer:form.url()}, maxRedirects:0,
        });
        expect(saved.status()).toBe(302);
        await page.goto('/categories/');
        await checkFooter(1440, 'en');
        await page.screenshot({path:info.outputPath(`category-footer-${theme}.png`)});
        await page.context().addCookies([{name:'django_language', value:'pt-br', url:info.project.use.baseURL}]);
        await page.reload();
        await checkFooter(390, 'pt-br');
        await page.screenshot({path:info.outputPath(`category-footer-mobile-${theme}.png`)});
    });
}
