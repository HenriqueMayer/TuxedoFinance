// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
async function post(page, path, values) {
    const response=await page.request.get(path);
    const csrf=(await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const result=await page.request.post(path,{form:{csrfmiddlewaretoken:csrf,...values},headers:{Referer:response.url()},maxRedirects:0});
    expect(result.status(),await result.text()).toBe(302);
}
async function prepare(page,info) {
    const name=`month-widget-${info.workerIndex}-${Date.now()}`;
    await post(page,'/accounts/signup/',{username:name,email:`${name}@example.test`,password1:'Tuxedo-E2E-2026!',password2:'Tuxedo-E2E-2026!'});
    await post(page,'/banking/create/',{name:'Widget bank'});
    await page.goto('/banking/accounts/create/');
    const bank=await page.locator('#id_bank option').last().getAttribute('value');
    await post(page,'/banking/accounts/create/',{bank,name:'Widget account',currency:'BRL',opening_balance:'1000',opening_date:'2020-01-01',planning_enabled:'on'});
    await page.goto('/banking/credit-cards/create/');
    const account=await page.locator('#id_account option').last().getAttribute('value');
    await post(page,'/banking/credit-cards/create/',{account,name:'Widget card',card_type:'PHYSICAL',closing_day:'31',due_day:'10'});
    await post(page,'/categories/create/',{name:'Month shopping',transaction_type:'EXPENSE'});
    await page.goto('/transactions/create/');
    const card=await page.locator('#id_credit_card option').last().getAttribute('value');
    const category=await page.locator('#id_category option').filter({hasText:'Month shopping'}).getAttribute('value');
    const year=new Date().getFullYear();
    for (const [month,title] of [['09','September record'],['10','October record']])
        await post(page,'/transactions/create/',{title,category,amount:'10',transaction_type:'EXPENSE',payment_channel:'CREDIT_CARD',credit_card:card,date:`${year}-${month}-10`,installments:'1'});
    await page.goto('/transactions/');
    return year;
}
for (const [theme,language,width] of [['light','en',1366],['dark','en',1366],['light','pt-br',390],['dark','pt-br',390]]) {
    test(`compact month names, year, ambiguity, clear and history (${theme}, ${language})`,async({page},info)=>{
        const year=await prepare(page,info);
        await page.addInitScript(value=>localStorage.setItem('theme',value),theme);
        await page.context().addCookies([{name:'django_language',value:language,url:info.project.use.baseURL}]);
        await page.setViewportSize({width,height:800});await page.goto('/transactions/');
        const trigger=page.locator('#filter-month-trigger'), panel=page.locator('#filter-month-panel');
        const search=page.locator('#filter-month-choice-search'), native=page.locator('#filter-month');
        await expect(page.locator('#transaction-extra-filters')).not.toHaveAttribute('open','');
        await expect(native).toBeHidden();
        await page.evaluate(()=>scrollTo(0,40));const top=await page.evaluate(()=>scrollY);
        await trigger.press('Enter');await expect(search).toBeFocused();
        await search.pressSequentially(language==='en'?'sep':'sete');
        await expect(panel.getByRole('option')).toHaveCount(1);
        const bounds=await panel.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
        expect(bounds.y).toBeGreaterThanOrEqual(0);expect(bounds.y+bounds.height).toBeLessThanOrEqual(800);
        expect(Math.abs(await page.evaluate(()=>scrollY)-top)).toBeLessThan(4);
        await page.screenshot({path:info.outputPath(`month-popup-${theme}-${language}.png`)});
        await search.press('Enter');
        await expect(page).toHaveURL(url=>url.searchParams.get('month')===`${year}-09`);
        await expect(native).toHaveValue(`${year}-09`);await expect(trigger).toBeFocused();
        await expect(panel).toBeHidden();await expect(page.locator('#transaction-results')).toContainText('September record');
        await expect(page.locator('#transaction-results')).not.toContainText('October record');
        await trigger.press('Enter');await search.fill(language==='en'?'ju':'ma');
        await expect(panel.getByRole('option')).toHaveCount(2);await search.press('Enter');
        await expect(panel).toBeVisible();await expect(native).toHaveValue(`${year}-09`);
        await search.press('Escape');await expect(trigger).toBeFocused();
        await trigger.press('Enter');const yearInput=page.locator('#filter-month-year');
        await yearInput.fill('');await yearInput.press('Enter');await expect(yearInput).toHaveAttribute('aria-invalid','true');
        await expect(native).toHaveValue(`${year}-09`);
        await yearInput.fill(String(year-1));await yearInput.press('Enter');
        await search.fill(language==='en'?'sep':'sete');await search.press('Enter');
        await expect(page).toHaveURL(url=>url.searchParams.get('month')===`${year-1}-09`);
        await page.goBack();await expect(native).toHaveValue(`${year}-09`);
        await expect(trigger).toContainText(String(year));
        // The shared clear inside a selected month must clear its canonical GET
        // value, even with an invalid draft year in the open picker.
        await trigger.press('Enter');await yearInput.fill('');
        await panel.locator('.search-choice button').press('Enter');
        await expect(page).toHaveURL(url=>!url.searchParams.has('month'));
        await expect(native).toHaveValue('');await expect(trigger).toBeFocused();
        await expect(page.locator('#transaction-results')).toContainText('October record');
        await page.locator('#transaction-extra-filters > summary').press('Enter');
        const categorySearch=page.locator('#filter-category-search');await categorySearch.fill('Month shopping');
        await categorySearch.press('Enter');await expect(page.locator('#filter-category')).toHaveValue('');
        await categorySearch.press('ArrowDown');await categorySearch.press('Enter');
        await expect(page).toHaveURL(url=>Boolean(url.searchParams.get('category')));
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    });
}
test('native month retains ISO query without JavaScript',async({browser},info)=>{
    const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:800}});
    try {
        const page=await context.newPage();const year=await prepare(page,info);
        await expect(page.locator('#filter-month-trigger')).toHaveCount(0);
        await page.locator('#filter-month').fill(`${year}-09`);
        await page.locator('#transaction-apply-filters').press('Enter');
        await expect(page.locator('#transaction-results')).toContainText('September record');
        await expect(page.locator('#transaction-results')).not.toContainText('October record');
        await expect(page).toHaveURL(url=>url.searchParams.get('month')===`${year}-09`);
    } finally {await context.close();}
});
test('month selection remains usable with touch',async({browser},info)=>{
    const context=await browser.newContext({hasTouch:true,isMobile:true,viewport:{width:390,height:800}});
    try {
        const page=await context.newPage();const year=await prepare(page,info);
        await page.locator('#filter-month-trigger').tap();
        await page.locator('#filter-month-panel').getByRole('option',{name:'September',exact:true}).tap();
        await expect(page).toHaveURL(url=>url.searchParams.get('month')===`${year}-09`);
        await expect(page.locator('#filter-month-panel')).toBeHidden();
        await page.locator('#filter-month-trigger').tap();await page.getByRole('button',{name:'Close',exact:true}).tap();
        await expect(page.locator('#filter-month-panel')).toBeHidden();
    } finally {await context.close();}
});

for (const theme of ['light', 'dark']) {
    test(`closed invalid draft year cannot block native filter recovery (${theme})`, async ({page}, info) => {
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const year = await prepare(page, info);
        for (const invalidYear of ['0', '10000']) {
            await page.goto(`/transactions/?month=${year}-09`);
            const trigger = page.locator('#filter-month-trigger');
            const draftYear = page.locator('#filter-month-year');
            const canonical = page.locator('#filter-month');
            await trigger.press('Enter');
            await expect(draftYear).toBeEnabled();
            await draftYear.focus();
            await page.keyboard.press('ControlOrMeta+A');
            await page.keyboard.type(invalidYear);
            await page.keyboard.press('Enter');
            await expect(draftYear).toHaveAttribute('aria-invalid', 'true');
            await expect(canonical).toHaveValue(`${year}-09`);
            await page.keyboard.press('Escape');
            await expect(page.locator('#filter-month-panel')).toBeHidden();
            await expect(trigger).toBeFocused();
            await expect(draftYear).toBeDisabled();

            const pattern = '**/transactions/?**';
            const failFetch = route => route.request().resourceType() === 'fetch'
                ? route.abort('failed') : route.continue();
            await page.route(pattern, failFetch);
            const search = page.locator('#filter-search');
            await search.focus();
            await page.keyboard.type('September');
            await page.keyboard.press('Enter');
            const apply = page.locator('#transaction-apply-filters');
            await expect(apply).toBeVisible();
            await expect(canonical).toHaveValue(`${year}-09`);
            await page.unroute(pattern, failFetch);

            // A nameless month-panel draft must never veto this real native GET.
            // The successfully submitted filter still comes from its ISO input.
            const submitted = page.waitForRequest(request => request.method() === 'GET'
                && request.resourceType() === 'document'
                && new URL(request.url()).pathname === '/transactions/');
            await apply.press('Enter');
            const destination = new URL((await submitted).url());
            expect(destination.searchParams.get('month')).toBe(`${year}-09`);
            expect(destination.searchParams.get('q')).toBe('September');
            expect(destination.searchParams.has('year')).toBe(false);
            await expect(page).toHaveURL(url => url.pathname === '/transactions/'
                && url.searchParams.get('month') === `${year}-09`
                && url.searchParams.get('q') === 'September');
            await expect(page.locator('#transaction-results')).toContainText('September record');
            await expect(page.locator('#transaction-results')).not.toContainText('October record');
        }
    });
}
