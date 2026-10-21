// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { test, expect } = require('@playwright/test');
const {openCatalogue} = require('../helpers/catalogue');
const { selectChoice } = require('../helpers/forms');

async function expectCardContrast(card) {
    const ratios = await card.evaluate(node => {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 1;
        const context = canvas.getContext('2d');
        const rgb = color => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = color;
            context.fillRect(0, 0, 1, 1);
            return [...context.getImageData(0, 0, 1, 1).data];
        };
        const luminance = channels => channels.slice(0, 3).map(value => {
            const unit = value / 255;
            return unit <= .04045 ? unit / 12.92 : ((unit + .055) / 1.055) ** 2.4;
        }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
        const style = getComputedStyle(node);
        const copy = node.querySelector('.lab-card-copy');
        const surface = rgb(getComputedStyle(copy).backgroundColor);
        // Arbitrary gradients may use an opaque text surface. Otherwise both
        // actual gradient stops must keep all essential card text readable.
        const backgrounds = surface[3] === 255 ? [surface] : ['--card-start', '--card-end']
            .map(name => rgb(style.getPropertyValue(name)));
        return [...copy.children].flatMap(text => backgrounds.map(background => {
            const foreground = rgb(getComputedStyle(text).color);
            const alpha = foreground[3] / 255;
            const ink = foreground.slice(0, 3).map((value, index) => value * alpha + background[index] * (1 - alpha));
            const light = [luminance(ink), luminance(background)].sort((a, b) => b - a);
            return (light[0] + .05) / (light[1] + .05);
        }));
    });
    expect(ratios.length).toBeGreaterThanOrEqual(3);
    ratios.forEach(ratio => expect(ratio, 'Card name, currency and bank/account text contrast').toBeGreaterThanOrEqual(4.5));
}

async function chooseExpense(page) {
    await page.locator('#lab-entry-type-expense').press('Space');
    await expect(page.locator('#lab-entry-type-expense')).toBeChecked();
}

async function fillDetails(page) {
    await page.locator('#lab-entry-title').fill('Payment keyboard example');
    await page.locator('#lab-entry-amount').fill('125.50');
    await page.locator('#lab-entry-date').fill('2026-10-17');
    await selectChoice(page.locator('#lab-entry-category'), '1001');
}

async function previewEntry(page) {
    await page.locator('#lab-transaction-form').getByRole('button', {name: 'Preview entry', exact: true}).press('Enter');
}

for (const theme of ['light', 'dark']) {
    test('catalogue payment buttons clear incompatible sources and retain compatible details (' + theme + ')', async ({page}, info) => {
        await page.setViewportSize({width: 390, height: 844});
        await openCatalogue(page, {hash: '#forms', theme, waitForFonts: true});
        const writes = [];
        page.on('request', request => {
            if (request.method() !== 'GET' || ['xhr', 'fetch'].includes(request.resourceType())) writes.push(request.url());
        });
        const storage = await page.evaluate(() => ({local: {...localStorage}, session: {...sessionStorage}}));
        const payment = page.locator('#lab-entry-payment');
        const account = page.locator('#lab-entry-account');
        const accountMethod = page.locator('#lab-entry-payment-account');
        const pix = page.locator('#lab-entry-payment-pix');
        const debit = page.locator('#lab-entry-payment-debit');
        const credit = page.locator('#lab-entry-payment-credit');
        const result = page.locator('#lab-entry-result');
        await expect(payment).toBeHidden();
        await chooseExpense(page);
        await fillDetails(page);
        await expect(payment.locator('input:checked')).toHaveCount(0);
        await accountMethod.press('Space');
        await expect(accountMethod.locator('..')).toHaveCSS('outline-style', 'solid');
        await expect(accountMethod.locator('..')).toHaveCSS('outline-width', '2px');
        await expect(accountMethod).toHaveCSS('outline-style', 'none');
        await selectChoice(account, '2002');
        await accountMethod.press('ArrowRight');
        await expect(pix).toBeChecked();
        await expect(account).toHaveValue('');
        await expect(account.locator('option[value="2002"]')).toBeDisabled();
        await selectChoice(account, '2001');
        await pix.press('ArrowLeft');
        await expect(accountMethod).toBeChecked();
        await expect(account).toHaveValue('2001');
        await accountMethod.press('ArrowRight');
        await expect(account).toHaveValue('2001');
        await previewEntry(page);
        await expect(result).toContainText('Pix');
        await expect(result).toContainText('Everyday bank');
        await pix.press('ArrowRight');
        await expect(debit).toBeChecked();
        await expect(page.locator('#lab-entry-account-search')).toBeHidden();
        await expect(page.locator('#lab-entry-debit input:checked')).toHaveCount(0);
        await previewEntry(page);
        await expect(page.locator('#lab-entry-debit-4001')).toBeFocused();
        await page.locator('#lab-entry-debit-4001').press('Space');
        await expectCardContrast(page.locator('[data-card-id="4001"]'));
        await debit.press('ArrowRight');
        await expect(credit).toBeChecked();
        await expect(page.locator('#lab-entry-debit-4001')).not.toBeChecked();
        await expect(page.locator('#lab-entry-debit-4001')).toBeDisabled();
        await previewEntry(page);
        await expect(page.locator('#lab-entry-credit-3001')).toBeFocused();
        await page.locator('#lab-entry-credit-3001').press('Space');
        await page.locator('#lab-entry-credit-3001').press('ArrowRight');
        await expect(page.locator('#lab-entry-credit-3002')).toBeChecked();
        for (const card of await page.locator('#lab-entry-credit [data-card-id]').all()) await expectCardContrast(card);
        await previewEntry(page);
        await expect(result).toContainText('Credit card');
        await expect(result).toContainText('Travel');
        await expect(result).toContainText('BRL 125.50');
        await page.locator('#lab-entry-type-expense').press('ArrowRight');
        await expect(page.locator('#lab-entry-type-income')).toBeChecked();
        await expect(credit).toBeDisabled();
        await expect(debit).toBeDisabled();
        await expect(payment.locator('input:checked')).toHaveCount(0);
        await expect(page.locator('#lab-entry-credit-3002')).not.toBeChecked();
        await expect(page.locator('#lab-entry-category')).toHaveValue('');
        await expect(page.locator('#lab-entry-title')).toHaveValue('Payment keyboard example');
        await expect(page.locator('#lab-entry-amount')).toHaveValue('125.50');
        await expect(page.locator('#lab-entry-date')).toHaveValue('2026-10-17');
        await selectChoice(page.locator('#lab-entry-category'), '1004');
        await accountMethod.press('Space');
        await selectChoice(account, '2001');
        await previewEntry(page);
        await expect(result).toHaveAttribute('data-lab-state', 'created');
        await expect(page.locator('#lab-entry-account-search')).toHaveAccessibleName(/Received into/);
        await page.locator('#lab-entry-type-income').press('ArrowLeft');
        await expect(credit).toBeEnabled();
        await expect(credit).not.toBeChecked();
        await expect(account).toHaveValue('2001');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(await page.evaluate(() => ({local: {...localStorage}, session: {...sessionStorage}}))).toEqual(storage);
        expect(writes).toEqual([]);
        await page.locator('#lab-transaction-form').screenshot({path: info.outputPath('payment-buttons-' + theme + '.png')});
    });

    test('catalogue card editor validates independently and retains edited colors and billing data (' + theme + ')', async ({page}, info) => {
        await page.setViewportSize({width: theme === 'light' ? 1440 : 390, height: 900});
        await openCatalogue(page, {hash: '#forms', theme, waitForFonts: true});
        const writes = [];
        page.on('request', request => {
            if (request.method() !== 'GET' || ['xhr', 'fetch'].includes(request.resourceType())) writes.push(request.url());
        });
        await chooseExpense(page);
        await page.locator('#lab-entry-payment-credit').press('Space');
        const editor = page.locator('#lab-card-editor');
        await editor.locator(':scope > summary').press('Enter');
        const save = page.locator('[data-lab-card-submit]');
        await expect(page.locator('#lab-card-color')).toHaveValue('#253330');
        await expect(page.locator('.lab-card-presets input[type="radio"]')).toHaveCount(6);
        await expect(page.locator('#lab-card-gradient')).toBeVisible();
        await expect(page.locator('#lab-card-gradient')).toBeEnabled();
        await expect(page.locator('#lab-card-account-search')).toBeHidden();
        await expect(page.locator('#lab-card-account')).toBeDisabled();
        await save.press('Enter');
        await expect(page.locator('#lab-card-error')).toBeVisible();
        await expect(page.locator('#lab-card-bank-search')).toBeFocused();
        await selectChoice(page.locator('#lab-card-bank'), 'bank2');
        await expect(page.locator('#lab-card-account')).toHaveValue('');
        await expect(page.locator('#lab-card-account option[value="2001"]')).toBeDisabled();
        await selectChoice(page.locator('#lab-card-account'), '2003');
        await page.locator('#lab-card-name').fill('Weekend <card>');
        const cycle = editor.locator('details.lab-card-cycle');
        if (!await cycle.evaluate(node => node.open)) await cycle.locator('summary').press('Enter');
        await page.locator('#lab-card-closing').fill('32');
        await page.locator('#lab-card-due').fill('10');
        await cycle.locator('summary').press('Enter');
        await expect(cycle).not.toHaveAttribute('open');
        await save.press('Enter');
        await expect(cycle).toHaveAttribute('open', '');
        await expect(page.locator('#lab-card-closing')).toBeFocused();
        await expect(page.locator('#lab-card-error')).toBeVisible();
        await page.locator('#lab-card-closing').fill('24');
        await page.locator('#lab-card-type').selectOption('VIRTUAL');
        await page.locator('#lab-card-manual').fill('2026-10-01');
        await page.locator('#lab-card-preset-black').press('Space');
        for (let step = 0; step < 5; step += 1) await page.keyboard.press('ArrowRight');
        await expect(page.locator('#lab-card-preset-gold')).toBeChecked();
        await expect(page.locator('#lab-card-color')).toHaveValue('#c6a173');
        await expectCardContrast(page.locator('#lab-card-preview'));
        await save.press('Enter');
        const created = page.locator('#lab-entry-credit [data-card-id]').filter({has: page.locator('strong').filter({hasText: 'Weekend <card>'})});
        await expect(created).toHaveCount(1);
        await expect(created.locator('input')).not.toBeChecked();
        await expect(created).toHaveAttribute('data-card-color', /^#c6a173$/i);
        await expectCardContrast(created);
        const identifier = await created.getAttribute('data-card-id');
        await page.locator('[data-lab-edit-card="' + identifier + '"]').press('Enter');
        await expect(editor).toHaveAttribute('open', '');
        await expect(page.locator('#lab-card-bank')).toHaveValue('bank2');
        await expect(page.locator('#lab-card-account')).toHaveValue('2003');
        await expect(page.locator('#lab-card-type')).toHaveValue('VIRTUAL');
        await expect(page.locator('#lab-card-manual')).toHaveValue('2026-10-01');
        await page.locator('#lab-card-color').fill('#000000');
        await page.locator('#lab-card-gradient').press('Space');
        await expect(page.locator('#lab-card-end')).toBeVisible();
        await page.locator('#lab-card-end').fill('#ffffff');
        await page.locator('#lab-card-angle').selectOption('90');
        await expectCardContrast(page.locator('#lab-card-preview'));
        await save.press('Enter');
        await expect(created).toHaveAttribute('data-card-gradient', 'true');
        await expect(created).toHaveAttribute('data-card-protected', 'true');
        await expectCardContrast(created);
        await page.locator('[data-lab-edit-card="' + identifier + '"]').press('Enter');
        await expect(page.locator('#lab-card-gradient')).toBeChecked();
        await expect(page.locator('#lab-card-color')).toHaveValue('#000000');
        await expect(page.locator('#lab-card-end')).toHaveValue('#ffffff');
        await expect(page.locator('#lab-card-angle')).toHaveValue('90');
        await expect(page.locator('#lab-card-closing')).toHaveValue('24');
        await expect(page.locator('#lab-card-due')).toHaveValue('10');
        await expect(page.locator('#lab-card-name')).toHaveValue('Weekend <card>');
        await page.locator('[data-lab-card-cancel]').press('Enter');
        await expect(editor).not.toHaveAttribute('open');
        await expect(editor.locator(':scope > summary')).toBeFocused();
        await page.locator('[data-lab-reset]').press('Enter');
        await chooseExpense(page);
        await page.locator('#lab-entry-payment-credit').press('Space');
        await expect(created).toHaveCount(1);
        await expect(created.locator('input')).not.toBeChecked();
        await editor.locator(':scope > summary').press('Enter');
        await expect(page.locator('#lab-card-color')).toHaveValue('#253330');
        await expect(page.locator('#lab-card-gradient')).not.toBeChecked();
        await expect(page.locator('#lab-card-gradient')).toBeEnabled();
        await expect(page.locator('#lab-card-gradient')).toBeVisible();
        expect(writes).toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await editor.screenshot({path: info.outputPath('card-editor-' + theme + '.png')});
    });
}

test('catalogue type, payment and card labels remain deliberate touch targets in both themes', async ({browser}) => {
    for (const theme of ['light', 'dark']) {
        const context = await browser.newContext({hasTouch: true, isMobile: true, viewport: {width: 390, height: 844}});
        try {
            const page = await context.newPage();
            await openCatalogue(page, {hash: '#forms', theme, waitForFonts: true});
            await page.locator('label').filter({has: page.locator('#lab-entry-type-expense')}).tap();
            await expect(page.locator('#lab-entry-type-expense')).toBeChecked();
            await page.locator('label').filter({has: page.locator('#lab-entry-payment-credit')}).tap();
            await expect(page.locator('#lab-entry-credit input[name="credit_card"]:checked')).toHaveCount(0);
            const card = page.locator('[data-card-id="3002"]');
            await card.tap();
            await expect(page.locator('#lab-entry-credit-3002')).toBeChecked();
            for (const label of await page.locator('#lab-entry-type label, #lab-entry-payment label, #lab-entry-credit label[data-card-id]').all()) {
                const target = await label.boundingBox();
                expect(target.width).toBeGreaterThanOrEqual(44);
                expect(target.height).toBeGreaterThanOrEqual(44);
            }
            await expectCardContrast(card);
            await page.locator('label').filter({has: page.locator('#lab-entry-type-income')}).tap();
            await expect(page.locator('#lab-entry-payment-credit')).toBeDisabled();
            await expect(page.locator('#lab-entry-credit-3002')).not.toBeChecked();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        } finally { await context.close(); }
    }
});

test('catalogue native card creation submits only the separate read-only editor GET without JavaScript', async ({browser}) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    try {
        const page = await context.newPage();
        await openCatalogue(page, {hash: '#forms', theme: 'light', waitForFonts: true});
        await page.locator('#lab-entry-title').fill('Unsubmitted transaction');
        await page.locator('#lab-card-editor > summary').press('Enter');
        await expect(page.locator('#lab-card-bank-search')).toHaveCount(0);
        await page.locator('#lab-card-bank').selectOption('bank2');
        await page.locator('#lab-card-account').selectOption('2003');
        await page.locator('#lab-card-name').fill('Native illustrative card');
        await page.locator('#lab-card-editor details.lab-card-cycle > summary').press('Enter');
        await page.locator('#lab-card-closing').fill('24');
        await page.locator('#lab-card-due').fill('10');
        const submitted = page.waitForRequest(request => request.isNavigationRequest()
            && new URL(request.url()).searchParams.get('card_name') === 'Native illustrative card');
        await page.locator('[data-lab-card-submit]').press('Enter');
        expect((await submitted).method()).toBe('GET');
        await expect(page).toHaveURL(url => url.searchParams.get('bank') === 'bank2'
            && url.searchParams.get('card_account') === '2003' && url.searchParams.get('closing_day') === '24'
            && !url.searchParams.has('title') && !url.searchParams.has('type') && !url.searchParams.has('amount')
            && url.hash === '#forms');
        await expect(page.locator('#lab-entry-credit [data-card-id]')).toHaveCount(2);
    } finally { await context.close(); }
});
