const {projectRoot} = require('../helpers/paths');
// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
const fs = require('node:fs/promises');
const {resolve} = require('node:path');
const baseline = process.env.REPORTS_AUDIT_BASELINE === '1';

async function post(page, path, values) {
    const response = await page.request.get(path);
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {form: {csrfmiddlewaretoken: token, ...values},
        headers: {Referer: response.url()}, maxRedirects: 0});
    expect(result.status(), await result.text()).toBe(302);
}
async function seed(page, info) {
    const username = `reports-design-${info.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {username, email: `${username}@example.test`, password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!'});
    await post(page, '/accounts/settings/', {base_currency: 'BRL', date_format: 'DMY'});
    const names = {bank: 'Institution' + 'X'.repeat(85), account: 'Account' + 'Y'.repeat(90), category: 'Category' + 'Z'.repeat(52)};
    await post(page, '/banking/create/', {name: names.bank, color: '#315D50'});
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').filter({hasText: names.bank}).getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name: names.account, currency: 'BRL', opening_balance: '2000', opening_date: '2020-01-01', planning_enabled: 'on'});
    await post(page, '/banking/credit-cards/create/', {account: await (async () => {
        await page.goto('/banking/credit-cards/create/');
        return page.locator('#id_account option').filter({hasText: names.account}).getAttribute('value');
    })(), name: 'Daily violet', card_type: 'PHYSICAL', closing_day: '20', due_day: '28', color: '#5B3E7C', use_gradient: 'on', gradient_end: '#315D50', gradient_angle: '135'});
    await post(page, '/categories/create/', {name: names.category, transaction_type: 'EXPENSE'});
    await post(page, '/categories/create/', {name: 'Salary audit', transaction_type: 'INCOME'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').filter({hasText: names.account}).getAttribute('value');
    const card = await page.locator('#id_credit_card option').filter({hasText: 'Daily violet'}).getAttribute('value');
    const category = await page.locator('#id_category option').filter({hasText: names.category}).getAttribute('value');
    const income = await page.locator('#id_category option').filter({hasText: 'Salary audit'}).getAttribute('value');
    const now = new Date(); const month = now.toISOString().slice(0,7);
    const previous = new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth()-1,1)).toISOString().slice(0,7);
    for (const [title,amount,date,kind,cat,channel,record,extra] of [
        ['Salary source','2000',`${month}-01`,'INCOME',income,'ACCOUNT',{bank_account: account},{}],
        ['Ordinary source','89.90',`${month}-01`,'EXPENSE',category,'ACCOUNT',{bank_account: account},{}],
        ['Fixed source','12.34',`${month}-02`,'EXPENSE',category,'ACCOUNT',{bank_account: account},{is_fixed:'on',fixed_until:`${month}-02`}],
        ['Installment source','123.45',`${month}-01`,'EXPENSE',category,'CREDIT_CARD',{credit_card: card},{installments:'3'}],
        ['Previous source','60',`${previous}-01`,'EXPENSE',category,'ACCOUNT',{bank_account: account},{}],
    ]) await post(page,'/transactions/create/',{title,amount,date,transaction_type:kind,category:cat,payment_channel:channel,...record,...extra});
    return {month,previous,names,bank,account};
}
async function screenshot(page, info, name) {
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({path: info.outputPath(name)});
}
async function observations(page) {
    return page.evaluate(() => ({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        chartRegions: [...document.querySelectorAll('#reports-charts svg.chart-canvas')].map(svg => {
            const box = svg.parentElement;
            return {width: box.clientWidth, scrollWidth: box.scrollWidth, tabindex: box.getAttribute('tabindex'), role: box.getAttribute('role'), name: box.getAttribute('aria-label') || document.getElementById(box.getAttribute('aria-labelledby'))?.textContent};
        }),
        bankHeadings: [...document.querySelectorAll('#instrument-activity h3')].map(el => {
            const r = document.createRange();r.selectNodeContents(el);const b=r.getBoundingClientRect();
            return {left:b.left,right:b.right,text:el.textContent};
        }),
        resetControls: [...document.querySelectorAll('#instrument-all,#instrument-current,#installment-all,#installment-current')].map(el => {
            const b=el.getBoundingClientRect();return {id:el.id,tag:el.tagName,width:b.width,height:b.height,current:el.getAttribute('aria-current')};
        })
    }));
}

async function reference(page, info, theme) {
    const root = projectRoot;
    await page.route('**/audit-reference/**', route => {
        const file = new URL(route.request().url()).pathname.slice('/audit-reference/'.length);
        if ((file.startsWith('docs/design-system') || file.startsWith('static/')) && !file.split('/').includes('..')) {
            return route.fulfill({path: resolve(root, file)});
        }
        return route.abort();
    });
    await page.goto('/audit-reference/docs/design-system.html#data');
    await page.locator('#data').scrollIntoViewIfNeeded();
    await screenshot(page, info, `00-design-reference-${theme}.png`);
}

for (const theme of ['light','dark']) {
    test(`Reports fresh design review and preserved controls (${theme})`, async ({page},info) => {
        test.setTimeout(150000);
        const errors=[];page.on('pageerror',error=>errors.push(error.message));
        await page.addInitScript(value=>localStorage.setItem('theme',value),theme);
        const data=await seed(page,info);
        const observed=[];
        for (const width of [1280,390]) {
            await page.setViewportSize({width,height:width===390?640:900});
            await page.goto(`/dashboard/reports/?instrument_month=${data.month}&installment_month=${data.month}`);
            await expect(page.locator('#reports-charts')).toBeVisible();
            observed.push(await observations(page));
            await screenshot(page,info,`01-overview-${theme}-${width}.png`);
            for(const [id,prefix] of [['monthly-cashflow','02-cashflow'],['installments','03-installments'],['instrument-activity','04-instruments']]) {
                await page.locator(`#${id}`).scrollIntoViewIfNeeded();
                await screenshot(page,info,`${prefix}-${theme}-${width}.png`);
            }
            const mark=page.locator('#instrument-activity [data-chart-layer="instrument-interactions"] [data-point][data-series="1"]').first();
            // Expense-first bar configurations may use a different series index;
            // choose by actual signed selection values instead of visible labels.
            const expense=await mark.count()?mark:page.locator('#instrument-activity [data-chart-layer="instrument-interactions"] [data-point]').first();
            await expense.focus();await page.keyboard.press('Control');
            const panel=page.locator('.chart-composition:visible');
            await expect(panel).toBeVisible();
            await screenshot(page,info,`05-composition-${theme}-${width}.png`);
            await page.keyboard.press('Escape');await expect(panel).toHaveCount(0);
            if (!baseline) {
                expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
                for(const region of await observations(page).then(o=>o.chartRegions)) {
                    if(region.scrollWidth>region.width+1) {
                        expect(region.tabindex).toBe('0');expect(region.role).toBe('region');expect(region.name).toBeTruthy();
                    }
                }
                const expenseMark=page.locator('#instrument-activity [data-chart-layer="instrument-interactions"] [data-point][data-series="0"]').first();
                await expenseMark.press('Enter');
                const selected=page.locator('#instrument-activity [data-selection-summary]');
                await expect(selected).toContainText(data.names.bank);
                await expect(selected).toContainText(/102[,.]24/);
                expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
                await screenshot(page,info,`07-selected-expenses-${theme}-${width}.png`);
                await expenseMark.focus();await page.keyboard.press('Control');
                await expect(panel).toContainText(data.names.category);
                const disclosure=panel.locator('details.chart-composition-group summary').first();
                await disclosure.press('Enter');
                await expect(panel.getByRole('link',{name:/Ordinary source/})).toBeVisible();
                await expect(panel.getByRole('link',{name:/Fixed source/})).toBeVisible();
                await screenshot(page,info,`08-expense-sources-${theme}-${width}.png`);
                await page.keyboard.press('Escape');
                await expect(expenseMark).toBeFocused();

                const next=page.locator('#instrument-next');
                const previous=page.locator('#instrument-previous');
                const slots=[await previous.boundingBox(),await next.boundingBox()];
                await expect(page.locator('#instrument-current')).toHaveAttribute('aria-current','date');
                await page.locator('#instrument-all').press('Enter');
                await expect(page).toHaveURL(/instrument_month=ALL/);
                await expect(page.locator('#instrument-all')).toHaveAttribute('aria-current','true');
                await expect(page.locator('#instrument-all')).toBeFocused();
                for (const [index,arrow] of [previous,next].entries()) {
                    const box=await arrow.boundingBox();
                    expect(Math.abs(box.x-slots[index].x)).toBeLessThan(2);
                    expect(box.width).toBe(44);
                }
                for(const id of ['instrument-all','instrument-current','installment-all','installment-current']) {
                    expect((await page.locator(`#${id}`).boundingBox()).height).toBeGreaterThanOrEqual(44);
                }
                await screenshot(page,info,`09-active-period-${theme}-${width}.png`);
                await page.locator('#instrument-current').press('Enter');
                await expect(page).toHaveURL(new RegExp(`instrument_month=${data.month}`));
                await expect(page.locator('#instrument-current')).toBeFocused();
                if(width<768) {
                    const region=page.locator('#balance-evolution .report-chart-scroll');
                    await region.focus();
                    const documentX=await page.evaluate(()=>scrollX);
                    await region.press('ArrowRight');
                    await expect.poll(()=>region.evaluate(el=>el.scrollLeft)).toBeGreaterThan(0);
                    expect(await page.evaluate(()=>scrollX)).toBe(documentX);
                    await screenshot(page,info,`10-chart-keyboard-pan-${theme}-${width}.png`);
                }
            }
        }
        if(!baseline) {
            // Exercise the actual server-rendered tooltip using the widest
            // uninterrupted names, with complete ARIA/ledger identities retained.
            for (const language of ['en','pt-br']) {
                await page.context().addCookies([{name:'django_language',value:language,url:info.project.use.baseURL}]);
                for (const character of ['W','C']) {
                    const name=character.repeat(97);
                    await post(page,`/banking/accounts/${data.account}/edit/`,{bank:data.bank,name,currency:'BRL',opening_balance:'2000',opening_date:'2020-01-01',planning_enabled:'on',reserved_amount:'0'});
                    await page.goto(`/dashboard/reports/?instrument_month=${data.month}&installment_month=${data.month}`);
                    await page.evaluate(()=>document.fonts.ready);
                    const mark=page.locator('#instrument-activity [data-chart-layer="instrument-interactions"] [data-point][data-series="0"]').first();
                    await expect(mark).toHaveAttribute('aria-label',new RegExp(name));
                    await mark.focus();
                    const size=await mark.locator(':scope > g').evaluate(group=>{
                        const text=group.querySelector('text').getBBox();
                        return {left:text.x,right:text.x+text.width,limit:Number(group.querySelector('rect').getAttribute('width'))-10};
                    });
                    expect(size.left).toBeGreaterThanOrEqual(10);
                    expect(size.right).toBeLessThanOrEqual(size.limit);
                    await screenshot(page,info,`12-tooltip-width-${theme}-${language}-${character}.png`);
                }
            }
            await reference(page,info,theme);
        }
        await fs.writeFile(info.outputPath('06-observations.json'),JSON.stringify(observed,null,2));
        expect(errors).toEqual([]);
    });
}

test('Reports native month controls retain independent filters in Portuguese', async ({browser},info) => {
    test.skip(baseline,'Fresh baseline only captures the unchanged interactive screens.');
    const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:640}});
    try {
        const page=await context.newPage();const data=await seed(page,info);
        await context.addCookies([{name:'django_language',value:'pt-br',url:info.project.use.baseURL}]);
        await page.goto(`/dashboard/reports/?charts_offset=-1&instrument_month=${data.month}&installment_month=${data.month}`);
        for(const id of ['installment-all','instrument-all']) {
            await page.locator(`#${id}`).press('Enter');
            await expect(page).toHaveURL(/charts_offset=-1/);
            await expect(page.locator(`#${id}`)).toHaveAttribute('aria-current','true');
        }
        await expect(page).toHaveURL(/instrument_month=ALL/);
        await expect(page).toHaveURL(/installment_month=ALL/);
        await page.locator('#instrument-current').press('Enter');
        await expect(page).toHaveURL(new RegExp(`instrument_month=${data.month}`));
        await expect(page).toHaveURL(/installment_month=ALL/);
        await page.locator('#instrument-activity').scrollIntoViewIfNeeded();
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        await screenshot(page,info,'11-native-periods-pt-390.png');
    } finally {await context.close();}
});
