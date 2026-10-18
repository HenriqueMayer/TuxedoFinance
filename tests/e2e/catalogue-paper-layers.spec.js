// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const { resolve } = require('node:path');

const mapEntries = [
    {layer: 'left', destination: 'home', title: 'Home', description: 'Balances, upcoming bills and reports.'},
    {layer: 'ledger', destination: 'transactions', title: 'Transactions', description: 'Income, expenses and categories.'},
    {layer: 'knot', destination: 'accounts', title: 'Accounts', description: 'Bank accounts, cards and invoices.'},
    {layer: 'rings', destination: 'investments', title: 'Investments', description: 'Holdings, movements and dated prices.'},
    {layer: 'right', destination: 'plan', title: 'Plan', description: 'Budgets, goals and reserved cash.'},
];
const verifiedMapPages = new WeakSet();

async function openCatalogue(page) {
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
    await page.goto('/catalogue/docs/design-system.html#public-homepage');
}

async function prepare(page, theme) {
    await page.addInitScript(value => {
        localStorage.setItem('theme', value);
        // Observe the real scheduler. Quiet-frame waits use the original RAF
        // and do not create work attributed to the decorative interaction.
        const request = window.requestAnimationFrame.bind(window);
        const cancel = window.cancelAnimationFrame.bind(window);
        const observer = {requests: 0, callbacks: 0, pending: new Set(), peak: 0,
            next: () => new Promise(resolve => request(resolve))};
        window.__paperLayerFrames = observer;
        window.requestAnimationFrame = callback => {
            observer.requests++;
            const id = request(time => {
                observer.pending.delete(id);
                observer.callbacks++;
                callback(time);
            });
            observer.pending.add(id);
            observer.peak = Math.max(observer.peak, observer.pending.size);
            return id;
        };
        window.cancelAnimationFrame = id => {
            observer.pending.delete(id);
            cancel(id);
        };
    }, theme);
    await openCatalogue(page);
    await page.waitForLoadState('networkidle');
    const art = page.locator('[data-lab-bowtie]');
    await art.scrollIntoViewIfNeeded();
    await expect(art).toBeVisible();
    const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
    await expect(control).toHaveAttribute('tabindex', '0');
    await expect(control).toHaveAttribute('aria-controls', 'lab-bowtie-map');
    await expect(control).toHaveAttribute('aria-pressed', 'false');
    await expect(art.locator('[data-bowtie-layer]')).toHaveCount(5);
    expect(await art.locator('[data-bowtie-layer]').evaluateAll(nodes => nodes.map(node => node.dataset.bowtieLayer).sort()))
        .toEqual(['knot', 'ledger', 'left', 'right', 'rings']);
    await expect(art.locator('[data-bowtie-fragment]')).toHaveCount(0);
    await expect(art.locator('[data-bowtie-seal]')).toHaveCount(0);
    await expect(art.locator('[data-bowtie-map-connectors]')).toHaveCount(1);
    await expect(art.locator('[data-bowtie-map-connectors] [data-bowtie-connector]')).toHaveCount(5);
    await expect(art.locator('[data-bowtie-trigger]')).toHaveCount(1);
    await expectMap(page, false);
    expect(new URL(page.url()).search).toBe('');
    await expect(art.locator('[data-bowtie-svg]')).toHaveCSS('color', theme === 'dark' ? 'rgb(250, 248, 243)' : 'rgb(26, 46, 38)');
    return art;
}

async function pose(art) {
    return art.evaluate(owner => {
        const transform = node => {
            const value = getComputedStyle(node).transform;
            const matrix = new DOMMatrix(value === 'none' ? undefined : value);
            return [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f];
        };
        return {camera: transform(owner.querySelector('[data-bowtie-layers]')),
            planes: [...owner.querySelectorAll('[data-bowtie-layer]')].map(transform)};
    });
}

function expectOpenPose(value) {
    const [a, b] = value.camera;
    expect(Math.atan2(b, a) * 180 / Math.PI).toBeCloseTo(90, 0);
    expect(Math.hypot(a, b)).toBeCloseTo(.64, 2);
}

async function expectPaperEnvelope(art, folded) {
    const geometry = await art.evaluate(owner => {
        const svg = owner.querySelector('[data-bowtie-svg]');
        const sources = {left: 'left', ledger: 'left', right: 'right', rings: 'right', knot: 'knot'};
        const points = [...owner.querySelectorAll('[data-bowtie-layer]')].flatMap(layer => {
            // Printed lines use wing clips. Their unclipped SVG bounding boxes
            // include invisible ink, so measure each physical paper envelope.
            const box = svg.querySelector('#lab-paper-' + sources[layer.dataset.bowtieLayer]).getBBox();
            const matrix = layer.getScreenCTM();
            return [[box.x, box.y], [box.x + box.width, box.y],
                [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
                .map(([x, y]) => new DOMPoint(x, y).matrixTransform(matrix));
        });
        const rect = node => {
            const box = node.getBoundingClientRect();
            return {left: box.left, right: box.right, top: box.top, bottom: box.bottom};
        };
        return {paper: {left: Math.min(...points.map(point => point.x)), right: Math.max(...points.map(point => point.x)),
            top: Math.min(...points.map(point => point.y)), bottom: Math.max(...points.map(point => point.y))},
            svg: rect(svg), map: rect(owner.querySelector('[data-bowtie-map]')), compact: innerWidth <= 1099};
    });
    expect(geometry.paper.right - geometry.paper.left).toBeGreaterThan(0);
    expect(geometry.paper.bottom - geometry.paper.top).toBeGreaterThan(0);
    for (const edge of ['left', 'top']) {
        expect(geometry.paper[edge], 'Paper stays inside the SVG at ' + edge).toBeGreaterThanOrEqual(geometry.svg[edge] - 1);
    }
    for (const edge of ['right', 'bottom']) {
        expect(geometry.paper[edge], 'Paper stays inside the SVG at ' + edge).toBeLessThanOrEqual(geometry.svg[edge] + 1);
    }
    if (folded) {
        const [a, b] = (await pose(art)).camera;
        expect(Math.hypot(a, b), 'The resting bow tie retains its larger size').toBeCloseTo(.88, 2);
    } else if (geometry.compact) {
        expect(geometry.paper.bottom, 'The open diagram stays above the compact index').toBeLessThanOrEqual(geometry.map.top + 1);
    } else {
        expect(geometry.paper.right, 'The open diagram stays left of its links').toBeLessThanOrEqual(geometry.map.left + 1);
    }
}

async function expectMap(page, open = true) {
    const art = page.locator('[data-lab-bowtie]');
    const map = page.locator('nav[data-bowtie-map]');
    await expect(art).toHaveAttribute('data-bowtie-map-open', String(open));
    await expect(art.getByRole('button', {name: 'Explore workspaces', exact: true}))
        .toHaveAttribute('aria-expanded', String(open));
    if (open) {
        await expect(map).toBeVisible();
        await expect(map).not.toHaveAttribute('aria-hidden', 'true');
    } else {
        await expect(map).toBeHidden();
        await expect(map).toHaveAttribute('aria-hidden', 'true');
    }
    expect(await map.evaluate(node => node.inert)).toBe(!open);
    const links = map.locator('[data-bowtie-map-link]');
    await expect(links).toHaveCount(5);
    await expect(map.locator('[data-bowtie-map-link]:visible')).toHaveCount(open ? 5 : 0);
    // Destinations, copy and accessible bindings are static for a document.
    // Verify them once when exposed, then check only state during transitions.
    if (!open || verifiedMapPages.has(page)) return links;
    for (let index = 0; index < mapEntries.length; index++) {
        const entry = mapEntries[index];
        const link = links.nth(index);
        await expect(link).toHaveAttribute('data-bowtie-map-link', entry.layer);
        await expect(link).toHaveAttribute('data-lab-feature-link', entry.destination);
        await expect(link).toHaveAttribute('href', `#lab-view-${entry.destination}`);
        await expect(link).toHaveAccessibleName(entry.title);
        await expect(link).toHaveAccessibleDescription(entry.description);
        await expect(link).toContainText(entry.title);
        await expect(link).toContainText(entry.description);
    }
    verifiedMapPages.add(page);
    return links;
}

async function mapGeometry(page) {
    return page.locator('[data-bowtie-map-link]').evaluateAll(nodes => nodes.map(node => {
        const bounds = node.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(node);
        const text = range.getBoundingClientRect();
        const rect = value => [value.left + scrollX, value.top + scrollY, value.width, value.height];
        return {target: rect(bounds), contents: rect(text)};
    }));
}

function expectStableMap(actual, baseline) {
    expect(actual).toHaveLength(5);
    actual.forEach((entry, index) => {
        for (const name of ['target', 'contents']) {
            entry[name].forEach((value, component) => expect(value,
                `${mapEntries[index].title} ${name} geometry`).toBeCloseTo(baseline[index][name][component], 1));
        }
    });
}

async function expectSelectedDestination(page, entry, enhanced = true) {
    await expect(page).toHaveURL(url => url.hash === `#lab-view-${entry.destination}`);
    const target = page.locator(`[data-lab-view="${entry.destination}"]`);
    await expect(target).toBeVisible();
    await expect(page.locator('[data-lab-view]:not([hidden])')).toHaveCount(enhanced ? 1 : 5);
    if (enhanced) {
        await expect(page.locator(`[data-lab-destination="${entry.destination}"]`)).toHaveAttribute('aria-current', 'page');
    }
    return target;
}

async function expectDestination(page, entry, enhanced = true) {
    const target = await expectSelectedDestination(page, entry, enhanced);
    await expect(target).toBeInViewport();
    await expect.poll(() => target.getByRole('heading', {level: 3}).evaluate(node => {
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        return node.getBoundingClientRect().top - header.bottom;
    })).toBeGreaterThanOrEqual(-2);
}

async function quietFrames(page) {
    return page.evaluate(async () => {
        for (let index = 0; index < 4; index++) await window.__paperLayerFrames.next();
        return window.__paperLayerFrames.requests;
    });
}

async function idle(page) {
    await expect.poll(async () => {
        const before = await page.evaluate(() => window.__paperLayerFrames.requests);
        return await quietFrames(page) - before;
    }).toBe(0);
    expect(await page.evaluate(() => window.__paperLayerFrames.pending.size)).toBe(0);
}

async function resting(page, art, original) {
    await expectMap(page, false);
    await expect(art).toHaveAttribute('data-bowtie-state', 'resting');
    await expect.poll(() => pose(art)).toEqual(original);
    await idle(page);
}

async function pointerTargets(art) {
    return art.locator('[data-bowtie-svg]').evaluate(svg => {
        const at = (node, x, y) => {
            const point = new DOMPoint(x, y).matrixTransform(node.getScreenCTM());
            return {x: point.x, y: point.y};
        };
        // The stable painted trigger shares the closed artwork's transform.
        // Empty viewport space must never act as an oversized hover target.
        const paper = matchMedia('(prefers-reduced-motion: reduce)').matches
            ? svg.querySelector('[data-bowtie-layer="left"]') : svg.querySelector('[data-bowtie-trigger]');
        return {bowtie: at(paper, 150, 220), empty: at(svg, 600, 10)};
    });
}

async function activatePainted(page, art, touch = false) {
    const visiblePaperPoint = () => art.locator('[data-bowtie-svg]').evaluate(svg => {
        const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        const layers = [...svg.querySelectorAll('[data-bowtie-layer]')];
        const candidates = reduced ? layers : [svg.querySelector('[data-bowtie-trigger]'), ...layers];
        for (const node of candidates) {
            const layer = node.dataset.bowtieLayer;
            const x = !layer || ['left', 'ledger'].includes(layer) ? 142 : ['right', 'rings'].includes(layer) ? 438 : 288;
            const point = new DOMPoint(x, 220).matrixTransform(node.getScreenCTM());
            if (point.x < 8 || point.x > innerWidth - 8 || point.y < header.bottom + 8 || point.y > innerHeight - 8) continue;
            const hit = document.elementFromPoint(point.x, point.y);
            if (svg.contains(hit) && hit.closest('[data-bowtie-trigger], [data-bowtie-layers]')) {
                return {x: point.x, y: point.y};
            }
        }
        return null;
    });
    let point = await visiblePaperPoint();
    if (!point) {
        // A short viewport can leave the rotated reduced-motion wing behind
        // the sticky toolbar even while the SVG frame intersects the viewport.
        // Reveal the frame, then hit-test the actual painted paper again.
        await art.locator('[data-bowtie-svg]').evaluate(node => node.scrollIntoView({block: 'center', behavior: 'instant'}));
        point = await visiblePaperPoint();
    }
    expect(point, 'Activation must target visible painted paper below the sticky header').not.toBeNull();
    if (touch) await page.touchscreen.tap(point.x, point.y);
    else await page.mouse.click(point.x, point.y);
}

for (const theme of ['light', 'dark']) {
    test('catalogue paper map uses one SVG control with stable pointer and keyboard feedback (' + theme + ')', async ({page}, info) => {
        await page.setViewportSize({width: 1440, height: 1000});
        await page.emulateMedia({reducedMotion: 'no-preference'});
        const art = await prepare(page, theme);
        const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
        const links = page.locator('[data-bowtie-map-link]');
        await expect(art).toHaveAttribute('data-bowtie-motion', 'full');
        const original = await pose(art);
        const geometry = await mapGeometry(page);
        const historyLength = await page.evaluate(() => history.length);
        await resting(page, art, original);
        await expectPaperEnvelope(art, true);
        await control.focus();
        await page.keyboard.press('Tab');
        expect(await page.evaluate(() => Boolean(document.activeElement.closest('[data-bowtie-map]'))),
            'The closed, inert map is absent from the Tab sequence').toBe(false);
        const focusOwner = page.locator('#public-homepage a[href="#lab-home-features"]');
        await focusOwner.focus();
        await art.scrollIntoViewIfNeeded();
        const top = await page.evaluate(() => scrollY);
        const points = await pointerTargets(art);
        await page.mouse.move(4, 4);
        await page.mouse.move(points.empty.x, points.empty.y);
        await page.mouse.click(points.empty.x, points.empty.y);
        await resting(page, art, original);
        await page.evaluate(() => { window.__paperLayerFrames.peak = window.__paperLayerFrames.pending.size; });

        // Painted-area hover opens without a follow-up movement; the SVG's
        // empty rectangular frame is never an oversized pointer control.
        await page.mouse.move(points.bowtie.x, points.bowtie.y);
        await expectMap(page);
        await expect(control).toHaveAttribute('aria-pressed', 'false');
        await idle(page);
        const opened = await pose(art);
        expectOpenPose(opened);
        await expectPaperEnvelope(art, false);
        expect(opened.camera).not.toEqual(original.camera);
        await page.mouse.move(points.bowtie.x + 12, points.bowtie.y + 8);
        await idle(page);
        const moved = await pose(art);
        const depths = moved.planes.map((matrix, index) => matrix.map((value, channel) => value - opened.planes[index][channel]));
        expect(new Set(depths.map(matrix => JSON.stringify(matrix))).size).toBeGreaterThan(1);
        expect(await page.evaluate(() => window.__paperLayerFrames.peak)).toBeLessThanOrEqual(1);
        expectStableMap(await mapGeometry(page), geometry);
        await quietFrames(page);
        expect(await pose(art), 'A parked pointer does not keep a RAF loop running').toEqual(moved);
        expect(Math.abs(await page.evaluate(() => scrollY) - top)).toBeLessThan(2);

        // Escape blocks a stationary pointer from reopening the folding ink.
        await page.keyboard.press('Escape');
        await resting(page, art, original);
        await quietFrames(page);
        await expect(control).toBeFocused();
        await page.mouse.move(points.bowtie.x + 16, points.bowtie.y + 8);
        await expectMap(page);
        await idle(page);
        const home = await links.first().boundingBox();
        await page.mouse.move(home.x + home.width / 2, home.y + home.height / 2, {steps: 12});
        await expectMap(page);
        await expect(art).toHaveAttribute('data-bowtie-highlight', 'left');
        expectStableMap(await mapGeometry(page), geometry);
        await art.screenshot({path: info.outputPath('paper-map-hover-' + theme + '.png')});
        await page.mouse.move(4, 4);
        await resting(page, art, original);

        // A deliberate click fixes an already hovered map. A second one folds
        // it, preserving the same single accessible SVG control.
        await activatePainted(page, art);
        await expect(control).toHaveAttribute('aria-pressed', 'true');
        await expectMap(page);
        await page.mouse.move(4, 4);
        await expectMap(page);
        await idle(page);
        await activatePainted(page, art);
        await resting(page, art, original);
        await page.mouse.move(4, 4);
        await control.focus();
        await control.press('Tab');
        await page.keyboard.press('Shift+Tab');
        await expect(control).toBeFocused();
        expect(await control.evaluate(node => node.matches(':focus-visible'))).toBe(true);
        expect(await control.evaluate(node => {
            const style = getComputedStyle(node);
            return parseFloat(style.outlineWidth) > 0 && style.outlineStyle !== 'none';
        })).toBe(true);
        const keyboardTop = await page.evaluate(() => scrollY);
        await control.press('Enter');
        await expect(control).toHaveAttribute('aria-pressed', 'true');
        await expectMap(page);
        await idle(page);
        expectStableMap(await mapGeometry(page), geometry);
        await control.press('Space');
        await resting(page, art, original);
        await expect(control).toBeFocused();
        expect(Math.abs(await page.evaluate(() => scrollY) - keyboardTop)).toBeLessThan(2);
        expect(await page.evaluate(() => history.length)).toBe(historyLength);

        await control.press('Enter');
        await expectMap(page);
        await links.first().hover();
        await links.first().focus();
        await page.keyboard.press('Tab');
        await expect(links.nth(1)).toBeFocused();
        expect(await links.first().evaluate(node => node.matches(':hover'))).toBe(true);
        await expect(art).toHaveAttribute('data-bowtie-highlight', 'ledger');
        expectStableMap(await mapGeometry(page), geometry);
        await page.keyboard.press('Escape');
        await resting(page, art, original);
        await expect(control).toBeFocused();
        await page.mouse.move(4, 4);
    });

    test('catalogue paper map preserves native workspace destinations and history (' + theme + ')', async ({page}) => {
        await page.setViewportSize({width: 1440, height: 1000});
        await page.emulateMedia({reducedMotion: 'no-preference'});
        const art = await prepare(page, theme);
        const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
        const links = page.locator('[data-bowtie-map-link]');
        const original = await pose(art);
        const geometry = await mapGeometry(page);
        const departurePositions = [];
        const destinationPositions = [];
        // Register after the catalogue initializes so this observer inspects
        // its synchronous response to popstate, before native scroll recovery.
        await page.evaluate(() => {
            window.__catalogueHistoryEvents = [];
            for (const type of ['popstate', 'hashchange']) window.addEventListener(type, () => {
                window.__catalogueHistoryEvents.push({type, hash: location.hash,
                    visible: [...document.querySelectorAll('[data-lab-view]:not([hidden])')]
                        .map(view => view.dataset.labView)});
            });
        });
        for (let index = 0; index < mapEntries.length; index++) {
            await control.focus();
            await control.press('Enter');
            await expectMap(page);
            for (let step = 0; step <= index; step++) await page.keyboard.press('Tab');
            const link = links.nth(index);
            await expect(link).toBeFocused();
            await expect(art).toHaveAttribute('data-bowtie-highlight', mapEntries[index].layer);
            expectStableMap(await mapGeometry(page), geometry);
            if (index) departurePositions[index - 1] = await page.evaluate(() => scrollY);
            await link.press('Enter');
            await expectDestination(page, mapEntries[index]);
            destinationPositions[index] = await page.evaluate(() => scrollY);
            await expect(art).not.toBeInViewport();
            await resting(page, art, original);
            await expect(control).toHaveAttribute('aria-pressed', 'false');
        }
        const lastDestinationPosition = await page.evaluate(() => scrollY);
        await page.evaluate(() => { window.__catalogueHistoryEvents = []; });
        await page.goBack();
        await expectSelectedDestination(page, mapEntries[3]);
        await expect.poll(() => page.evaluate(() => window.__catalogueHistoryEvents[0]))
            .toEqual({type: 'popstate', hash: '#lab-view-investments', visible: ['investments']});
        // Native fragment traversal may restore the departure position or its
        // destination anchor. Both are measured in this real keyboard journey;
        // an unrelated jump is never accepted or repaired by the test.
        await expect.poll(async () => {
            const restored = await page.evaluate(() => scrollY);
            return Math.min(Math.abs(restored - departurePositions[3]),
                Math.abs(restored - destinationPositions[3]));
        })
            .toBeLessThan(2);
        const restored = await page.evaluate(() => scrollY);
        if (Math.abs(restored - destinationPositions[3]) < 2) await expectDestination(page, mapEntries[3]);
        await page.evaluate(() => { window.__catalogueHistoryEvents = []; });
        await page.goForward();
        await expectSelectedDestination(page, mapEntries[4]);
        await expect.poll(() => page.evaluate(() => window.__catalogueHistoryEvents[0]))
            .toEqual({type: 'popstate', hash: '#lab-view-plan', visible: ['plan']});
        await expect.poll(async () => Math.abs(await page.evaluate(() => scrollY) - lastDestinationPosition))
            .toBeLessThan(2);
    });
}

// Keep viewport transitions together, but give each theme its own default
// test budget instead of accumulating two complete touch journeys in 30s.
for (const theme of ['light', 'dark']) {
    test(`catalogue paper map keeps touch activation, compact targets and native scrolling (${theme})`, async ({browser}, info) => {
        const context = await browser.newContext({viewport: {width: 390, height: 844}, hasTouch: true, isMobile: true});
        try {
            const page = await context.newPage();
            await page.emulateMedia({reducedMotion: 'no-preference'});
            const art = await prepare(page, theme);
            const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
            for (const width of [320, 900, 390]) {
                await page.setViewportSize({width, height: 844});
                await control.scrollIntoViewIfNeeded();
                await quietFrames(page);
                await expectMap(page, false);
                const closed = await pose(art);
                const geometry = await mapGeometry(page);
                await expectPaperEnvelope(art, true);
                await activatePainted(page, art, true);
                const links = await expectMap(page);
                await expect(control).toHaveAttribute('aria-pressed', 'true');
                await idle(page);
                await expectPaperEnvelope(art, false);
                const targets = await links.evaluateAll(nodes => nodes.map(node => {
                    const bounds = node.getBoundingClientRect();
                    return {width: bounds.width, height: bounds.height};
                }));
                targets.forEach(target => {
                    expect(target.width).toBeGreaterThanOrEqual(44);
                    expect(target.height).toBeGreaterThanOrEqual(44);
                });
                for (const entry of await mapGeometry(page)) {
                    const [left, top, targetWidth, targetHeight] = entry.target;
                    const [textLeft, textTop, textWidth, textHeight] = entry.contents;
                    expect(textLeft).toBeGreaterThanOrEqual(left - 1);
                    expect(textTop).toBeGreaterThanOrEqual(top - 1);
                    expect(textLeft + textWidth).toBeLessThanOrEqual(left + targetWidth + 1);
                    expect(textTop + textHeight).toBeLessThanOrEqual(top + targetHeight + 1);
                }
                expectStableMap(await mapGeometry(page), geometry);
                expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
                    theme + ' overflow at ' + width + 'px').toBe(true);
                await expect(art.locator('[data-bowtie-map-connectors]')).toBeHidden();
                await activatePainted(page, art, true);
                await resting(page, art, closed);
            }
            await control.scrollIntoViewIfNeeded();
            const original = await pose(art);
            const bounds = await control.boundingBox();
            const top = await page.evaluate(() => scrollY);
            const x = bounds.x + bounds.width * .35;
            const y = Math.min(bounds.y + bounds.height * .8, 740);
            const touch = await context.newCDPSession(page);
            await touch.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{x, y}]});
            for (let step = 1; step <= 8; step++) {
                await touch.send('Input.dispatchTouchEvent', {type: 'touchMove', touchPoints: [{x, y: y - step * 20}]});
            }
            await touch.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
            await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(top + 30);
            await expect(control).toHaveAttribute('aria-pressed', 'false');
            await resting(page, art, original);

            await page.setViewportSize({width: 390, height: 600});
            await control.scrollIntoViewIfNeeded();
            await quietFrames(page);
            const shortClosed = await pose(art);
            await activatePainted(page, art, true);
            await expect(control).toHaveAttribute('aria-pressed', 'true');
            await expectMap(page);
            await expect(control).toBeInViewport({ratio: .1});
            await expect.poll(() => control.evaluate(node => {
                const bounds = node.getBoundingClientRect();
                const header = document.querySelector('[data-catalogue-header]').getBoundingClientRect();
                return Math.min(innerHeight, bounds.bottom) - Math.max(0, header.bottom, bounds.top);
            })).toBeGreaterThan(40);
            await idle(page);
            expectOpenPose(await pose(art));
            await expectPaperEnvelope(art, false);
            await page.screenshot({path: info.outputPath('paper-map-short-viewport-' + theme + '.png')});
            await activatePainted(page, art, true);
            await resting(page, art, shortClosed);

            await page.emulateMedia({reducedMotion: 'reduce'});
            await expectMap(page, false);
            const reduced = await pose(art);
            expectOpenPose(reduced);
            const requests = await quietFrames(page);
            await activatePainted(page, art, true);
            await expectMap(page);
            expect(await pose(art)).toEqual(reduced);
            await activatePainted(page, art, true);
            await resting(page, art, reduced);
            expect(await quietFrames(page), 'Reduced-motion touch exposes the map without RAF').toBe(requests);
        } finally { await context.close(); }
    });
}

test('catalogue paper map keeps the same SVG access and a static reduced-motion pose in both themes', async ({browser}) => {
    for (const theme of ['light', 'dark']) {
        const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
        try {
            const page = await context.newPage();
            await page.emulateMedia({reducedMotion: 'reduce'});
            const art = await prepare(page, theme);
            const control = art.getByRole('button', {name: 'Explore workspaces', exact: true});
            const original = await pose(art);
            expectOpenPose(original);
            await expectPaperEnvelope(art, false);
            await expect(art).toHaveAttribute('data-bowtie-motion', 'reduced');
            const geometry = await mapGeometry(page);
            const points = await pointerTargets(art);
            const before = await quietFrames(page);
            await page.mouse.move(points.empty.x, points.empty.y);
            await page.mouse.click(points.empty.x, points.empty.y);
            await resting(page, art, original);
            await page.mouse.move(points.bowtie.x, points.bowtie.y);
            await expectMap(page);
            expectStableMap(await mapGeometry(page), geometry);
            expect(await pose(art)).toEqual(original);
            await page.mouse.move(4, 4);
            await resting(page, art, original);
            await control.focus();
            await control.press('Enter');
            const links = await expectMap(page);
            await page.keyboard.press('Tab');
            await expect(links.first()).toBeFocused();
            await page.keyboard.press('Escape');
            await resting(page, art, original);
            await expect(control).toBeFocused();

            await control.press('Enter');
            await expectMap(page);
            await page.keyboard.press('Tab');
            await expect(links.first()).toBeFocused();
            const resizeTop = await page.evaluate(() => scrollY);
            await page.setViewportSize({width: 1440, height: 980});
            await expect(control).toBeFocused();
            await resting(page, art, original);
            expect(Math.abs(await page.evaluate(() => scrollY) - resizeTop)).toBeLessThan(2);
            expect(await quietFrames(page), 'Reduced-motion hover and keyboard access never schedule decorative RAF').toBe(before);

            await page.emulateMedia({reducedMotion: 'no-preference'});
            await expect(art).toHaveAttribute('data-bowtie-motion', 'full');
            await expect.poll(() => pose(art)).not.toEqual(original);
            await control.focus();
            await control.press('Enter');
            await expectMap(page);
            await idle(page);
            expect(await pose(art)).toEqual(original);
            await page.keyboard.press('Tab');
            await expect(links.first()).toBeFocused();
            const preferenceTop = await page.evaluate(() => scrollY);
            await page.emulateMedia({reducedMotion: 'reduce'});
            await expect(art).toHaveAttribute('data-bowtie-motion', 'reduced');
            await expect(control).toBeFocused();
            await expect(control).toHaveAttribute('aria-pressed', 'false');
            await resting(page, art, original);
            expect(Math.abs(await page.evaluate(() => scrollY) - preferenceTop)).toBeLessThan(2);
            const runtime = await quietFrames(page);
            await control.press('Space');
            await expectMap(page);
            expect(await pose(art)).toEqual(original);
            await page.keyboard.press('Escape');
            await expect(control).toBeFocused();
            await resting(page, art, original);
            expect(await quietFrames(page)).toBe(runtime);
        } finally { await context.close(); }
    }
});

test('catalogue keeps original artwork and native workspace links without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    try {
        const page = await context.newPage();
        await openCatalogue(page);
        const art = page.locator('[data-lab-bowtie]');
        await art.scrollIntoViewIfNeeded();
        await expect(art.locator('[data-bowtie-whole]')).toBeVisible();
        await expect(art.locator('[data-bowtie-svg]')).toHaveAttribute('role', 'img');
        await expect(art.getByRole('button')).toHaveCount(0);
        const drawing = await art.locator('[data-bowtie-svg]').innerHTML();
        const bounds = await art.boundingBox();
        await page.mouse.move(bounds.x + bounds.width * .45, bounds.y + bounds.height * .4, {steps: 5});
        expect(await art.locator('[data-bowtie-svg]').innerHTML()).toBe(drawing);
        const native = page.locator('.lab-native-workspace-index');
        await expect(native).toBeVisible();
        const links = native.getByRole('link');
        await expect(links).toHaveText(mapEntries.map(entry => entry.title));
        for (let index = 0; index < mapEntries.length; index++) {
            await expect(links.nth(index)).toHaveAttribute('href', `#lab-view-${mapEntries[index].destination}`);
            await links.nth(index).press('Enter');
            await expectDestination(page, mapEntries[index], false);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await art.screenshot({path: info.outputPath('paper-layers-native-static.png')});
    } finally { await context.close(); }
});
