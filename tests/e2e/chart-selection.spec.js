// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
async function post(page, path, values) {
    const response = await page.request.get(path);
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result = await page.request.post(path, {
        form: { csrfmiddlewaretoken: csrf, ...values },
        headers: { Referer: response.url() }, maxRedirects: 0,
    });
    const errors = (await result.text()).match(/<[^>]+id="[^"]+-error-[^"]+"[^>]*>.*?<\/[^>]+>/g);
    expect(result.status(), `${path}: ${errors || 'unexpected response'}`).toBe(302);
}

async function seed(page, testInfo) {
    const username = `context-help-${testInfo.workerIndex}-${Date.now()}`;
    await post(page, '/accounts/signup/', {
        username, email: `${username}@example.test`,
        password1: 'Tuxedo-Help-2026!', password2: 'Tuxedo-Help-2026!',
    });
    await post(page, '/banking/create/', { name: 'Help bank' });
    await page.goto('/investments/products/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/investments/products/create/', { bank, name: 'Savings', purpose: 'INVESTMENT' });
    await page.goto('/investments/assets/create/');
    const product = await page.locator('#id_opening_product option').last().getAttribute('value');
    await post(page, '/investments/assets/create/', {
        name: 'Saved balance', code: 'SAVE', asset_class: 'LIQUIDITY', currency: 'BRL',
        valuation_mode: 'MONETARY', opening_balance: '1000', opening_product: product,
        opening_quantity: '0', opening_unit_price: '0',
    });
    await page.goto('/investments/create/');
    const asset = await page.locator('#id_asset option').last().getAttribute('value');
    await post(page, '/investments/create/', {
        product, asset, kind: 'YIELD', yield_input_mode: 'YIELD_AMOUNT', amount: '10', fees: '0', date: new Date().toISOString().slice(0,10),
    });
}


async function seedExpenses(page) {
    await page.goto('/banking/accounts/create/');
    const bank = await page.locator('#id_bank option').last().getAttribute('value');
    await post(page, '/banking/accounts/create/', {bank, name:'Daily',currency:'BRL',opening_balance:'1000',pix_enabled:'on'});
    await post(page, '/categories/create/', {name:'Selection A',transaction_type:'EXPENSE'});
    await post(page, '/categories/create/', {name:'Selection B',transaction_type:'EXPENSE'});
    await page.goto('/transactions/create/');
    const account = await page.locator('#id_bank_account option').last().getAttribute('value');
    const today = new Date().toISOString().slice(0,10);
    for (const [name,amount,fixed] of [['Selection A','10',false],['Selection B','20',true]]) {
        const category = await page.locator('#id_category option').filter({hasText:name}).getAttribute('value');
        await post(page, '/transactions/create/', {title:name,category,amount,transaction_type:'EXPENSE',
            payment_channel:'ACCOUNT',bank_account:account,date:today,installments:'1', ...(fixed?{is_fixed:'on',fixed_until:today}:{})});
    }
}

for (const theme of ['light','dark']) {
    test(`direct chart selection, Ctrl composition and outside clearing (${theme})`, async({page},info)=>{
        const errors=[];page.on('pageerror',error=>errors.push(error.message));
        await page.addInitScript(theme=>localStorage.setItem('theme',theme),theme);
        await seed(page,info);await seedExpenses(page);
        await page.goto('/dashboard/reports/?instrument_month=ALL&installment_month=ALL');
        await expect(page.locator('[data-selection-start], #id_range_start')).toHaveCount(0);
        await expect(page.getByRole('heading',{name:'Where the money goes',exact:true})).toHaveCount(0);
        const donut=page.locator('#installments'), slices=donut.locator('[data-chart-layer="recurrence-interactions"] [data-point]');
        const original=await donut.locator('[data-donut-total]').textContent();
        await slices.first().press('Enter');
        await expect(donut.locator('[data-donut-total]')).toContainText('20.00');
        await slices.last().press('Shift+Space');
        await expect(donut.locator('[data-donut-total]')).toContainText('30.00');
        await expect(donut.locator('[data-selection-summary]')).toBeHidden();
        await slices.first().press('Shift+Enter');
        await expect(donut.locator('[data-donut-total]')).toContainText('10.00');
        await page.getByRole('heading',{level:1}).click();
        await expect(donut.locator('[data-donut-total]')).toHaveText(original);
        await donut.locator('[data-legend-item]').first().click();
        await donut.locator('[data-legend-item]').last().click({modifiers:['Shift']});
        await expect(donut.locator('[data-donut-total]')).toContainText('30.00');
        const instrument=page.locator('#instrument-activity');
        const bar=instrument.locator('[data-chart-layer="instrument-interactions"] [data-point]').first();
        await expect(instrument.locator('svg a')).toHaveCount(0);
        const url=page.url();await bar.click();
        await expect(instrument.locator('[data-selection-values]')).toContainText('30.00');
        await expect(page).toHaveURL(url);
        await bar.hover();await page.keyboard.down('Control');
        await expect(page.locator('.chart-composition:visible')).toContainText('Selection A');
        await expect(page.locator('.chart-composition:visible')).toContainText('Selection B');
        await page.keyboard.up('Control');await expect(page.locator('.chart-composition:visible')).toHaveCount(0);
        const balance=page.locator('[data-balance-range]');
        await balance.locator('[data-selection-surface]').scrollIntoViewIfNeeded();
        const points=balance.locator('[data-point]');
        const from=await points.nth(8).locator('circle').first().boundingBox(), to=await points.nth(2).locator('circle').first().boundingBox();
        await page.mouse.move(from.x+from.width/2,from.y+from.height/2);await page.mouse.down();
        await page.mouse.move(to.x+to.width/2,to.y+to.height/2,{steps:8});await page.mouse.up();
        await expect(balance.locator('[data-selection-summary]')).toBeVisible();
        await page.getByRole('heading',{level:1}).click();await expect(balance.locator('[data-selection-summary]')).toBeHidden();
        await page.goto('/investments/');
        const total=page.locator('[data-chart-selection]').first(), marks=total.locator('[data-point]');
        await marks.first().press('Enter');await marks.last().press('Space');
        await expect(total.locator('[data-selection-values]')).toContainText('1,010.00');
        await marks.last().focus();await page.keyboard.down('Control');
        await expect(page.locator('.chart-composition:visible')).toContainText('Savings > Saved balance');
        await expect(page.locator('.chart-composition:visible')).toContainText('1,010.00');
        await page.keyboard.up('Control');
        await page.screenshot({path:info.outputPath(`direct-${theme}.png`)});
        expect(errors).toEqual([]);
    });
}

test('browser Back retains contextual navigation through investment operations',async({page},info)=>{
    await seed(page,info);await page.goto('/dashboard/reports/');
    await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Investments',exact:true}).click();
    await page.locator('#investment-operations-link').click();
    await expect(page).toHaveURL(/\/investments\/operations\//);
    await expect(page.locator('[data-previous-workspace]')).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(/\/investments\/$/);
});

test('bank color palette, arbitrary color and marker edit preserve the bank',async({page},info)=>{
    await seed(page,info);await page.goto('/banking/create/');
    await page.locator('#id_name').fill('Colored bank');
    await page.locator('#id_color').evaluate(input=>input.type='text');await page.locator('#id_color').fill('invalid');
    await page.getByRole('button',{name:'Save',exact:true}).click();
    await expect(page.locator('[data-field-error]')).toContainText('Enter a color in #RRGGBB format.');
    await expect(page.locator('#id_name')).toHaveValue('Colored bank');
    await page.getByRole('button',{name:'Use color #6E42A1',exact:true}).press('Enter');
    await expect(page.locator('#id_color')).toHaveValue('#6e42a1');
    await page.getByRole('button',{name:'Save',exact:true}).click();
    const panel=page.locator('section').filter({has:page.getByRole('heading',{name:'Colored bank',exact:true})});
    await expect(panel.locator('.bank-bookmark')).toHaveCSS('background-color','rgb(110, 66, 161)');
    await page.screenshot({path:info.outputPath('bank-list-marker.png')});
    await panel.getByRole('link',{name:'Colored bank',exact:true}).click();
    await page.getByRole('link',{name:'Change marker color',exact:true}).press('Enter');
    await page.locator('#id_color').fill('#1278ab');await page.getByRole('button',{name:'Save',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Colored bank',exact:true})).toBeVisible();
    await expect(page.locator('.bank-marker')).toHaveCSS('background-color','rgb(18, 120, 171)');
    await page.screenshot({path:info.outputPath('bank-marker.png')});
});

test('Shift-click sums chosen bars independently of the intervening series',async({page},info)=>{
    await seed(page,info);await seedExpenses(page);
    await page.goto('/banking/accounts/create/');const bank=await page.locator('#id_bank option').last().getAttribute('value');
    await post(page,'/banking/accounts/create/',{bank,name:'Second',currency:'BRL',opening_balance:'0'});
    await post(page,'/categories/create/',{name:'Income',transaction_type:'INCOME'});
    await page.goto('/transactions/create/');
    const accounts=page.locator('#id_bank_account option');const second=await accounts.filter({hasText:'Second'}).getAttribute('value');
    const first=await accounts.filter({hasText:'Daily'}).getAttribute('value');
    const expense=await page.locator('#id_category option').filter({hasText:'Selection A'}).getAttribute('value');
    const income=await page.locator('#id_category option').filter({hasText:/^Income$/}).getAttribute('value');
    const date=new Date().toISOString().slice(0,10);
    await post(page,'/transactions/create/',{title:'Second expense',category:expense,amount:'40',transaction_type:'EXPENSE',payment_channel:'ACCOUNT',bank_account:second,date,installments:'1'});
    await post(page,'/transactions/create/',{title:'Income',category:income,amount:'100',transaction_type:'INCOME',payment_channel:'ACCOUNT',bank_account:first,date,installments:'1'});
    await page.goto('/dashboard/reports/?instrument_month=ALL');
    const instrument=page.locator('#instrument-activity'), expenses=instrument.locator('[data-point][data-series="0"]');
    await expenses.first().click();await expenses.last().click({modifiers:['Shift']});
    await expect(instrument.locator('[data-selection-values]')).toContainText('70.00');
    await expect(instrument.locator('[data-selection-values]')).not.toContainText('170.00');
    await expenses.first().click({modifiers:['Shift']});
    await expect(instrument.locator('[data-selection-values]')).toContainText('40.00');
    await expenses.last().hover();await page.keyboard.down('Control');
    await expect(page.locator('.chart-composition:visible')).toContainText('Selection A');
    await expect(page.locator('.chart-composition:visible')).toContainText('40.00');
    await page.keyboard.up('Control');await page.keyboard.press('Escape');await expect(instrument.locator('[data-selection-summary]')).toBeHidden();
});

test('touch selection, held composition, and native bank colors remain usable on mobile',async({page,browser},info)=>{
    await seed(page,info);await seedExpenses(page);
    const context=await browser.newContext({hasTouch:true,viewport:{width:390,height:844},storageState:await page.context().storageState()});
    try {
        const mobile=await context.newPage();await mobile.goto('/dashboard/reports/?installment_month=ALL');
        const donut=mobile.locator('#installments'), legend=donut.locator('[data-legend-item]');
        await legend.first().tap();await legend.last().tap();
        await expect(donut.locator('[data-donut-total]')).toContainText('30.00');
        await legend.first().scrollIntoViewIfNeeded();const box=await legend.first().boundingBox();
        const client=await context.newCDPSession(mobile);
        await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+20,y:box.y+box.height/2}]});
        await expect(mobile.locator('.chart-composition:visible')).toContainText('Selection B');
        await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
        expect(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        await mobile.getByRole('heading',{level:1}).tap();await expect(mobile.locator('.chart-composition:visible')).toHaveCount(0);
        await mobile.screenshot({path:info.outputPath('direct-mobile.png')});
    } finally {await context.close();}
    const native=await browser.newContext({javaScriptEnabled:false,storageState:await page.context().storageState()});
    try {
        const p=await native.newPage();await p.goto('/banking/create/');
        await p.locator('#id_name').fill('Native color');await p.locator('#id_color').fill('#abcdef');await p.getByRole('button',{name:'Save',exact:true}).click();
        const panel=p.locator('section').filter({has:p.getByRole('heading',{name:'Native color',exact:true})});
        await expect(panel.locator('.bank-bookmark')).toHaveCSS('background-color','rgb(171, 205, 239)');
        await p.goto('/dashboard/reports/');await expect(p.locator('[data-balance-range] svg[data-selection-surface]')).toBeVisible();
        await expect(p.locator('[data-selection-start], #id_range_start')).toHaveCount(0);
    } finally {await native.close();}
});
