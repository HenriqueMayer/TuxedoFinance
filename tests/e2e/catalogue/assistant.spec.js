// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

async function scenario(panel, value) {
    const controls = panel.locator('.lab-assistant-demo-controls');
    if (await controls.getAttribute('open') === null) await controls.locator('summary').press('Enter');
    const select = controls.getByLabel('Synthetic response', {exact:true});
    await select.focus();
    await select.press('Home');
    for (let index = 0; index < ['answer', 'hold', 'error', 'disconnected'].indexOf(value); index++) {
        await select.press('ArrowDown');
    }
    await select.press('Tab');
    await expect(select).toHaveValue(value);
    await controls.locator('summary').press('Enter');
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    test(`synthetic assistant keeps context, recovery and keyboard ownership (${theme}, ${width})`, async ({page}, info) => {
        const external = [];
        const origin = new URL(info.project.use.baseURL).origin;
        page.on('request', request => {
            if (new URL(request.url()).origin !== origin) external.push(request.url());
        });
        await page.setViewportSize({width, height:900});
        await openCatalogue(page, {hash:'#assistant', theme, waitForFonts:true});
        const launcher = page.getByRole('button', {name:'Open Tuxedo assistant specimen', exact:true});
        const panel = page.locator('[data-lab-assistant-panel]');
        const originalScroll = await page.evaluate(() => scrollY);
        await launcher.focus();
        await launcher.press('Tab');
        await page.keyboard.press('Shift+Tab');
        await expect(launcher).toBeFocused();
        await expect(launcher).toHaveCSS('outline-style', 'solid');
        await launcher.press('Enter');
        await expect(panel).toBeVisible();
        await expect(panel).toHaveAttribute('aria-modal', String(width < 1280));
        await expect(panel.getByRole('button', {name:'Close assistant', exact:true})).toBeFocused();
        await expect(panel).toContainText('Synthetic preview · no provider');
        await expect(panel.locator('[data-lab-assistant-scope]')).toHaveText('Home · October 2026 · BRL');
        await expect.poll(() => panel.evaluate(node => node.getAnimations().length)).toBe(0);
        const box = await panel.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
        expect(box.y + box.height).toBeLessThanOrEqual(900);
        if (width >= 1280) {
            expect(box.width).toBe(376);
            expect(await page.locator('main').evaluate(node => node.inert)).toBe(false);
            expect((await page.locator('main').boundingBox()).x + (await page.locator('main').boundingBox()).width).toBeLessThan(box.x);
            await page.locator('[data-lab-navigation] [data-lab-destination="accounts"]').press('Enter');
            await expect(panel.locator('[data-lab-assistant-scope]')).toHaveText('Accounts · October 2026 · BRL');
            await panel.getByRole('button', {name:'Close assistant', exact:true}).focus();
        } else {
            await expect(page.locator('main')).toHaveAttribute('inert', '');
            await page.keyboard.press('Shift+Tab');
            await expect(panel.locator('[data-lab-assistant-delete] > summary')).toBeFocused();
            await page.keyboard.press('Tab');
            await expect(panel.getByRole('button', {name:'Close assistant', exact:true})).toBeFocused();
        }
        await page.screenshot({path:info.outputPath(`assistant-empty-${theme}-${width}.png`)});
        await page.keyboard.press('Escape');
        await expect(panel).toBeHidden();
        await expect(launcher).toBeFocused();
        expect(Math.abs(await page.evaluate(() => scrollY) - originalScroll)).toBeLessThan(2);
        await launcher.press('Enter');

        const question = panel.getByLabel('Your question about the example', {exact:true});
        const send = panel.getByRole('button', {name:'Preview reply ↗', exact:true});
        const notice = panel.locator('[data-lab-assistant-notice]');
        await scenario(panel, 'hold');
        await question.fill('Keep my synthetic question');
        await send.press('Enter');
        await expect(notice).toHaveText('Preparing a synthetic reply…');
        await expect(panel.locator('form')).toHaveAttribute('aria-busy', 'true');
        await panel.getByRole('button', {name:'Cancel preview', exact:true}).press('Enter');
        await expect(question).toHaveValue('Keep my synthetic question');
        await expect(panel.locator('form')).toHaveAttribute('aria-busy', 'false');
        await expect(notice).toContainText('Preview cancelled');

        await scenario(panel, 'error');
        await send.press('Enter');
        await expect(notice).toContainText('The example reply failed');
        await expect(question).toHaveValue('Keep my synthetic question');
        await scenario(panel, 'disconnected');
        await expect(question).toBeDisabled();
        await expect(send).toBeDisabled();
        await expect(notice).toContainText('Questions are not sent');
        await scenario(panel, 'answer');
        await question.fill('What can I safely set aside?');
        await question.press('Control+Enter');
        await expect(notice).toContainText('Synthetic reply ready');
        const answer = panel.locator('[data-lab-assistant-message="assistant"]');
        await expect(answer).toContainText('BRL 700.00 unreserved');
        await expect(answer).toContainText('BRL 800.00 projection');
        await page.screenshot({path:info.outputPath(`assistant-reply-${theme}-${width}.png`)});

        await panel.locator('[data-lab-assistant-history] > summary').press('Enter');
        await panel.getByRole('button', {name:'October cash review', exact:true}).press('Enter');
        await expect(answer).toContainText('Synthetic example:');
        await panel.getByRole('button', {name:'New conversation', exact:true}).press('Enter');
        await expect(answer).toHaveCount(0);
        await expect(panel).toContainText('Consult this workspace.');
        await question.fill('A conversation to delete');
        await send.press('Enter');
        await expect(notice).toContainText('Synthetic reply ready');
        await panel.locator('[data-lab-assistant-delete] > summary').press('Enter');
        await panel.getByRole('button', {name:'Delete conversation', exact:true}).press('Enter');
        await expect(notice).toHaveText('Synthetic conversation deleted.');
        await panel.locator('[data-lab-assistant-history] > summary').press('Enter');
        await expect(panel.getByRole('button', {name:'A conversation to delete', exact:true})).toHaveCount(0);
        await panel.locator('[data-lab-assistant-history] > summary').press('Enter');
        await answer.locator('.lab-assistant-sources > summary').press('Enter');
        await answer.getByRole('link', {name:'Recorded cash and reserves ↗', exact:true}).press('Enter');
        await expect(panel).toBeHidden();
        await expect(page).toHaveURL(/#lab-assistant-cash-source$/);
        await expect(page.locator('#lab-assistant-cash-source')).toBeInViewport();
        await expect(page.locator('main')).not.toHaveAttribute('inert');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(external).toEqual([]);
    });
}

test('assistant sheet fits touch, short viewports and reduced motion', async ({browser}, info) => {
    const context = await browser.newContext({hasTouch:true, reducedMotion:'reduce', viewport:{width:320, height:700}});
    try {
        const page = await context.newPage();
        await openCatalogue(page, {hash:'#assistant', theme:'dark'});
        await page.getByRole('button', {name:'Open Tuxedo assistant specimen', exact:true}).tap();
        const panel = page.locator('[data-lab-assistant-panel]');
        await expect(panel).toHaveCSS('animation-name', 'none');
        await page.setViewportSize({width:320, height:480});
        const input = panel.getByLabel('Your question about the example', {exact:true});
        await input.tap();
        const box = await input.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(320);
        expect(box.y + box.height).toBeLessThanOrEqual(480);
        await page.screenshot({path:info.outputPath('assistant-short-touch.png')});
        await panel.getByRole('button', {name:'Close assistant', exact:true}).tap();
        await expect(panel).toBeHidden();
        await expect(page.locator('main')).not.toHaveAttribute('inert');
    } finally {
        await context.close();
    }
});

test('assistant specimen has a meaningful native reading fallback', async ({browser}) => {
    const context = await browser.newContext({javaScriptEnabled:false, viewport:{width:390, height:844}});
    try {
        const page = await context.newPage();
        await openCatalogue(page, {hash:'#assistant'});
        await expect(page.locator('[data-lab-assistant-panel]')).toBeHidden();
        await expect(page.getByRole('button', {name:'Open Tuxedo assistant specimen', exact:true})).toBeHidden();
        await page.getByRole('link', {name:'Read the Tuxedo assistant specimen', exact:true}).press('Enter');
        const fallback = page.locator('#lab-assistant-native');
        await fallback.locator('summary').press('Enter');
        await expect(fallback).toContainText('BRL 700.00 unreserved');
        await expect(fallback).toContainText('Questions are not sent');
        await fallback.getByRole('link', {name:'Inspect recorded cash and reserves', exact:true}).press('Enter');
        await expect(page).toHaveURL(/#lab-assistant-cash-source$/);
        await expect(page.locator('#lab-assistant-cash-source')).toBeInViewport();
    } finally {
        await context.close();
    }
});
