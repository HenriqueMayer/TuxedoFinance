const {projectRoot} = require('../helpers/paths');
// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {test, expect} = require('@playwright/test');

// Read-only provenance stays available while new imports are paused. Fixtures
// may use ORM only inside the official runner's owned disposable installation;
// never enable the import feature or seed a developer/Docker database.
const isolated = path.basename(process.env.TUXEDO_DATA_DIR || '').startsWith('tuxedo-e2e-');

async function seed(page, info) {
    const username = `history-audit-${info.workerIndex}-${Date.now()}`;
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const signup = await page.request.post('/accounts/signup/', {
        form: {csrfmiddlewaretoken: csrf, username, email: `${username}@example.test`,
            password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(signup.status(), await signup.text()).toBe(302);
    const script = `
from pathlib import Path
import os
from django.contrib.auth import get_user_model
from banking.models import Bank, BankAccount
from ingestion.models import ImportBatch
assert Path(os.environ['TUXEDO_DATA_DIR']).name.startswith('tuxedo-e2e-')
user = get_user_model().objects.get(username=${JSON.stringify(username)})
bank = Bank.objects.create(user=user, name='History institution')
account = BankAccount.objects.create(user=user, bank=bank, name='Provenance account', currency='BRL')
for index in range(24):
    ImportBatch.objects.create(user=user, account=account, file_name=f'Audit {"House" if index < 12 else "Office"} {index:02}.csv', file_hash=f'{index:064x}', file_format='CSV', raw_text='', status='CONFIRMED' if index % 2 else 'UNDONE')
ImportBatch.objects.create(user=user, account=account, file_name='Unconfirmed evidence.csv', file_hash='a' * 64, file_format='CSV', raw_text='', status='STAGED')
`;
    execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', script], {
        cwd: projectRoot, encoding: 'utf8', env: process.env,
    });
}

for (const theme of ['light', 'dark']) {
    test(`import history keeps the editorial rail, caret, scroll and browser history (${theme})`, async ({page}, info) => {
        test.skip(!isolated, 'Run with npm run test:e2e to own the disposable provenance fixture.');
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width: 390, height: 740});
        await seed(page, info);
        await page.goto('/imports/history/');
        const form = page.locator('#import-history-filters');
        const search = page.locator('#import-history-query');
        const results = page.locator('#import-history-results');
        await expect(form).toHaveClass(/\bconsultation-bar\b/);
        await expect(form.locator('.consultation-search')).toHaveCount(1);
        await expect(form.locator('[data-live-submit]')).toBeHidden();
        await expect(search).toHaveCSS('border-radius', '8px');
        await expect(search).toHaveCSS('min-height', '44px');
        await expect(results.locator('article')).toHaveCount(20);
        await expect(results).not.toContainText('Unconfirmed evidence');
        const initialBounds = await search.boundingBox();
        await search.focus();
        await page.keyboard.press('Tab');
        await page.keyboard.press('Shift+Tab');
        await expect(search).toBeFocused();
        expect(await search.evaluate(element => element.matches(':focus-visible'))).toBe(true);
        const before = await page.evaluate(() => {
            window.importSearchControl = document.getElementById('import-history-query');
            window.scrollTo(0, 40);
            return {top: scrollY, history: history.length};
        });
        expect(before.top).toBeGreaterThan(0);
        await page.keyboard.type('House', {delay: 20});
        await expect(page).toHaveURL(/\/imports\/history\/\?q=House$/);
        await expect(results.locator('article')).toHaveCount(12);
        await expect(search).toBeFocused();
        expect(await page.evaluate(() => history.length)).toBe(before.history + 1);
        await expect.poll(() => page.evaluate(() => scrollY)).toBe(before.top);
        const activeBounds = await search.boundingBox();
        expect(activeBounds.x).toBe(initialBounds.x);
        expect(activeBounds.width).toBe(initialBounds.width);
        await search.press('ArrowLeft');
        await search.press('ArrowLeft');
        await page.keyboard.type('s');
        await expect(page).toHaveURL(/q=Housse$/);
        expect(await search.evaluate(element => element.selectionStart)).toBe(4);
        await page.keyboard.press('Backspace');
        await expect(page).toHaveURL(/q=House$/);
        expect(await search.evaluate(element => element.selectionStart)).toBe(3);
        expect(await page.evaluate(() => window.importSearchControl === document.getElementById('import-history-query'))).toBe(true);
        await page.goBack();
        await expect(page).toHaveURL(/\/imports\/history\/$/);
        await expect(search).toHaveValue('');
        await expect(results.locator('article')).toHaveCount(20);
        await page.goForward();
        await expect(search).toHaveValue('House');
        await expect(results.locator('article')).toHaveCount(12);
        const clear = form.getByRole('link', {name: 'Clear filters', exact: true});
        await clear.focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/imports\/history\/$/);
        await expect(search).toHaveValue('');
        await expect(search).toBeFocused();
        await expect(results.locator('article')).toHaveCount(20);
        await expect(clear).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`import-history-${theme}.png`), fullPage: true});
    });

    if (theme === 'light') test('import history retains a native GET and reset without JavaScript', async ({browser}, info) => {
        test.skip(!isolated, 'Run with npm run test:e2e to own the disposable provenance fixture.');
        const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 740}});
        const page = await context.newPage();
        try {
            await seed(page, info);
            await page.goto('/imports/history/');
            const form = page.locator('#import-history-filters');
            const search = page.locator('#import-history-query');
            await expect(form.locator('[data-live-submit]')).toBeVisible();
            await search.focus();
            await page.keyboard.type('House');
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(/q=House$/);
            await expect(search).toHaveValue('House');
            await expect(page.locator('#import-history-results article')).toHaveCount(12);
            await form.getByRole('link', {name: 'Clear filters', exact: true}).press('Enter');
            await expect(page).toHaveURL(/\/imports\/history\/$/);
            await expect(search).toHaveValue('');
            await expect(page.locator('#import-history-results article')).toHaveCount(20);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        } finally {
            await context.close();
        }
    });
}
