// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const {selectChoice} = require('../helpers/forms');
const fs = require('node:fs/promises');

async function post(page, path, fields, expected = 302) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved = await page.request.post(path, {form: {csrfmiddlewaretoken: csrf, ...fields},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(saved.status(), await saved.text()).toBe(expected);
    return saved.headers().location;
}

async function seed(page, info) {
    const username = `entry-polish-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/categories/delete-all/', {});
    await post(page, '/banking/create/', {name: 'Banco de despesas e compromissos familiares internacionais', color: '#527891'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: 'Conta para despesas e viagens internacionais em família',
        currency: 'BRL', opening_balance: '5000', opening_date: '2020-01-01', pix_enabled: 'on'});
    const rootName = 'CATEG'.repeat(20), deleteName = 'DELETE'.repeat(16);
    await post(page, '/categories/create/', {name: rootName, transaction_type: 'EXPENSE'});
    await page.goto('/categories/create/');
    const root = await page.locator('#id_parent_category option').filter({hasText: rootName}).getAttribute('value');
    await post(page, '/categories/create/', {name: 'Compras e serviços para viagens e compromissos familiares', transaction_type: 'EXPENSE', parent_category: root});
    await post(page, '/categories/create/', {name: deleteName, transaction_type: 'EXPENSE'});
    await page.goto('/categories/create/');
    const child = await page.locator('#id_parent_category option').filter({hasText: 'Compras e serviços'}).getAttribute('value');
    const unused = await page.locator('#id_parent_category option').filter({hasText: deleteName}).getAttribute('value');
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    await post(page, '/banking/credit-cards/create/', {account, name: 'Cartão para despesas e viagens internacionais em família',
        color: '#5B3E7C', use_gradient: 'on', gradient_end: '#C6A173', gradient_angle: '45', card_type: 'PHYSICAL', closing_day: '20', due_day: '28'});
    await page.goto('/transactions/create/');
    const credit = await page.locator('#id_credit_card option').last().getAttribute('value');
    const title = 'COMPRA'.repeat(25), date = new Date().toISOString().slice(0, 10);
    await post(page, '/transactions/create/', {title, amount: '100', transaction_type: 'EXPENSE',
        category: root, payment_channel: 'ACCOUNT', bank_account: account, date});
    await page.goto('/transactions/');
    const row = page.locator('#transaction-results li').filter({hasText: title}).first();
    const edit = new URL(await row.getByRole('link', {name: 'Edit', exact: true}).getAttribute('href'), info.project.use.baseURL).pathname;
    const id = edit.match(/\/(\d+)\/edit\//)[1];
    return {root, child, unused, rootName, deleteName, title, account, credit, edit,
        split: `/transactions/${id}/split/`, remove: `/transactions/${id}/delete/`};
}

async function setup(page) {
    await page.addInitScript(() => localStorage.setItem('theme', sessionStorage.getItem('entryAuditTheme') || 'light'));
    page.on('dialog', dialog => dialog.accept());
    await page.addLocatorHandler(page.locator('#departure-confirm[open]'), () => page.locator('[data-departure-leave]').click());
}

async function appearance(page, info, width, theme, language) {
    await page.setViewportSize({width, height: width < 640 ? 640 : 900});
    await page.evaluate(value => sessionStorage.setItem('entryAuditTheme', value), theme);
    await page.context().addCookies([{name: 'django_language', value: language, url: info.project.use.baseURL}]);
}

async function record(page, info, name, states) {
    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/htmx-settling/);
    states.push({name, url: page.url(), ...await page.evaluate(() => ({width: innerWidth,
        documentWidth: document.documentElement.scrollWidth}))});
    await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
    expect(states.at(-1).documentWidth).toBeLessThanOrEqual(states.at(-1).width);
}

for (const theme of ['light', 'dark']) {
test(`ordinary category dropdowns reveal long complete labels (${theme})`, async ({page}, info) => {
    await setup(page); const data = await seed(page, info), states = [];
    await appearance(page, info, 360, theme, 'pt-br');
    for (const [route, input, name] of [['/categories/create/', '#parent-category-search', '01-category-parent-results'],
        ['/transactions/create/', '#category-search', '02-transaction-category-results']]) {
        await page.goto(route);
        if (route.startsWith('/transactions')) await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
        await page.locator(input).fill(data.rootName);
        await expect(page.locator(`${input}-results [role="option"]`).first()).toBeVisible();
        await record(page, info, name, states);
        const result = page.locator(`${input}-results [role="option"]`).first();
        const geometry = await result.evaluate(element => ({width: element.clientWidth,
            textWidth: element.scrollWidth, overflowWrap: getComputedStyle(element).overflowWrap}));
        states.push({name: `${name}-text-width`, ...geometry});
        expect(geometry.textWidth).toBeLessThanOrEqual(geometry.width);
        const box = await result.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(12);
        expect(box.x + box.width).toBeLessThanOrEqual(348);
        await page.locator(input).press('ArrowDown');
        await expect(page.locator(input)).toBeFocused();
        await page.locator(input).press('Enter');
        await expect(page.locator(route.startsWith('/categories') ? '#id_parent_category' : '#id_category')).toHaveValue(data.root);
    }
    await fs.writeFile(info.outputPath('dropdown-states.json'), JSON.stringify(states, null, 2));
});

test(`categories complete forms, confirmations and filters (${theme})`, async ({page}, info) => {
    await setup(page); const data = await seed(page, info), states = [];
    for (const [width, language] of [[1440, 'en'], [360, 'pt-br']]) {
        await appearance(page, info, width, theme, language);
        for (const [name, route] of [['01-list', '/categories/'], ['02-create', '/categories/create/'],
            ['03-edit', `/categories/${data.child}/edit/`], ['04-delete', `/categories/${data.unused}/delete/`],
            ['05-import', '/categories/import/'], ['06-delete-all', '/categories/delete-all/']]) {
            await page.goto(route); await record(page, info, `${width}-${name}`, states);
        }
        await page.goto('/categories/create/');
        await page.locator('#id_name').fill(data.rootName);
        await page.locator('main button[type="submit"]').press('Enter');
        await expect(page.locator('#id_name-error-1')).toBeVisible();
        await record(page, info, `${width}-07-category-invalid`, states);
        const origin = `/categories/?q=${data.deleteName}&type=EXPENSE&level=top`;
        await page.goto(origin);
        const menu = page.locator(`[data-category-actions-for="${data.unused}"] details`);
        await menu.locator('summary').press('Enter');
        const deletion = menu.getByRole('link', {name: language === 'en' ? 'Delete' : 'Excluir', exact: true});
        states.push({name: `${width}-delete-origin`, href: await deletion.getAttribute('href')});
        expect(new URL(await deletion.getAttribute('href'), info.project.use.baseURL).searchParams.get('next')).toBe(origin);
        await deletion.press('Enter');
        const cancel = page.getByRole('link', {name: language === 'en' ? 'Cancel' : 'Cancelar', exact: true});
        states.push({name: `${width}-cancel-origin`, href: await cancel.getAttribute('href')});
        await expect(cancel).toHaveAttribute('href', origin);
        await cancel.press('Enter');
        await record(page, info, `${width}-08-after-cancel`, states);
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        for (const [link, target] of [[language === 'en' ? 'Import CSV' : 'Importar CSV', '/categories/import/'],
            [language === 'en' ? 'Delete all' : 'Excluir todas', '/categories/delete-all/']]) {
            const options = page.locator('main details.secondary-actions').first();
            await options.locator(':scope > summary').press('Enter');
            await options.locator(`a[href^="${target}"]`).press('Enter');
            await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
            await page.getByRole('link', {name: language === 'en' ? 'Cancel' : 'Cancelar', exact: true}).press('Enter');
            await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        }
    }
    await fs.writeFile(info.outputPath('category-states.json'), JSON.stringify(states, null, 2));
});

test(`transaction complete entry, cards, allocations and confirmation (${theme})`, async ({page}, info) => {
    await setup(page); const data = await seed(page, info), states = [];
    for (const [width, language] of [[1440, 'en'], [360, 'pt-br']]) {
        await appearance(page, info, width, theme, language);
        for (const [name, route] of [['01-list', '/transactions/'], ['02-create', '/transactions/create/'],
            ['03-edit', data.edit], ['04-split', data.split], ['05-delete', data.remove]]) {
            await page.goto(route); await record(page, info, `${width}-${name}`, states);
        }
        await page.goto('/transactions/create/');
        await selectChoice(page.locator('#id_transaction_type'), 'EXPENSE');
        await page.locator('#id_title').fill(data.title);
        await page.locator('#id_amount').fill('100.00');
        await page.locator('#id_date').fill('31/02/2030');
        await page.locator('#id_split_categories').press('Space');
        await selectChoice(page.locator('#id_splits-0-category'), data.root);
        await selectChoice(page.locator('#id_splits-1-category'), data.child);
        await selectChoice(page.locator('#id_payment_channel'), 'CREDIT_CARD');
        await selectChoice(page.locator('#id_credit_card'), data.credit);
        await page.locator('#id_installments').fill('3');
        await record(page, info, `${width}-06-full-credit-entry`, states);
        await page.locator('#id_splits-0-amount').fill('100');
        await expect(page.locator('[data-allocation-row-error]:visible')).toBeVisible();
        await record(page, info, `${width}-07-allocation-error`, states);
        await page.locator('#id_splits-0-amount').fill('60');
        await page.locator('main button[type="submit"]').first().press('Enter');
        await expect(page.locator('#id_date-error-1')).toBeVisible();
        await record(page, info, `${width}-08-full-bound-error`, states);
        await expect(page.locator('#id_credit_card')).toHaveValue(data.credit);
        await expect(page.locator('#id_installments')).toHaveValue('3');
        await expect(page.locator('#id_splits-0-amount')).toHaveValue('60.00');
        await expect(page.locator('#id_splits-1-amount')).toHaveValue('40.00');
        await page.locator('#id_date').fill('15/01/2030');
        await page.locator('main button[type="submit"]').first().press('Enter');
        await expect(page).toHaveURL(/\/transactions\/$/);
        const notice = page.locator('.notice-panel');
        await expect(notice).toContainText(data.title);
        expect(await notice.locator('p').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        await record(page, info, `${width}-09-success-notice`, states);
    }
    await fs.writeFile(info.outputPath('transaction-states.json'), JSON.stringify(states, null, 2));
});
}

test('native category actions preserve filters, invalid import recovery and protected data', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 360, height: 640}});
    try {
        const page = await context.newPage(), data = await seed(page, info);
        await context.addCookies([{name: 'django_language', value: 'en', url: info.project.use.baseURL}]);
        const origin = `/categories/?q=${data.deleteName}&type=EXPENSE&level=top`;
        await page.goto(origin);
        const menu = page.locator(`[data-category-actions-for="${data.unused}"] details`);
        await menu.locator('summary').press('Enter');
        await menu.getByRole('link', {name: 'Delete', exact: true}).press('Enter');
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.getByRole('link', {name: 'Cancel', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await menu.locator('summary').press('Enter');
        await menu.getByRole('link', {name: 'Delete', exact: true}).press('Enter');
        await page.getByRole('button', {name: 'Delete', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await page.goto(`/categories/import/?next=${encodeURIComponent(origin)}`);
        await page.locator('#id_file').setInputFiles({name: 'invalid.csv', mimeType: 'text/csv',
            buffer: Buffer.from('name,transaction_type,parent_category\nBroken,EXPENSE,,extra\n')});
        await page.getByRole('button', {name: 'Import', exact: true}).press('Enter');
        await expect(page.locator('#id_file-error-1')).toBeVisible();
        await expect(page.locator('main input[name="next"]')).toHaveValue(origin);
        await page.locator('#id_file').setInputFiles({name: 'valid.csv', mimeType: 'text/csv',
            buffer: Buffer.from(`name,transaction_type,parent_category\n${data.deleteName}CSV,EXPENSE,\n`)});
        await page.getByRole('button', {name: 'Import', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        await page.goto(`/categories/delete-all/?next=${encodeURIComponent(origin)}`);
        await page.getByRole('button', {name: 'Yes, delete all', exact: true}).press('Enter');
        await expect(page).toHaveURL(url => url.pathname + url.search === origin);
        await expect(page.locator('.notice-panel')).toContainText('cannot be deleted');
        await expect(page.locator('#category-results-status')).toHaveText('1 category');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath('native-category-actions.png'), fullPage: true});
    } finally {await context.close();}
});
