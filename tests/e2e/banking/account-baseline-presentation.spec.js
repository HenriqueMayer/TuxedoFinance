// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {
        form: {csrfmiddlewaretoken: csrf, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0,
    });
    expect(saved.status()).toBe(302);
}

async function seed(page, info) {
    const username = `account-baseline-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Baseline-E2E-2026!', password2: 'Baseline-E2E-2026!',
    });
    await post(page, '/banking/create/', {name: 'Local bank'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {
        bank, name: 'Everyday', currency: 'BRL', opening_balance: '1000',
        opening_date: '2026-01-01', pix_enabled: 'on', planning_enabled: 'on',
        reserved_amount: '0',
    });
    await page.goto('/banking/debit-cards/create/');
    const account = await page.locator('#id_account option').last().getAttribute('value');
    return {bank, account};
}

for (const theme of ['light', 'dark']) {
for (const width of [390, 1440]) {
    test(`account baseline and optional planning stay clear (${width}, ${theme})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 850});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const {bank, account} = await seed(page, info);
        const url = `/banking/accounts/${account}/edit/`;
        await page.goto(url);
        await expect(page.locator('#id_opening_balance')).toHaveValue('1000.00');
        await expect(page.getByText('Balance when tracking starts', {exact: false}).first()).toBeVisible();
        await expect(page.locator('#id_opening_date')).toBeVisible();
        await expect(page.getByText('Enter the balance you already had when you started tracking this account, at the start of the chosen date and before its movements.', {exact: true})).toBeVisible();
        const settings = page.locator('#account-planning-adjustments');
        const summary = settings.locator(':scope > summary');
        await expect(settings).not.toHaveAttribute('open', '');
        await expect(page.locator('#id_reserved_amount')).not.toBeVisible();
        await summary.press('Enter');
        await expect(settings).toHaveAttribute('open', '');
        await summary.press('Tab');
        await expect(page.locator('#id_planning_enabled')).toBeFocused();
        await expect(page.locator('#id_planning_enabled')).toBeChecked();
        await page.locator('#id_reserved_amount').fill('125.50');
        await summary.press('Space');
        await expect(settings).not.toHaveAttribute('open', '');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${bank}/$`));
        await page.goto(url);
        await expect(settings).toHaveAttribute('open', '');
        await expect(page.locator('#id_reserved_amount')).toHaveValue('125.50');
        await page.locator('#id_reserved_amount').fill('-1');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(settings).toHaveAttribute('open', '');
        await expect(page.locator('#id_reserved_amount')).toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('#id_reserved_amount')).toHaveValue('-1');
        await page.locator('#id_reserved_amount').fill('0');
        await page.locator('#id_planning_enabled').press('Space');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await page.goto(url);
        await expect(settings).toHaveAttribute('open', '');
        await expect(page.locator('#id_planning_enabled')).not.toBeChecked();
        await expect(page.locator('#id_opening_balance')).toHaveValue('1000.00');
        await page.getByRole('button', {name: 'Save', exact: true}).scrollIntoViewIfNeeded();
        await expect(page.getByRole('button', {name: 'Save', exact: true})).toBeInViewport();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`account-baseline-${width}-${theme}.png`), fullPage: true});
    });
}
}

test('optional planning works with native keyboard and POST without JavaScript', async ({browser, baseURL}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL, viewport: {width: 390, height: 850}});
    const page = await context.newPage();
    try {
        const {bank, account} = await seed(page, info);
        const url = `/banking/accounts/${account}/edit/`;
        await page.goto(url);
        const settings = page.locator('#account-planning-adjustments');
        const summary = settings.locator(':scope > summary');
        await summary.press('Enter');
        await page.locator('#id_reserved_amount').fill('50.25');
        await summary.press('Space');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${bank}/$`));
        await page.goto(url);
        await expect(settings).toHaveAttribute('open', '');
        await expect(page.locator('#id_reserved_amount')).toHaveValue('50.25');
        await expect(page.locator('#id_planning_enabled')).toBeChecked();
    } finally {
        await context.close();
    }
});
