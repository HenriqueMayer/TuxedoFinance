// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');

async function post(page, path, fields) {
    const source = await page.request.get(path);
    const csrf = (await source.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const response = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: source.url()}, maxRedirects: 0});
    expect(response.status()).toBe(302);
}

async function fixture(page, info) {
    const username = `color-picker-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-Color-2026!', password2: 'Tuxedo-Color-2026!'});
}

async function assertCompact(page) {
    expect(await page.locator('[data-color-picker] input[type="color"]').evaluateAll(inputs => inputs.every(input => {
        const bounds = input.getBoundingClientRect();
        return bounds.width >= 44 && bounds.width <= 52 && bounds.height >= 44;
    }))).toBe(true);
    for (const owner of await page.locator('[data-color-picker]:has([data-color-presets]:visible)').all()) {
        const palette = await owner.locator('[data-color-presets]').boundingBox();
        const custom = await owner.locator('.color-picker-custom').boundingBox();
        expect(Math.abs(palette.y + palette.height / 2 - custom.y - custom.height / 2)).toBeLessThan(2);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
    test(`shared bank and card colors preserve custom HEX, keyboard and compact controls (${theme}, ${width})`, async ({page}, info) => {
        await page.setViewportSize({width, height: 900});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await fixture(page, info);
        await page.goto('/banking/create/');
        const presets = page.locator('[data-color-presets] button');
        await expect(presets).toHaveCount(6);
        const black = page.getByRole('button', {name: 'Black', exact: true});
        await black.focus();
        await page.keyboard.press('Space');
        await expect(black).toHaveAttribute('aria-pressed', 'true');
        await expect(page.locator('#id_color')).toHaveValue('#111111');
        await page.keyboard.press('Tab');
        const blueGray = page.getByRole('button', {name: 'Blue gray', exact: true});
        await expect(blueGray).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(blueGray).toHaveAttribute('aria-pressed', 'true');
        await expect(black).toHaveAttribute('aria-pressed', 'false');
        await page.locator('#id_color').fill('#abcdef');
        await expect(page.locator('[data-color-presets] button[aria-pressed="true"]')).toHaveCount(0);
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_name-error-1')).toBeVisible();
        await expect(page.locator('#id_color')).toHaveValue('#abcdef');
        await assertCompact(page);
        await page.locator('[data-color-picker]').screenshot({path: info.outputPath(`bank-color-${theme}-${width}.png`)});
        await page.locator('#id_name').fill('Palette bank');
        // A native color picker cannot produce malformed HEX. Retain a forged
        // POST as readable text so the user can correct its actual value.
        await page.locator('#id_color').evaluate(input => { input.type = 'text'; });
        await page.locator('#id_color').fill('#12ZZ89');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page.locator('#id_color')).toHaveAttribute('type', 'text');
        await expect(page.locator('#id_color')).toHaveValue('#12ZZ89');
        await expect(page.locator('#id_color-error-1')).toBeVisible();
        await page.locator('#id_color').focus();
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type('#abcdef');
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await page.goto('/banking/accounts/create/');
        const bank = await page.locator('#id_bank option').last().getAttribute('value');
        await post(page, '/banking/accounts/create/', {bank, name: 'Palette account', currency: 'BRL', opening_balance: '0'});
        await page.goto('/banking/debit-cards/create/');
        const account = await page.locator('#id_account option').last().getAttribute('value');
        await selectChoice(page.locator('#id_account'), account);
        await page.locator('#id_name').fill('Custom card');
        await page.getByRole('button', {name: 'Purple', exact: true}).press('Space');
        await expect(page.locator('[data-card-appearance-preview]')).toHaveCSS('--card-start', '#820AD1');
        await page.locator('#id_color').fill('#aabbcc');
        await page.locator('#id_use_gradient').check();
        await page.locator('#id_gradient_end').fill('#112233');
        await page.locator('[data-card-angle-dial]').press('Home');
        await page.locator('[data-card-angle-dial]').press('Shift+ArrowRight');
        await expect(page.locator('#id_gradient_angle')).toHaveValue('15');
        await assertCompact(page);
        await page.locator('.card-appearance').screenshot({path: info.outputPath(`card-color-${theme}-${width}.png`)});
        await page.getByRole('button', {name: 'Save', exact: true}).press('Enter');
        await expect(page).not.toHaveURL(/debit-cards\/create\/$/);
        await page.goto('/transactions/create/');
        const card = await page.locator('#id_debit_card option').filter({hasText: /^Custom card -/}).getAttribute('value');
        await page.goto(`/banking/debit-cards/${card}/edit/`);
        await expect(page.locator('#id_color')).toHaveValue('#aabbcc');
        await expect(page.locator('#id_gradient_end')).toHaveValue('#112233');
        await expect(page.locator('#id_gradient_angle')).toHaveValue('15');
        await expect(page.locator('[data-color-presets] button[aria-pressed="true"]')).toHaveCount(0);
        await page.locator('#id_color').evaluate(input => {
            input.value = '#64788c';
            input.form.dispatchEvent(new Event('tuxedo:restore'));
        });
        await expect(page.getByRole('button', {name: 'Blue gray', exact: true})).toHaveAttribute('aria-pressed', 'true');
    });
}

test.describe('native color fallback', () => {
    test.use({javaScriptEnabled: false});
    test('bank and card creation accept custom colors without JavaScript', async ({page}, info) => {
        await fixture(page, info);
        await page.goto('/banking/create/');
        await expect(page.locator('[data-color-presets]')).toBeHidden();
        await expect(page.locator('#id_color')).toHaveAttribute('list', 'id_color-palette');
        await page.locator('#id_name').fill('Native palette bank');
        await page.locator('#id_color').fill('#abcdef');
        await page.getByRole('button', {name: 'Save', exact: true}).click();
        await page.goto('/banking/accounts/create/');
        const bank = await page.locator('#id_bank option').last().getAttribute('value');
        await post(page, '/banking/accounts/create/', {bank, name: 'Native palette account', currency: 'BRL', opening_balance: '0'});
        await page.goto('/banking/debit-cards/create/');
        const account = await page.locator('#id_account option').last().getAttribute('value');
        await page.locator('#id_account').selectOption(account);
        await page.locator('#id_name').fill('Native custom card');
        await page.locator('#id_color').fill('#fedcba');
        await page.locator('#id_use_gradient').check();
        await page.locator('#id_gradient_end').fill('#010203');
        await page.locator('#id_gradient_angle').fill('270');
        await page.getByRole('button', {name: 'Save', exact: true}).click();
        await expect(page).not.toHaveURL(/debit-cards\/create\/$/);
        await page.goto('/transactions/create/');
        const card = await page.locator('#id_debit_card option').filter({hasText: /^Native custom card -/}).getAttribute('value');
        await page.goto(`/banking/debit-cards/${card}/edit/`);
        await expect(page.locator('#id_color')).toHaveValue('#fedcba');
        await expect(page.locator('#id_gradient_end')).toHaveValue('#010203');
        await expect(page.locator('#id_gradient_angle')).toHaveValue('270');
    });
});

for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
    test(`Portuguese bank, card and account controls remain readable (${theme}, ${width})`, async ({page, baseURL}, info) => {
        await page.setViewportSize({width, height: 850});
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await fixture(page, info);
        await page.context().addCookies([{name: 'django_language', value: 'pt-br', url: baseURL}]);
        await page.goto('/banking/create/');
        await expect(page.locator('html')).toHaveAttribute('lang', 'pt-br');
        const names = ['Preto', 'Cinza azulado', 'Roxo', 'Azul', 'Laranja', 'Dourado'];
        for (const name of names) await expect(page.getByRole('button', {name, exact: true})).toBeVisible();
        await page.getByRole('button', {name: 'Cinza azulado', exact: true}).press('Enter');
        await expect(page.locator('#id_color')).toHaveValue('#64788c');
        await expect(page.getByText('Outra cor', {exact: true})).toBeVisible();
        await assertCompact(page);
        await page.screenshot({path: info.outputPath(`bank-pt-${theme}-${width}.png`), fullPage: true});
        await post(page, '/banking/create/', {name: 'Banco de teste', color: '#64788C'});
        await page.goto('/banking/accounts/create/');
        await expect(page.getByText('Saldo ao começar o controle', {exact: false}).first()).toBeVisible();
        await expect(page.locator('#id_opening_date')).toBeVisible();
        const summary = page.locator('#account-planning-adjustments > summary');
        await expect(summary).toHaveText('Ajustes de planejamento (opcional)');
        await summary.press('Enter');
        await expect(page.getByText('Manter fora do planejamento mensal', {exact: false}).first()).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath(`account-pt-${theme}-${width}.png`), fullPage: true});
        await page.getByRole('button', {name: 'Salvar', exact: true}).scrollIntoViewIfNeeded();
        await page.screenshot({path: info.outputPath(`account-pt-viewport-${theme}-${width}.png`)});
        const bank = await page.locator('#id_bank option').last().getAttribute('value');
        await post(page, '/banking/accounts/create/', {bank, name: 'Conta de teste', currency: 'BRL', opening_balance: '0'});
        await page.goto('/banking/credit-cards/create/');
        await page.getByRole('button', {name: 'Roxo', exact: true}).press('Space');
        await page.locator('#id_use_gradient').press('Space');
        await expect(page.locator('#id_gradient_end')).toBeVisible();
        await expect(page.locator('[data-card-angle-dial]')).toHaveRole('slider');
        await assertCompact(page);
        await page.screenshot({path: info.outputPath(`card-pt-${theme}-${width}.png`), fullPage: true});
        await page.locator('.card-appearance').scrollIntoViewIfNeeded();
        await page.screenshot({path: info.outputPath(`card-pt-viewport-${theme}-${width}.png`)});
    });
}
