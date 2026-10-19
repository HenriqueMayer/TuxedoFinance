// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');

async function pageGeometry(page) {
    return page.evaluate(() => ['main', '#lab-workspace-example', '#daily-flow .filter-panel', '#daily-flow input[type="search"]'].map(selector => {
        const {left, top, width, height} = document.querySelector(selector).getBoundingClientRect();
        return {selector, left:left + scrollX, top:top + scrollY, width, height};
    }));
}

async function expectSteadyLauncherMotion(launcher) {
    // Seek the real CSS effects instead of waiting through their slow cycles.
    const motion = await launcher.evaluate(button => {
        const box = () => {
            const {x, y, width, height} = button.getBoundingClientRect();
            return {x, y, width, height};
        };
        return ['img', 'svg'].map(selector => {
            const node = button.querySelector(selector), animation = node.getAnimations()[0];
            if (!animation) return null;
            const duration = animation.effect.getTiming().duration;
            animation.pause();
            const samples = [0, duration / 2].map(time => {
                animation.currentTime = time;
                const matrix = new DOMMatrix(getComputedStyle(node).transform);
                return {box:box(), y:matrix.m42, angle:Math.atan2(matrix.b, matrix.a) * 180 / Math.PI};
            });
            const properties = [...new Set(animation.effect.getKeyframes().flatMap(frame => Object.keys(frame)))];
            animation.play();
            return {duration, samples, properties, buttonAnimations:button.getAnimations().length};
        });
    });
    for (const [index, duration, angle] of [[0, 4000, 2], [1, 12000, 7]]) {
        expect(motion[index]).not.toBeNull();
        expect(motion[index].duration).toBe(duration);
        expect(motion[index].buttonAnimations).toBe(0);
        expect(motion[index].properties.filter(key => !['offset', 'computedOffset', 'easing', 'composite'].includes(key))).toEqual(['transform']);
        expect(motion[index].samples[0].box).toEqual(motion[index].samples[1].box);
        expect(motion[index].samples[0].angle).toBeCloseTo(-angle, 3);
        expect(motion[index].samples[1].angle).toBeCloseTo(angle, 3);
    }
    expect(motion[0].samples[0].y).toBeCloseTo(1.5, 3);
    expect(motion[0].samples[1].y).toBeCloseTo(-1.5, 3);
    expect(motion[0].samples[0].box.width).toBeGreaterThanOrEqual(44);
    expect(motion[0].samples[0].box.height).toBeGreaterThanOrEqual(44);
}

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
    test(`synthetic assistant preserves page geometry, compact context and keyboard ownership (${theme}, ${width})`, async ({page}, info) => {
        const external = [];
        const origin = new URL(info.project.use.baseURL).origin;
        page.on('request', request => {
            if (new URL(request.url()).origin !== origin) external.push(request.url());
        });
        await page.setViewportSize({width, height:900});
        await page.emulateMedia({reducedMotion:'no-preference'});
        await openCatalogue(page, {hash:'#assistant', theme, waitForFonts:true});
        const launcher = page.getByRole('button', {name:'Open Tuxedo assistant specimen', exact:true});
        const panel = page.locator('[data-lab-assistant-panel]');
        const geometry = await pageGeometry(page);
        const originalScroll = await page.evaluate(() => scrollY);
        await expectSteadyLauncherMotion(launcher);
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
        const compactContext = panel.getByLabel('Current page context', {exact:true});
        await expect(compactContext.getByRole('link')).toHaveCount(2);
        await expect(compactContext.getByRole('link', {name:'Cash and reserves ↗', exact:true})).toBeVisible();
        await expect(compactContext.getByRole('link', {name:'Known commitments ↗', exact:true})).toBeVisible();
        await expect(compactContext.locator('details, summary, dl')).toHaveCount(0);
        await expect(compactContext).not.toContainText('1,000.00');
        await expect(compactContext).not.toContainText('300.00');
        await expect(compactContext).not.toContainText('800.00');
        await expect(panel.getByText('Included context and sources', {exact:true})).toHaveCount(0);
        await expect.poll(() => panel.evaluate(node => node.getAnimations().length)).toBe(0);
        if (width >= 1280) expect(await pageGeometry(page)).toEqual(geometry);
        const box = await panel.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
        expect(box.y + box.height).toBeLessThanOrEqual(900);
        if (width >= 1280) {
            expect(box.width).toBe(376);
            expect(await page.locator('main').evaluate(node => node.inert)).toBe(false);
            const mainBox = await page.locator('main').boundingBox();
            expect(mainBox.x + mainBox.width).toBeGreaterThan(box.x);
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
        const geometryBeforeClose = width >= 1280 ? await pageGeometry(page) : null;
        await page.keyboard.press('Escape');
        await expect(panel).toBeHidden();
        await expect(launcher).toBeFocused();
        expect(Math.abs(await page.evaluate(() => scrollY) - originalScroll)).toBeLessThan(2);
        if (width >= 1280) expect(await pageGeometry(page)).toEqual(geometryBeforeClose);
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
        const launcher = page.getByRole('button', {name:'Open Tuxedo assistant specimen', exact:true});
        await expect(launcher.locator('img')).toHaveCSS('animation-name', 'none');
        await expect(launcher.locator('svg')).toHaveCSS('animation-name', 'none');
        await launcher.tap();
        const panel = page.locator('[data-lab-assistant-panel]');
        await expect(panel).toHaveCSS('animation-name', 'none');
        await expect(panel.locator('.lab-assistant-mark img')).toHaveCSS('animation-name', 'none');
        await expect(panel.locator('.lab-assistant-mark svg')).toHaveCSS('animation-name', 'none');
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
