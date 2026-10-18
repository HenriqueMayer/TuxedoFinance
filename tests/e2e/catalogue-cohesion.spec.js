// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');
const { selectChoice } = require('./helpers/forms');

const sections = ['data', 'components', 'motion', 'icons', 'workspaces'];

for (const theme of ['light', 'dark']) {
    test(`catalogue period arrows keep their slots when reset appears (${theme})`, async ({page}, info) => {
        await openCatalogue(page, theme);
        for (const width of [1440, 390]) {
            await page.setViewportSize({width, height: 900});
            const example = page.locator('[data-lab-period-example]');
            await example.scrollIntoViewIfNeeded();
            const previous = example.getByRole('button', {name: 'Previous month', exact: true});
            const next = example.getByRole('button', {name: 'Next month', exact: true});
            const reset = example.getByRole('button', {name: 'Back to this month', exact: true});
            const geometry = async () => example.evaluate(node => {
                const parent = node.getBoundingClientRect();
                return [...node.querySelectorAll('[data-lab-period-step]')].map(button => {
                    const box = button.getBoundingClientRect();
                    return [box.x - parent.x, box.y - parent.y, box.width, box.height];
                });
            });
            const initial = await geometry();
            await expect(reset).toBeHidden();
            await previous.focus();
            await page.keyboard.press('Tab');
            await expect(next).toBeFocused();
            await page.keyboard.press('Enter');
            await expect(reset).toBeVisible();
            expect(await geometry()).toEqual(initial);
            await expect(example.locator('[data-lab-period-context]')).toHaveText('Planned month');
            await page.keyboard.press('Tab');
            await expect(reset).toBeFocused();
            await page.keyboard.press('Enter');
            await expect(reset).toBeHidden();
            expect(await geometry()).toEqual(initial);
            await previous.press('Enter');
            await expect(example.locator('[data-lab-period-context]')).toHaveText('Completed month');
            expect(await geometry()).toEqual(initial);
            await page.screenshot({path: info.outputPath(`period-${theme}-${width}.png`)});
            await reset.press('Enter');
        }
    });
}

async function openCatalogue(page, theme) {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    const root = resolve(__dirname, '../..');
    await page.route('**/catalogue/**', async route => {
        const name = new URL(route.request().url()).pathname.slice('/catalogue/'.length);
        const documents = ['docs/design-system.html', 'docs/design-system.css',
            'docs/design-system.js', 'docs/design-system-layers.js', 'docs/design-system-calendar.js'];
        if ((!documents.includes(name) && !name.startsWith('static/')) || name.split('/').includes('..')) return route.abort();
        const types = {html: 'text/html', css: 'text/css', js: 'application/javascript',
            woff2: 'font/woff2', png: 'image/png', jpg: 'image/jpeg', ico: 'image/x-icon'};
        await route.fulfill({path: resolve(root, name), contentType: types[name.split('.').pop()]});
    });
    await page.goto('/catalogue/docs/design-system.html#data');
    await page.evaluate(() => document.fonts.ready);
}

async function presentation(control) {
    return control.evaluate(async node => {
        getComputedStyle(node).transform;
        await Promise.all(node.getAnimations({subtree: true}).map(animation => animation.finished.catch(() => {})));
        const style = getComputedStyle(node);
        const bounds = node.getBoundingClientRect();
        const arrow = node.querySelector('[aria-hidden="true"]');
        const arrowBounds = arrow?.getBoundingClientRect();
        const label = [...node.childNodes].find(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        const range = document.createRange();
        if (label) range.selectNodeContents(label);
        const text = label ? range.getBoundingClientRect() : null;

        // Read browser-resolved colors, including color-mix and alpha tokens.
        // Composite ancestor surfaces so transparent labels are checked against
        // their actual CSS background rather than an assumed white canvas.
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 1;
        const context = canvas.getContext('2d');
        const rgba = value => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = value;
            context.fillRect(0, 0, 1, 1);
            return [...context.getImageData(0, 0, 1, 1).data].map((part, index) => index === 3 ? part / 255 : part);
        };
        const composite = (foreground, background) => foreground.slice(0, 3)
            .map((channel, index) => channel * foreground[3] + background[index] * (1 - foreground[3]));
        const background = element => {
            const ancestors = [];
            for (let current = element; current; current = current.parentElement) ancestors.unshift(current);
            return ancestors.reduce((color, ancestor) => composite(rgba(getComputedStyle(ancestor).backgroundColor), color), [255, 255, 255]);
        };
        const luminance = color => color.map(channel => {
            const unit = channel / 255;
            return unit <= .04045 ? unit / 12.92 : ((unit + .055) / 1.055) ** 2.4;
        }).reduce((total, channel, index) => total + channel * [.2126, .7152, .0722][index], 0);
        const contrast = (foreground, surface) => {
            const values = [luminance(composite(rgba(foreground), surface)), luminance(surface)].sort((a, b) => b - a);
            return (values[0] + .05) / (values[1] + .05);
        };
        return {
            width: bounds.width, height: bounds.height, transform: style.transform,
            layout: [node.offsetLeft, node.offsetTop, node.offsetWidth, node.offsetHeight],
            label: text ? [text.left - bounds.left, text.top - bounds.top, text.width, text.height] : null,
            radii: [style.borderTopLeftRadius, style.borderTopRightRadius, style.borderBottomRightRadius, style.borderBottomLeftRadius],
            arrow: arrow ? {left: arrowBounds.left - bounds.left, top: arrowBounds.top - bounds.top,
                width: arrowBounds.width, height: arrowBounds.height, transform: getComputedStyle(arrow).transform} : null,
            textContrast: contrast(style.color, background(node)),
            outline: {width: parseFloat(style.outlineWidth), style: style.outlineStyle,
                contrast: contrast(style.outlineColor, background(node.parentElement))},
            focusVisible: node.matches(':focus-visible'), fontSize: parseFloat(style.fontSize),
        };
    });
}

function expectStationary(actual, original) {
    expect(actual.radii).toEqual(original.radii);
    expect(actual.layout, 'The action target does not reflow').toEqual(original.layout);
    actual.label.forEach((value, index) => expect(value, 'The action label does not reflow').toBeCloseTo(original.label[index], 1));
    for (const dimension of ['width', 'height']) expect(actual[dimension]).toBeCloseTo(original[dimension], 1);
    expect(actual.arrow).not.toBeNull();
    for (const dimension of ['width', 'height']) {
        expect(actual.arrow[dimension], 'Stationary decorative arrow ' + dimension).toBeCloseTo(original.arrow[dimension], 1);
    }
    for (const dimension of ['left', 'top']) {
        expect(Math.abs(actual.arrow[dimension] - original.arrow[dimension]), 'The arrow response stays within 2px').toBeLessThanOrEqual(2);
    }
}

function expectVisibleFocus(value) {
    expect(value.focusVisible).toBe(true);
    expect(value.outline.width).toBeGreaterThanOrEqual(1);
    expect(value.outline.style).not.toBe('none');
}

async function expectScrollRest(region) {
    await expect.poll(() => region.evaluate(async node => {
        const left = node.scrollLeft;
        for (let index = 0; index < 6; index++) await new Promise(resolve => requestAnimationFrame(resolve));
        return Math.abs(node.scrollLeft - left) < .1;
    }), {message: 'Native keyboard scrolling settles before the next direction'}).toBe(true);
}

async function expectSection(page, id) {
    const section = page.locator('#' + id);
    await expect(section).toHaveCount(1);
    // The catalogue keeps real fragment destinations regardless of decoration.
    const destination = page.locator('[data-catalogue-header] a[href="#' + id + '"]');
    await expect(destination).toHaveCount(1);
    await destination.focus();
    await destination.press('Enter');
    await expect(page).toHaveURL(url => url.hash === '#' + id);
    const heading = section.getByRole('heading', {level: 2});
    await expect(heading).toHaveCount(1);
    await expect(heading).toHaveAccessibleName(/\S/);
    await expect(heading).toBeInViewport();
    const layout = await heading.evaluate(node => {
        const box = node.getBoundingClientRect();
        const owner = node.closest('section').getBoundingClientRect();
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        return {top: box.top - header.bottom, left: box.left - owner.left, right: owner.right - box.right};
    });
    expect(layout.top).toBeGreaterThanOrEqual(-2);
    expect(layout.left).toBeGreaterThanOrEqual(-1);
    expect(layout.right).toBeGreaterThanOrEqual(-1);
    const text = await presentation(heading);
    expect(text.fontSize).toBeGreaterThanOrEqual(24);
    expect(text.textContrast).toBeGreaterThanOrEqual(4.5);
}

async function expectVisibleInvalidAmount(page) {
    const form = page.locator('#lab-transaction-form');
    await form.locator('[data-lab-reset]').press('Enter');
    const type = form.locator('#lab-entry-type-expense');
    await type.focus();
    await type.press('Space');
    await type.press('Tab');
    await expect(type).toBeChecked();
    await form.locator('#lab-entry-title').fill('Visible recovery example');
    await form.locator('#lab-entry-date').fill('2026-10-17');
    await selectChoice(form.locator('#lab-entry-category'), '1001');
    await form.getByRole('button', {name: 'Preview entry', exact: true}).press('Enter');
    const amount = form.locator('#lab-entry-amount');
    await expect(amount).toBeFocused();
    await expect(amount).toHaveAttribute('aria-invalid', 'true');
    const error = form.locator('#lab-entry-amount-error');
    await expect(error).toBeVisible();
    await expect(error).toBeInViewport();
    await expect.poll(() => amount.evaluate(node => {
        const box = node.getBoundingClientRect();
        const error = document.getElementById('lab-entry-amount-error').getBoundingClientRect();
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        return {underHeader: Math.min(box.top, error.top) >= header.bottom,
            insideBottom: Math.max(box.bottom, error.bottom) <= innerHeight};
    })).toEqual({underHeader: true, insideBottom: true});
}

async function expectOutlookReconciles(table) {
    const rows = await table.locator('tbody tr').evaluateAll(nodes => nodes.map(node => {
        const cents = text => Math.round(Number(text.replace(/−/g, '-').replace(/[^\d.-]/g, '')) * 100);
        return [...node.querySelectorAll('th, td')].slice(1).map(cell => cents(cell.textContent));
    }));
    expect(rows.length).toBeGreaterThan(1);
    rows.forEach((values, index) => {
        expect(values).toHaveLength(5);
        expect(values.every(Number.isFinite)).toBe(true);
        const [income, expenses, investments, net, closing] = values;
        expect(net, 'Outlook net reconciles with displayed flows').toBe(income - expenses - investments);
        if (index) expect(closing, 'Outlook closing follows the previous closing plus this net').toBe(rows[index - 1][4] + net);
    });
}

for (const theme of ['light', 'dark']) {
    test('catalogue cohesion preserves readable sections, stable actions and visible error recovery (' + theme + ')', async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 900});
        await openCatalogue(page, theme);
        for (const id of sections) await expectSection(page, id);
        const table = page.locator('#lab-outlook-scroll').getByRole('table');
        if (theme === 'light') await expectOutlookReconciles(table);
        const primary = page.locator('#components').getByRole('button', {name: 'Primary', exact: true});
        const motion = page.locator('#motion').getByRole('button', {name: 'Primary', exact: true});
        const empty = page.locator('#data').getByRole('link', {name: /^New transaction$/i});
        await expect(empty).toHaveAttribute('href', '#forms');
        const approved = await presentation(page.locator('#lab-view-home').getByRole('link', {name: 'New entry', exact: true}));
        expect(approved.height, 'Approved primary actions retain a 44px target').toBeGreaterThanOrEqual(44);
        for (const control of [primary, motion, empty]) {
            await page.mouse.move(0, 0);
            await control.scrollIntoViewIfNeeded();
            const original = await presentation(control);
            expect(original.height, 'Primary specimens match the approved action height').toBeCloseTo(approved.height, 1);
            expect(original.radii, 'Primary specimens match the approved silhouette').toEqual(approved.radii);
            expect(original.arrow).not.toBeNull();
            expect(original.textContrast).toBeGreaterThanOrEqual(4.5);
            await control.hover();
            expect(await control.evaluate(node => node.matches(':hover'))).toBe(true);
            expectStationary(await presentation(control), original);
            await page.mouse.move(0, 0);
            await control.focus();
            await control.press('Tab');
            await page.keyboard.press('Shift+Tab');
            await expect(control).toBeFocused();
            const focused = await presentation(control);
            expectStationary(focused, original);
            expectVisibleFocus(focused);
            expect(focused.textContrast).toBeGreaterThanOrEqual(4.5);
        }
        const uiActions = [
            ['button', 'Primary'], ['button', 'Secondary solid'], ['button', 'Outline'],
            ['button', 'Danger soft'], ['button', 'Danger solid'], ['link', 'Text link'],
        ];
        for (const [role, name] of uiActions) {
            const control = page.locator('#components').getByRole(role, {name, exact: true});
            // Remove both active states before measuring the resting colors.
            await page.locator('[data-catalogue-header] a[href="#components"]').focus();
            await page.mouse.move(0, 0);
            await control.scrollIntoViewIfNeeded();
            expect(await control.evaluate(node => node.matches(':hover, :focus'))).toBe(false);
            expect((await presentation(control)).textContrast, name + ' resting text contrast (' + theme + ')')
                .toBeGreaterThanOrEqual(4.5);
            await control.hover();
            expect(await control.evaluate(node => node.matches(':hover'))).toBe(true);
            expect((await presentation(control)).textContrast, name + ' hovered text contrast (' + theme + ')')
                .toBeGreaterThanOrEqual(4.5);
            await page.mouse.move(0, 0);
            await control.focus();
            await control.press('Tab');
            await page.keyboard.press('Shift+Tab');
            await expect(control).toBeFocused();
            const focused = await presentation(control);
            expect(focused.focusVisible, name + ' uses keyboard focus').toBe(true);
            expect(focused.textContrast, name + ' focused text contrast (' + theme + ')')
                .toBeGreaterThanOrEqual(4.5);
        }
        await empty.press('Enter');
        await expect(page).toHaveURL(/#forms$/);
        await expectVisibleInvalidAmount(page);

        await page.emulateMedia({reducedMotion: 'reduce'});
        const movement = await page.locator('#data, #components, #motion, #icons, #workspaces')
            .locator('a, button, summary, svg').evaluateAll(nodes => nodes.map(node => {
                const style = getComputedStyle(node);
                return {transition: style.transitionDuration.split(',').every(value => parseFloat(value) === 0),
                    animation: node.getAnimations().filter(item => item.playState === 'running').length};
            }));
        expect(movement.length).toBeGreaterThan(5);
        expect(movement.every(item => item.transition && item.animation === 0)).toBe(true);
        await page.locator('#components').screenshot({path: info.outputPath('components-' + theme + '.png')});
        await page.locator('#motion').screenshot({path: info.outputPath('motion-' + theme + '.png')});
    });

    test('catalogue cohesion keeps mobile tables internally scrollable and focus below the header (' + theme + ')', async ({page}, info) => {
        await page.emulateMedia({reducedMotion: 'reduce'});
        await page.setViewportSize({width: 390, height: 700});
        await openCatalogue(page, theme);
        for (const width of [390, 320]) {
            await page.setViewportSize({width, height: 700});
            for (const id of sections) await expectSection(page, id);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
                'Document overflow at ' + width + 'px').toBe(true);
            for (const [id, label, name] of [
                ['lab-outlook-scroll', 'lab-outlook-title', /Outlook/i],
                ['lab-semantic-scroll', 'lab-semantic-title', /Semantic mapping/i],
            ]) {
                const region = page.locator('#' + id);
                await expect(region).toHaveAttribute('role', 'region');
                await expect(region).toHaveAttribute('aria-labelledby', label);
                await expect(region).toHaveAttribute('tabindex', '0');
                await expect(region).toHaveAccessibleName(name);
                expect(await region.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
                await region.scrollIntoViewIfNeeded();
                await region.focus();
                await region.press('Tab');
                await page.keyboard.press('Shift+Tab');
                await expect(region).toBeFocused();
                expectVisibleFocus(await presentation(region));
                const before = await page.evaluate(() => ({x: scrollX, y: scrollY}));
                const left = await region.evaluate(node => node.scrollLeft);
                await region.press('ArrowRight');
                await expect.poll(() => region.evaluate(node => node.scrollLeft)).toBeGreaterThan(left);
                await expectScrollRest(region);
                const right = await region.evaluate(node => node.scrollLeft);
                expect(await page.evaluate(() => scrollX)).toBe(before.x);
                expect(Math.abs(await page.evaluate(() => scrollY) - before.y)).toBeLessThan(2);
                await region.press('ArrowLeft');
                await expect.poll(() => region.evaluate(node => node.scrollLeft)).toBeLessThan(right);
                await expectScrollRest(region);
            }
            await expectVisibleInvalidAmount(page);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path: info.outputPath('mobile-error-' + width + '-' + theme + '.png')});
        }
    });
}
