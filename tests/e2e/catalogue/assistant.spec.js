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

async function selectModel(panel, value = 'synthetic') {
    const settings = panel.locator('[data-lab-assistant-settings]');
    if (!await settings.evaluate(node => node.open)) await settings.locator(':scope > summary').press('Enter');
    await settings.getByLabel('Preview model', {exact: true}).selectOption(value);
    await settings.locator(':scope > summary').press('Escape');
    await expect(settings).not.toHaveAttribute('open');
}

async function expectSquareSettingsGear(panel) {
    const summary = panel.locator('[data-lab-assistant-settings] > summary');
    const target = await summary.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(44);
    expect(target.height).toBeGreaterThanOrEqual(44);
    const gear = await summary.locator('svg').evaluate(svg => {
        const frame = svg.getBoundingClientRect(), circle = svg.querySelector('circle, path:last-child').getBoundingClientRect();
        return {width: frame.width, height: frame.height, shrink: getComputedStyle(svg).flexShrink,
            centerX: frame.x + frame.width / 2, centerY: frame.y + frame.height / 2,
            circleX: circle.x + circle.width / 2, circleY: circle.y + circle.height / 2};
    });
    expect(gear.width).toBeCloseTo(16, 1);
    expect(gear.height).toBeCloseTo(16, 1);
    expect(gear.shrink).toBe('0');
    expect(gear.circleX).toBeCloseTo(gear.centerX, 1);
    expect(gear.circleY).toBeCloseTo(gear.centerY, 1);
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
        await expect(panel.getByRole('button', {name:'Minimize assistant', exact:true})).toBeFocused();
        await expect(panel).toContainText('Synthetic preview · no provider');
        await expect(panel.locator('[data-lab-assistant-scope]')).toHaveText('Home · October 2026 · BRL');
        const compactContext = panel.getByLabel('Current page context', {exact:true});
        await expect(compactContext.getByRole('link')).toHaveCount(1);
        await expect(compactContext.getByRole('link', {name:'Home · October 2026 · BRL', exact:true})).toHaveAttribute('href', '#lab-view-home');
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
            expect(box.width).toBe(420);
            expect(await page.locator('main').evaluate(node => node.inert)).toBe(false);
            const mainBox = await page.locator('main').boundingBox();
            expect(mainBox.x + mainBox.width).toBeGreaterThan(box.x);
            await page.locator('[data-lab-navigation] [data-lab-destination="accounts"]').press('Enter');
            await expect(panel.locator('[data-lab-assistant-scope]')).toHaveText('Accounts · October 2026 · BRL');
            await panel.getByRole('button', {name:'Close assistant', exact:true}).focus();
        } else {
            await expect(page.locator('main')).toHaveAttribute('inert', '');
            await page.keyboard.press('Shift+Tab');
            await expect(panel.getByRole('checkbox', {name:'Use page data', exact:true})).toBeFocused();
            await page.keyboard.press('Tab');
            await expect(panel.getByRole('button', {name:'Minimize assistant', exact:true})).toBeFocused();
        }
        // Compact paint must retain touch-sized targets in both desktop and sheet layouts.
        for (const control of [
            panel.getByRole('button', {name:'Minimize assistant', exact:true}),
            panel.getByRole('button', {name:'Close assistant', exact:true}),
            panel.getByRole('button', {name:'New conversation', exact:true}),
            compactContext.getByRole('link'),
            panel.getByLabel('Your question about the example', {exact:true}),
            panel.locator('[data-lab-assistant-settings] > summary'),
            panel.locator('.lab-assistant-context-choice'),
            panel.getByRole('button', {name:'Preview reply', exact:true}),
        ]) {
            const target = await control.boundingBox();
            expect(target.width).toBeGreaterThanOrEqual(44);
            expect(target.height).toBeGreaterThanOrEqual(44);
        }
        const empty = panel.locator('.lab-assistant-empty');
        const emptyBox = await empty.boundingBox(), artworkBox = await empty.locator('svg').boundingBox();
        expect(Math.abs(artworkBox.x + artworkBox.width / 2 - emptyBox.x - emptyBox.width / 2)).toBeLessThan(1);
        await expect(empty).toHaveCSS('text-align', 'center');
        // The working chat and its specimen share one compact utility rail;
        // context must not consume a second row above the conversation.
        const chrome = await panel.evaluate(node => {
            const header = node.querySelector('.lab-assistant-header').getBoundingClientRect();
            const toolbar = node.querySelector('.lab-assistant-toolbar').getBoundingClientRect();
            const context = node.querySelector('[data-lab-assistant-scope]').getBoundingClientRect();
            const transcript = node.querySelector('[data-lab-assistant-messages]').getBoundingClientRect();
            const composer = node.querySelector('.lab-assistant-composer-input').getBoundingClientRect();
            return {header: header.height, toolbar: toolbar.height, contextY: context.y,
                toolbarY: toolbar.y, chrome: transcript.y - header.y, composer: composer.height};
        });
        expect(chrome.header).toBeLessThanOrEqual(58);
        expect(chrome.toolbar).toBeLessThanOrEqual(46);
        expect(chrome.chrome).toBeLessThanOrEqual(106);
        expect(Math.abs(chrome.contextY - chrome.toolbarY)).toBeLessThanOrEqual(1);
        expect(chrome.composer).toBeLessThanOrEqual(100);
        await expectSquareSettingsGear(panel);
        await page.screenshot({path:info.outputPath(`assistant-empty-${theme}-${width}.png`)});
        const geometryBeforeClose = width >= 1280 ? await pageGeometry(page) : null;
        await page.keyboard.press('Escape');
        await expect(panel).toBeHidden();
        await expect(page.getByRole('button', {name:'Restore assistant', exact:true})).toBeFocused();
        expect(Math.abs(await page.evaluate(() => scrollY) - originalScroll)).toBeLessThan(2);
        if (width >= 1280) expect(await pageGeometry(page)).toEqual(geometryBeforeClose);
        await page.getByRole('button', {name:'Restore assistant', exact:true}).press('Enter');
        await selectModel(panel);
        const settings = panel.locator('[data-lab-assistant-settings]');
        await settings.locator(':scope > summary').press('Enter');
        const model = settings.getByLabel('Preview model', {exact: true});
        const effort = settings.getByLabel('Reasoning effort', {exact: true});
        await effort.selectOption('medium');
        await model.selectOption('synthetic-mini');
        await expect(effort).toHaveValue('');
        await expect(panel.locator('[data-lab-assistant-notice]')).toContainText('Model default is now selected');
        await effort.selectOption('high');
        await expect(panel.locator('[data-lab-assistant-notice]')).toBeEmpty();
        await model.selectOption('synthetic');
        await expect(effort).toHaveValue('high');
        for (const control of [model, effort]) {
            await control.focus(); await expect(control).toBeInViewport();
            const bounds = await control.boundingBox();
            expect(bounds.width).toBeGreaterThanOrEqual(44);
            expect(bounds.height).toBeGreaterThanOrEqual(44);
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        }
        await page.screenshot({path:info.outputPath(`assistant-chat-settings-${theme}-${width}.png`)});
        await effort.press('Escape');
        await expect(settings).not.toHaveAttribute('open');
        await expect(settings.locator(':scope > summary')).toBeFocused();
        await expect(panel).toBeVisible();

        const question = panel.getByLabel('Your question about the example', {exact:true});
        const send = panel.getByRole('button', {name:'Preview reply', exact:true});
        const notice = panel.locator('[data-lab-assistant-notice]');
        await expect(question).toHaveAttribute('rows', '1');
        await question.fill('An unsent synthetic draft');
        await panel.getByRole('checkbox', {name:'Use page data', exact:true}).check();
        await panel.getByRole('button', {name:'Minimize assistant', exact:true}).press('Enter');
        await expect(panel).toBeHidden();
        const restore = page.getByRole('button', {name:'Restore assistant', exact:true});
        await expect(restore).toBeFocused();
        const restoreBox = await restore.boundingBox();
        expect(restoreBox.width).toBeGreaterThanOrEqual(44);
        expect(restoreBox.height).toBeGreaterThanOrEqual(44);
        expect(restoreBox.x).toBeGreaterThanOrEqual(0);
        expect(restoreBox.x + restoreBox.width).toBeLessThanOrEqual(width);
        await expect(page.locator('main')).not.toHaveAttribute('inert');
        await page.screenshot({path:info.outputPath(`assistant-minimized-${theme}-${width}.png`)});
        await restore.press('Enter');
        await expect(question).toHaveValue('An unsent synthetic draft');
        await expect(model).toHaveValue('synthetic');
        await expect(effort).toHaveValue('high');
        await expect(panel.getByRole('checkbox', {name:'Use page data', exact:true})).toBeChecked();
        await expect(panel.getByRole('button', {name:'Minimize assistant', exact:true})).toBeFocused();
        await panel.getByRole('checkbox', {name:'Use page data', exact:true}).uncheck();
        await question.fill('First line');
        await question.press('Shift+Enter');
        await question.press('x');
        await expect(question).toHaveValue('First line\nx');
        await expect(panel.locator('[data-lab-assistant-message="user"]')).toHaveCount(0);
        await question.fill('Line\n'.repeat(30));
        expect((await question.boundingBox()).height).toBeLessThanOrEqual(120);
        await scenario(panel, 'hold');
        await question.fill('Keep my synthetic question');
        await send.press('Enter');
        await expect(notice).toHaveText('Preparing a synthetic reply…');
        await expect(panel.locator('form')).toHaveAttribute('aria-busy', 'true');
        await panel.getByRole('button', {name:'Minimize assistant', exact:true}).press('Enter');
        await expect(panel).toBeHidden();
        await page.getByRole('button', {name:'Restore assistant', exact:true}).press('Enter');
        await expect(panel.locator('form')).toHaveAttribute('aria-busy', 'true');
        await panel.getByRole('button', {name:'Stop preview', exact:true}).press('Enter');
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
        await panel.getByRole('checkbox', {name:'Use page data', exact:true}).check();
        await question.press('Enter');
        await expect(notice).toContainText('Synthetic reply ready');
        const answer = panel.locator('[data-lab-assistant-message="assistant"]');
        await expect(answer).toContainText('BRL 700.00 unreserved');
        await expect(answer).toContainText('BRL 800.00 projection');
        await expect(panel.getByRole('checkbox', {name:'Use page data', exact:true})).not.toBeChecked();
        await expect(panel.locator('[data-lab-assistant-message="user"]')).toHaveCSS('align-self', 'flex-end');
        const composer = panel.locator('[data-lab-assistant-form]');
        const composerBox = await composer.boundingBox();
        await question.fill('A longer synthetic question about the example. '.repeat(24));
        await question.press('Enter');
        await expect(panel.locator('[data-lab-assistant-message="assistant"]')).toHaveCount(2);
        const transcript = panel.locator('[data-lab-assistant-messages]');
        await expect.poll(() => transcript.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
        await transcript.evaluate(node => { node.scrollTop = 0; });
        expect(await composer.boundingBox()).toEqual(composerBox);
        await expect(question).toBeInViewport();
        expect(await panel.locator('[data-lab-assistant-body]').evaluate(node => node.scrollTop)).toBe(0);
        await page.screenshot({path:info.outputPath(`assistant-reply-${theme}-${width}.png`)});

        await panel.locator('[data-lab-assistant-history] > summary').press('Enter');
        await panel.getByRole('button', {name:'October cash review', exact:true}).press('Enter');
        await expect(answer).toContainText('Synthetic example:');
        await panel.getByRole('button', {name:'New conversation', exact:true}).press('Enter');
        await expect(answer).toHaveCount(0);
        await expect(model).toHaveValue('synthetic');
        await expect(effort).toHaveValue('high');
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
        await answer.first().locator('.lab-assistant-sources > summary').press('Enter');
        await answer.first().getByRole('link', {name:'Recorded cash and reserves ↗', exact:true}).press('Enter');
        await expect(panel).toBeHidden();
        await expect(page).toHaveURL(/#lab-assistant-cash-source$/);
        await expect(page.locator('#lab-assistant-cash-source')).toBeInViewport();
        await expect(page.locator('main')).not.toHaveAttribute('inert');
        await page.getByRole('button', {name:'Restore assistant', exact:true}).press('Enter');
        await question.fill('Draft discarded by deliberate close');
        await panel.getByRole('button', {name:'Close assistant', exact:true}).press('Enter');
        await expect(panel).toBeHidden();
        await expect(launcher).toBeFocused();
        await expect(page.getByRole('button', {name:'Restore assistant', exact:true})).toBeHidden();
        await launcher.press('Enter');
        await expect(question).toHaveValue('');
        await expect(model).toHaveValue('synthetic');
        await expect(effort).toHaveValue('high');
        await expect(panel.getByRole('checkbox', {name:'Use page data', exact:true})).not.toBeChecked();
        await expect(answer).not.toHaveCount(0);
        await panel.getByRole('button', {name:'Close assistant', exact:true}).press('Enter');
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
        await expectSquareSettingsGear(panel);
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
        for (const width of [390, 320]) {
            await page.setViewportSize({width, height:320});
            await input.fill('A line\n'.repeat(25));
            await expect(page.locator('[data-lab-assistant-shell]')).toHaveAttribute('data-lab-assistant-short', '');
            expect((await input.boundingBox()).height).toBeLessThanOrEqual(44);
            for (const control of [input, panel.locator('[data-lab-assistant-settings] > summary'), panel.getByRole('checkbox', {name:'Use page data', exact:true}), panel.getByRole('button', {name:'Preview reply', exact:true}), panel.getByLabel('Current page context', {exact:true})]) {
                await expect(control).toBeInViewport();
                const bounds = await control.boundingBox();
                expect(bounds.y + bounds.height).toBeLessThanOrEqual(320);
            }
            expect(await panel.locator('[data-lab-assistant-messages]').evaluate(node => node.clientHeight)).toBeGreaterThan(0);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path:info.outputPath(`assistant-keyboard-${width}.png`)});
            const settings = panel.locator('[data-lab-assistant-settings]');
            await settings.locator(':scope > summary').tap();
            for (const control of [settings.getByLabel('Preview model', {exact: true}), settings.getByLabel('Reasoning effort', {exact: true})]) {
                await control.focus(); await expect(control).toBeInViewport();
                const bounds = await control.boundingBox();
                expect(bounds.y).toBeGreaterThanOrEqual(0);
                expect(bounds.y + bounds.height).toBeLessThanOrEqual(320);
                expect(bounds.height).toBeGreaterThanOrEqual(44);
            }
            await page.screenshot({path:info.outputPath(`assistant-chat-settings-short-${width}.png`)});
            await settings.locator(':scope > summary').tap();
        }
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
