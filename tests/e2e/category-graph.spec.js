// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {requestPath, expectContextualDestination} = require('./helpers/navigation');

async function post(page, path, form) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...form},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), path).toBe(302);
}
async function seed(page, info) {
    const username = `category-graph-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-Graph-2026!', password2: 'Tuxedo-Graph-2026!'});
    await post(page, '/categories/create/', {name: 'Living costs', transaction_type: 'EXPENSE'});
    await page.goto('/categories/create/');
    const living = await page.locator('#id_parent_category option').filter({hasText: /^Living costs$/}).getAttribute('value');
    await post(page, '/categories/create/', {name: 'Heating', transaction_type: 'EXPENSE', parent_category: living});
    await post(page, '/categories/create/', {name: 'Water', transaction_type: 'EXPENSE', parent_category: living});
    await page.goto('/categories/create/');
    const heating = await page.locator('#id_parent_category option').filter({hasText: /^Living costs > Heating$/}).getAttribute('value');
    await post(page, '/categories/create/', {name: 'Solar servicing', transaction_type: 'EXPENSE', parent_category: heating});
    await post(page, '/categories/create/', {name: 'Salary', transaction_type: 'INCOME'});
    await page.goto('/categories/');
    return {living, heating};
}
function branch(page, id) { return page.locator(`#category-toggle-${id}`); }
async function expectNodeInside(node) {
    await expect.poll(() => node.evaluate(element => {
        const bounds = element.getBoundingClientRect(), viewport = element.ownerSVGElement.getBoundingClientRect();
        return bounds.left >= viewport.left - 1 && bounds.right <= viewport.right + 1 &&
            bounds.top >= viewport.top - 1 && bounds.bottom <= viewport.bottom + 1;
    })).toBe(true);
}

for (const theme of ['light', 'dark']) {
    for (const width of [390, 1440]) {
        test(`category hierarchy and graph keep financial links unchanged (${width}, ${theme})`, async ({page}, info) => {
            await page.setViewportSize({width, height: 900});
            await page.addInitScript(value => localStorage.setItem('theme', value), theme);
            const ids = await seed(page, info);
            const posts = [];
            page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
            await expect(branch(page, ids.living)).toHaveAttribute('aria-expanded', 'false');
            await expect(page.locator(`#category-children-${ids.living}`)).toBeHidden();
            await expect(page.locator(`a[href^="/categories/${ids.living}/edit/"]`)).toBeVisible();
            await expect(page.locator('#filter-level')).toBeHidden();
            await page.locator('#filter-search').press('Tab');
            await expect(page.locator('#category-filters .filter-disclosure > summary')).toBeFocused();
            await page.keyboard.press('Space');
            await page.keyboard.press('Tab');
            await expect(page.locator('#filter-level')).toBeFocused();
            await page.keyboard.press('Home');
            await page.locator('#filter-search').fill('Solar');
            await page.locator('#filter-search').press('Enter');
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(branch(page, ids.living)).toHaveAttribute('aria-expanded', 'true');
            await expect(branch(page, ids.heating)).toHaveAttribute('aria-expanded', 'true');
            await expect(page.locator('#category-results')).not.toContainText('Water');
            await page.locator('#category-clear-filters').press('Enter');
            await expect(branch(page, ids.living)).toHaveAttribute('aria-expanded', 'false');
            await page.locator('#category-filters .filter-disclosure > summary').press('Enter');
            await page.locator('#category-view-tree').press('Enter');
            await expect(page).toHaveURL(/view=tree$/);
            const canvas = page.locator('[data-graph-canvas]');
            await expect(canvas).toBeVisible();
            await expect(canvas.getByRole('button')).toHaveCount(14); // Default categories plus the new hierarchy.
            expect(Number(await canvas.getAttribute('data-scale'))).toBeGreaterThanOrEqual(0.85);
            await page.screenshot({path: info.outputPath(`category-graph-initial-${width}-${theme}.png`), fullPage: true});
            await expect(canvas.locator('.category-graph-edge')).toHaveCount(3);
            await expect(page.locator('[data-category-graph-fallback]')).not.toHaveAttribute('open', '');
            await page.getByRole('button', {name: 'Fit graph', exact: true}).press('Tab');
            await expect(canvas).toBeFocused();
            await page.keyboard.press('Tab');
            await expect(canvas.getByRole('button', {name: 'Select category: Living costs', exact: true})).toBeFocused();
            await canvas.press('Home');
            const order = await canvas.locator('[data-node-id]').evaluateAll(nodes => nodes.map(node => node.dataset.nodeId));
            for (let index = 0; index < order.indexOf(ids.living); index++) await page.keyboard.press('ArrowDown');
            const living = canvas.getByRole('button', {name: 'Select category: Living costs', exact: true});
            await expect(living).toBeFocused();
            await expect(living).toHaveAttribute('aria-pressed', 'true');
            await page.keyboard.press('ArrowRight');
            const heating = canvas.getByRole('button', {name: 'Select category: Heating', exact: true});
            await expect(heating).toBeFocused();
            await page.keyboard.press('Space');
            await expect(page.locator('[data-graph-name]')).toHaveText('Heating');
            await expect(heating).toHaveAttribute('aria-pressed', 'true');
            const focusedStroke = await heating.locator('rect').evaluate(node => getComputedStyle(node).strokeWidth);
            expect(parseFloat(focusedStroke)).toBeGreaterThanOrEqual(3);
            const beforeZoom = Number(await canvas.getAttribute('data-scale'));
            await page.getByRole('button', {name: 'Zoom in', exact: true}).press('Enter');
            await expect.poll(async () => Number(await canvas.getAttribute('data-scale'))).toBeGreaterThan(beforeZoom);
            await page.getByRole('button', {name: 'Fit graph', exact: true}).press('Enter');
            const layer = canvas.locator('[data-graph-layer]');
            const beforePan = await layer.getAttribute('transform');
            const box = await canvas.boundingBox();
            await page.mouse.move(box.x + box.width - 20, box.y + box.height - 30);
            await page.mouse.down();
            await page.mouse.move(box.x + box.width - 100, box.y + box.height - 100, {steps: 8});
            await page.mouse.up();
            await expect(layer).not.toHaveAttribute('transform', beforePan);
            expect(posts).toEqual([]);
            await page.getByRole('button', {name: 'Fit graph', exact: true}).press('Enter');
            await canvas.press('Home');
            for (let index = 0; index < order.indexOf(ids.living); index++) await page.keyboard.press('ArrowDown');
            await page.keyboard.press('ArrowRight');
            const origin = `${requestPath(page.url())}#category-graph-node-${ids.heating}`;
            await page.locator('[data-graph-edit]').press('Enter');
            await expectContextualDestination(page, `/categories/${ids.heating}/edit/`, origin);
            await expect(page.locator('#id_name')).toHaveValue('Heating');
            await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
            await expect(canvas).toBeVisible();
            await expect(page.locator('[data-graph-name]')).toHaveText('Heating');
            await page.locator('#filter-search').fill('Solar');
            await page.locator('#filter-search').press('Enter');
            await expect(canvas.getByRole('button')).toHaveCount(3);
            await expect(page.locator('#category-results-status')).toHaveText('1 category');
            await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Solar' && !url.hash);
            const solar = canvas.getByRole('button', {name: 'Select category: Solar servicing', exact: true});
            await expect(solar).toHaveAttribute('aria-pressed', 'true');
            await expect(page.locator('[data-graph-name]')).toHaveText('Solar servicing');
            await expect(page.locator('#filter-search')).toBeFocused();
            await expectNodeInside(solar);
            const solarId = await solar.getAttribute('data-node-id');
            const editSolar = new URL(await page.locator('[data-graph-edit]').getAttribute('href'), page.url());
            expect(editSolar.pathname).toBe(`/categories/${solarId}/edit/`);
            expect(editSolar.searchParams.get('next')).toBe(`${requestPath(page.url())}#category-graph-node-${solarId}`);
            await page.screenshot({path: info.outputPath(`category-graph-search-${width}-${theme}.png`), fullPage: true});
            await page.locator('#category-clear-filters').press('Enter');
            await expect(page).toHaveURL(/view=tree$/);
            await expect(canvas.getByRole('button')).toHaveCount(14);
            await expect(page.locator('#filter-search')).toBeFocused();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({path: info.outputPath(`category-graph-${width}-${theme}.png`), fullPage: true});
        });
    }
}

for (const [theme, width] of [['light', 1440], ['dark', 390]]) {
    test(`graph search preserves explicit origins and reconciles applied results (${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const ids = await seed(page, info);
        const posts = [];
        page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
        const canvas = page.locator('[data-graph-canvas]');
        const solar = canvas.getByRole('button', {name: 'Select category: Solar servicing', exact: true});
        await page.goto('/categories/?view=tree&q=Solar');
        await expect(page.locator('[data-graph-name]')).toHaveText('Solar servicing');
        await expect(solar).toHaveAttribute('aria-pressed', 'true');
        await expectNodeInside(solar);
        const origin = `/categories/?view=tree&q=Solar#category-graph-node-${ids.heating}`;
        await page.goto('/categories/');
        await page.goto(origin);
        await expect(page.locator('[data-graph-name]')).toHaveText('Heating');
        await expect(page.locator('[data-graph-context]')).toBeVisible();
        const heating = canvas.getByRole('button', {name: 'Select category: Heating', exact: true});
        await expect(heating).toHaveAttribute('aria-pressed', 'true');
        await expectNodeInside(heating);
        await page.locator('[data-graph-edit]').press('Enter');
        await expectContextualDestination(page, `/categories/${ids.heating}/edit/`, origin);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => requestPath(url.href) + url.hash === origin);
        await expect(page.locator('[data-graph-name]')).toHaveText('Heating');
        const search = page.locator('#filter-search');
        await search.fill('ing');
        const top = await page.evaluate(() => scrollY);
        await search.press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'ing' && !url.hash);
        await expect(search).toBeFocused();
        await expect(page.locator('[data-graph-selected]')).toBeHidden();
        await expect(canvas.locator('[aria-pressed="true"]')).toHaveCount(0);
        const matches = await page.locator('#category-graph-data').evaluate(element =>
            JSON.parse(element.textContent).filter(node => !node.context));
        expect(matches.length).toBeGreaterThan(1);
        const first = canvas.locator(`[data-node-id="${matches[0].id}"]`);
        await expect(first).toHaveAttribute('tabindex', '0');
        await expectNodeInside(first);
        expect(Number(await canvas.getAttribute('data-scale'))).toBeGreaterThanOrEqual(0.85);
        expect(await page.evaluate(() => scrollY)).toBe(top);
        await search.fill('Solar');
        await search.press('Enter');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Solar' && !url.hash);
        await expect(page.locator('[data-graph-name]')).toHaveText('Solar servicing');
        await expect(solar).toHaveAttribute('aria-pressed', 'true');
        await expectNodeInside(solar);
        await expect(search).toBeFocused();
        expect(posts).toEqual([]);
    });
}

test('Portuguese mobile graph keeps translated actions and the selected parent origin', async ({page}, info) => {
    await page.setViewportSize({width: 390, height: 900});
    await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
    const ids = await seed(page, info);
    await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: info.project.use.baseURL}]);
    await page.goto('/categories/?view=tree');
    await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
    await expect(page.getByRole('heading', {name: 'Grafo de categorias', exact: true})).toBeVisible();
    await expect(page.locator('#category-view-tree')).toHaveText('Grafo');
    for (const name of ['Reduzir', 'Ampliar', 'Ajustar grafo']) {
        await expect(page.getByRole('button', {name, exact: true})).toBeVisible();
    }
    const posts = [];
    page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
    const search = page.locator('#filter-search');
    await search.fill('Solar');
    await search.press('Enter');
    const canvas = page.locator('[data-graph-canvas]');
    const solar = canvas.getByRole('button', {name: 'Selecionar categoria: Solar servicing', exact: true});
    await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Solar' && !url.hash);
    await expect(solar).toHaveAttribute('aria-pressed', 'true');
    await expectNodeInside(solar);
    await expect(search).toBeFocused();
    await solar.press('ArrowLeft');
    const heating = canvas.getByRole('button', {name: 'Selecionar categoria: Heating', exact: true});
    await expect(heating).toBeFocused();
    await expect(heating).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-graph-context]')).toHaveText('· Contexto da categoria pai');
    const origin = `${requestPath(page.url())}#category-graph-node-${ids.heating}`;
    await expect(page.locator('[data-graph-edit]')).toHaveText('Editar');
    await page.locator('[data-graph-edit]').press('Enter');
    await expectContextualDestination(page, `/categories/${ids.heating}/edit/`, origin);
    await expect(page.locator('#id_name')).toHaveValue('Heating');
    await page.getByRole('link', {name: 'Cancelar', exact: true}).press('Enter');
    await expect(page).toHaveURL(url => requestPath(url.href) + url.hash === origin);
    await expect(page.locator('[data-graph-name]')).toHaveText('Heating');
    await expect(heating).toHaveAttribute('aria-pressed', 'true');
    await expectNodeInside(heating);
    expect(posts).toEqual([]);
});

test('category graph supports real touch selection, pan and pinch', async ({browser}, info) => {
    const context = await browser.newContext({hasTouch: true, isMobile: true, viewport: {width: 390, height: 844}});
    const page = await context.newPage();
    try {
        await seed(page, info);
        await page.locator('#category-view-tree').tap();
        const canvas = page.locator('[data-graph-canvas]');
        await expect(canvas).toBeVisible();
        await canvas.getByRole('button', {name: 'Select category: Living costs', exact: true}).tap();
        await expect(page.locator('[data-graph-name]')).toHaveText('Living costs');
        await canvas.scrollIntoViewIfNeeded();
        const box = await canvas.boundingBox();
        const session = await context.newCDPSession(page);
        const x = box.x + box.width / 2, y = box.y + box.height / 2;
        const touch = async (type, points) => session.send('Input.dispatchTouchEvent', {type,
            touchPoints: points.map(([id, px, py]) => ({id, x: px, y: py, radiusX: 4, radiusY: 4}))});
        const original = await canvas.locator('[data-graph-layer]').getAttribute('transform');
        await touch('touchStart', [[1, x, y]]);
        await touch('touchMove', [[1, x + 50, y + 40]]);
        await touch('touchEnd', []);
        await expect(canvas.locator('[data-graph-layer]')).not.toHaveAttribute('transform', original);
        const scale = Number(await canvas.getAttribute('data-scale'));
        await touch('touchStart', [[1, x - 25, y], [2, x + 25, y]]);
        await touch('touchMove', [[1, x - 55, y], [2, x + 55, y]]);
        await touch('touchEnd', []);
        await expect.poll(async () => Number(await canvas.getAttribute('data-scale'))).toBeGreaterThan(scale);
        await page.getByRole('button', {name: 'Fit graph', exact: true}).tap();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath('category-graph-touch.png')});
    } finally { await context.close(); }
});

test('failed boosted navigation keeps the visible graph responsive', async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 800});
    await seed(page, info);
    await page.locator('#category-view-tree').press('Enter');
    const canvas = page.locator('[data-graph-canvas]');
    await expect(canvas).toBeVisible();
    await page.getByRole('button', {name: 'Fit graph', exact: true}).press('Enter');
    const layer = canvas.locator('[data-graph-layer]');
    const original = await layer.getAttribute('transform');
    await page.route(url => url.pathname === '/categories/create/' && url.searchParams.has('next'),
        route => route.fulfill({status: 500, contentType: 'text/html', body: 'Expected navigation failure'}));
    await Promise.all([
        page.waitForResponse(response => response.status() === 500 && new URL(response.url()).pathname === '/categories/create/'),
        page.getByRole('link', {name: 'New Category', exact: true}).press('Enter'),
    ]);
    await expect(page).toHaveURL(/view=tree$/);
    await expect(canvas).toBeVisible();
    await page.setViewportSize({width: 1440, height: 1050});
    await expect(layer).not.toHaveAttribute('transform', original);
});

test('graph bookmarks retain the complete native hierarchy without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    const page = await context.newPage();
    try {
        const ids = await seed(page, info);
        await page.locator('#category-view-tree').press('Enter');
        await expect(page).toHaveURL(/view=tree$/);
        await expect(page.locator('[data-category-graph]')).toBeHidden();
        await expect(page.locator('[data-category-graph-fallback]')).toHaveAttribute('open', '');
        await expect(page.locator(`[data-category-group="${ids.living}"] > div.absolute`)).toBeVisible();
        await branch(page, ids.living).press('Enter');
        await branch(page, ids.heating).press('Space');
        await expect(page.getByText('Solar servicing', {exact: true})).toBeVisible();
        await page.locator('#filter-search').fill('Solar');
        await page.getByRole('button', {name: 'Filter', exact: true}).press('Enter');
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await expect(page.getByText('Solar servicing', {exact: true})).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath('category-graph-native-mobile.png'), fullPage: true});
    } finally { await context.close(); }
});
