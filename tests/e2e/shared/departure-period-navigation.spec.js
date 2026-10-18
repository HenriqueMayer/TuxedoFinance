// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `departure-period-${info.workerIndex}-${Date.now()}`;
    const result = await page.request.post('/accounts/signup/', {
        form: {csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(result.status(), await result.text()).toBe(302);
    // Consume signup's one-off message before measuring a persistent control.
    await page.request.get('/dashboard/');
}
async function railPositions(root) {
    return root.locator('.period-navigation-rail > :first-child, .period-navigation-rail > :last-child')
        .evaluateAll(nodes => nodes.map(node => {
            const box = node.getBoundingClientRect();
            return {x: box.x, y: box.y, width: box.width, height: box.height};
        }));
}
function sameArrows(before, after) {
    expect(after).toHaveLength(2);
    after.forEach((box, index) => {
        expect(Math.abs(box.x - before[index].x)).toBeLessThan(1);
        expect(Math.abs(box.y - before[index].y)).toBeLessThan(1);
        expect(box.width).toBe(44);
        expect(box.height).toBe(44);
    });
}

for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
    test(`departure dialog supports keyboard, Back and Forward (${theme}, ${width})`, async ({page}, info) => {
        await signup(page, info);
        await page.setViewportSize({width, height: 844});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.goto('/transactions/');
        await page.getByRole('link', {name: 'New transaction', exact: true}).first().press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/transactions/create/');
        const formUrl = page.url();
        await page.locator('#id_title').fill('Preserve this draft');
        const cancel = page.getByRole('link', {name: 'Cancel', exact: true});
        const openedTab = page.context().waitForEvent('page');
        await cancel.click({modifiers: ['ControlOrMeta']});
        const other = await openedTab;
        await other.waitForURL(/\/transactions\/$/);
        await other.close();
        await expect(page.locator('#departure-confirm')).toBeHidden();
        await expect(page.locator('#id_title')).toHaveValue('Preserve this draft');
        await cancel.press('Enter');
        const dialog = page.getByRole('dialog', {name: 'Leave this page?', exact: true});
        const stay = dialog.getByRole('button', {name: 'Keep editing', exact: true});
        const leave = dialog.getByRole('button', {name: 'Leave page', exact: true});
        await expect(dialog).toBeVisible();
        await expect(stay).toBeFocused();
        await page.keyboard.press('Shift+Tab'); await expect(leave).toBeFocused();
        await page.keyboard.press('Tab'); await expect(stay).toBeFocused();
        await page.keyboard.press('Tab'); await expect(leave).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(dialog).toBeHidden();
        await expect(cancel).toBeFocused();
        await expect(page.locator('#id_title')).toHaveValue('Preserve this draft');
        await expect(page).toHaveURL(formUrl);
        await cancel.press('Enter');
        await expect(stay).toBeFocused();
        const box = await dialog.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(8);
        expect(box.x + box.width).toBeLessThanOrEqual(width - 8);
        await page.screenshot({path: info.outputPath(`departure-${theme}-${width}.png`), animations: 'disabled'});
        await leave.press('Enter');
        await expect(page).toHaveURL(/\/transactions\/$/);
        await expect(page.getByRole('heading', {name: 'Transactions', exact: true})).toBeVisible();
        await page.goBack();
        await expect(page).toHaveURL(formUrl);
        await expect(page.locator('#id_title')).toHaveValue('Preserve this draft');
        // Cancel belongs to a native POST form's hx-boost=false subtree.
        // Its accepted departure creates another document, so browser Forward
        // owns beforeunload and cannot display an application-styled dialog.
        const nativeWarning = page.waitForEvent('dialog');
        // A canceled traversal has no load event; use the native history API
        // without waiting for a document which deliberately will not load.
        await page.evaluate(() => { setTimeout(() => history.forward(), 0); });
        const warning = await nativeWarning;
        expect(warning.type()).toBe('beforeunload');
        await warning.dismiss();
        await expect(page).toHaveURL(formUrl);
        await expect(page.locator('#id_title')).toHaveValue('Preserve this draft');
        const acceptedWarning = page.waitForEvent('dialog');
        await page.evaluate(() => { setTimeout(() => history.forward(), 0); });
        const accepted = await acceptedWarning;
        expect(accepted.type()).toBe('beforeunload');
        await accepted.accept();
        await expect(page.getByRole('heading', {name: 'Transactions', exact: true})).toBeVisible();
        await expect(dialog).toBeHidden();

        // A workspace link outside that native form uses HTMX. Both history
        // directions stay in this document and therefore use the styled dialog.
        await page.getByRole('link', {name: 'New transaction', exact: true}).first().press('Enter');
        await expect(page).toHaveURL(url => url.pathname === '/transactions/create/');
        const sameDocumentUrl = page.url();
        await page.locator('#id_title').fill('Same document draft');
        await page.getByRole('navigation', {name: 'Transaction sections', exact: true})
            .getByRole('link', {name: 'Transactions', exact: true}).press('Enter');
        await leave.press('Enter');
        await expect(page.getByRole('heading', {name: 'Transactions', exact: true})).toBeVisible();
        await page.goBack();
        await expect(page.locator('#id_title')).toHaveValue('Same document draft');
        await page.goForward();
        await expect(dialog).toBeVisible();
        await stay.press('Enter');
        await expect(page).toHaveURL(sameDocumentUrl);
        await expect(page.locator('#id_title')).toHaveValue('Same document draft');
        await page.goForward();
        await leave.press('Enter');
        await expect(page.getByRole('heading', {name: 'Transactions', exact: true})).toBeVisible();
        await expect(dialog).toBeHidden();
    });

    test(`period arrows keep their positions when reset appears (${theme}, ${width})`, async ({page}, info) => {
        await signup(page, info);
        await page.setViewportSize({width, height: 844});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.goto('/dashboard/');
        let navigation = page.locator('[data-period-navigation]').first();
        await navigation.scrollIntoViewIfNeeded();
        let before = await railPositions(navigation);
        await navigation.getByRole('link', {name: 'Next month', exact: true}).press('Enter');
        await expect(navigation.getByRole('link', {name: 'Back to this month', exact: true})).toBeVisible();
        await navigation.scrollIntoViewIfNeeded();
        sameArrows(before, await railPositions(navigation));
        await navigation.getByRole('link', {name: 'Previous month', exact: true}).press('Enter');
        await expect(navigation.getByRole('link', {name: 'Back to this month', exact: true})).toHaveCount(0);
        await navigation.scrollIntoViewIfNeeded();
        sameArrows(before, await railPositions(navigation));
        await page.goto('/dashboard/reports/');
        navigation = page.locator('[data-period-navigation]').first();
        await navigation.scrollIntoViewIfNeeded();
        before = await railPositions(navigation);
        await navigation.getByRole('link', {name: 'Next window', exact: true}).press('Enter');
        await expect(navigation.getByRole('link', {name: 'Back to today', exact: true})).toBeVisible();
        await navigation.scrollIntoViewIfNeeded();
        sameArrows(before, await railPositions(navigation));
        await page.goto('/investments/charts/');
        navigation = page.locator('[data-period-navigation]').first();
        await navigation.scrollIntoViewIfNeeded();
        before = await railPositions(navigation);
        await navigation.getByRole('link', {name: 'Next window', exact: true}).press('Enter');
        await expect(navigation.getByRole('link', {name: 'Back to today', exact: true})).toBeVisible();
        await navigation.scrollIntoViewIfNeeded();
        sameArrows(before, await railPositions(navigation));
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`period-${theme}-${width}.png`)});
    });
}

for (const theme of ['light', 'dark']) {
    test(`contextual Cancel protects edits and retains the destination fragment (${theme})`, async ({page}, info) => {
        await signup(page, info);
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const destination = '/transactions/?q=contextual#transaction-results';
        await page.goto(`/transactions/create/?next=${encodeURIComponent(destination)}`);
        const formUrl = page.url();
        await page.locator('#id_title').fill('Draft with a contextual return');
        const cancel = page.getByRole('link', {name: 'Cancel', exact: true});
        await expect(cancel).toHaveAttribute('href', destination);
        await cancel.press('Enter');
        await expect(page.locator('[data-departure-stay]')).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(formUrl);
        await expect(cancel).toBeFocused();
        await expect(page.locator('#id_title')).toHaveValue('Draft with a contextual return');
        await cancel.press('Enter');
        await page.locator('[data-departure-leave]').press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === destination);
        await expect(page.getByRole('heading', {name: 'Transactions', exact: true})).toBeVisible();
    });
}

test('period arrows retain native GET links without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    const page = await context.newPage();
    try {
        await signup(page, info);
        await page.goto('/dashboard/');
        const navigation = page.locator('[data-period-navigation]').first();
        await navigation.scrollIntoViewIfNeeded();
        const before = await railPositions(navigation);
        await navigation.getByRole('link', {name: 'Next month', exact: true}).press('Enter');
        await expect(navigation.getByRole('link', {name: 'Back to this month', exact: true})).toBeVisible();
        await navigation.scrollIntoViewIfNeeded();
        sameArrows(before, await railPositions(navigation));
        await navigation.getByRole('link', {name: 'Back to this month', exact: true}).press('Enter');
        await expect(page).toHaveURL(/\/dashboard\/$/);
        await expect(page.locator('#departure-confirm')).toBeHidden();
    } finally { await context.close(); }
});
