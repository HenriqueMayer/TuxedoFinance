// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');
async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const csrf = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const username = `previous-${info.workerIndex}-${Date.now()}`;
    const saved = await page.request.post('/accounts/signup/', {form: {csrfmiddlewaretoken: csrf, username, email: username+'@example.test', password1:'Tuxedo-E2E-2026!',password2:'Tuxedo-E2E-2026!'}, headers:{Referer:response.url()},maxRedirects:0});
    expect(saved.status()).toBe(302);
}
for (const theme of ['light','dark']) {
    test(`previous screen restores unsent fields and only one context (${theme})`, async ({page}, info) => {
        await signup(page,info);
        await page.goto('/sandbox/');
        await page.evaluate(theme => {localStorage.setItem('theme',theme);document.documentElement.classList.toggle('dark',theme==='dark');},theme);
        await page.locator('#id_draft_name').fill('Return test');
        await page.getByRole('button', {name: 'Save draft', exact:true}).click();
        await expect(page).toHaveURL(/\/sandbox\/drafts\/\d+\/$/);
        const draftUrl = page.url();
        const salary = page.locator('#id_gross_salary');
        await salary.fill('4321');
        await page.locator('[data-add-variable]').click();
        await page.locator('[name="variable_label"]').last().fill('Unsent expense');
        await page.locator('[name="variable_value"]').last().fill('invalid');
        await salary.focus();
        await page.keyboard.press('End');
        await page.getByRole('link', {name:'Delete draft', exact:true}).click();
        await expect(page.locator('[data-previous-workspace]')).toBeVisible();
        const posts=[];page.on('request', r=>{if(r.method()==='POST')posts.push(r.url());});
        await page.locator('[data-previous-workspace]').press('Enter');
        await expect(salary).toHaveValue('4321');
        await expect(page.locator('[name="variable_label"]').last()).toHaveValue('Unsent expense');
        await expect(page.locator('[name="variable_value"]').last()).toHaveValue('invalid');
        await expect(salary).toBeFocused();
        expect(posts).toEqual([]);
        await expect(page.locator('[data-workspace-restored]')).toBeVisible();
        const state = await page.evaluate(()=>JSON.parse(sessionStorage.getItem('tuxedo.previous-workspace.v1')));
        expect(state.previous.url).toBe(new URL(draftUrl).pathname + 'delete/');
        expect(state.resume).toBeUndefined();
        await page.screenshot({path:info.outputPath(`previous-${theme}.png`)});
    });
}
test('investment simulation is last and previous view retains its query',async({page},info)=>{
    await signup(page,info);await page.goto('/investments/?section=cash');
    const nav=page.getByRole('navigation',{name:'Investment sections'});
    await expect(nav.getByRole('link').last()).toHaveText('Simulate returns');
    await nav.getByRole('link').last().click();
    await page.locator('[data-previous-workspace]').click();
    await expect(page).toHaveURL(/\/investments\/\?section=cash$/);
    await expect(nav.getByRole('link',{name:'Remunerated cash'})).toHaveAttribute('aria-current','page');
});
test('previous context survives reload, stays in its tab and clears for another user', async ({page,context},info)=>{
    await signup(page,info);await page.goto('/investments/?section=cash');
    await page.getByRole('navigation',{name:'Investment sections'}).getByRole('link',{name:'Simulate returns'}).click();
    await expect(page.locator('[data-previous-workspace]')).toBeVisible();
    await page.reload();await expect(page.locator('[data-previous-workspace]')).toBeVisible();
    const other=await context.newPage();await other.goto('/sandbox/');
    await expect(other.locator('[data-previous-workspace]')).toBeHidden();await other.close();
    await page.goto('/accounts/signup/');
    await signup(page,info);await page.goto('/sandbox/');
    await expect(page.locator('[data-previous-workspace]')).toBeHidden();
    expect(await page.evaluate(()=>sessionStorage.getItem('tuxedo.previous-workspace.v1'))).toBeNull();
});

test('unsent investment choices, amount and date return without saving an operation',async({page},info)=>{
    await signup(page,info);
    const response=await page.request.get('/investments/assets/create/');
    const csrf=(await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved=await page.request.post('/investments/assets/create/',{form:{csrfmiddlewaretoken:csrf,name:'Temporary asset',code:'TMP',valuation_mode:'MONETARY',asset_class:'LIQUIDITY',currency:'BRL',opening_balance:'0',opening_quantity:'0',opening_unit_price:'0'},headers:{Referer:response.url()},maxRedirects:0});
    expect(saved.status()).toBe(302);
    await page.goto('/investments/create/');
    await page.locator('#id_asset-search').fill('Temporary asset');
    await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    await page.locator('#id_kind').selectOption('DEPOSIT');
    await page.locator('#id_amount').fill('123.45');await page.locator('#id_date').fill('21/09/2026');
    const asset=await page.locator('#id_asset').inputValue();
    await page.getByRole('link', {name:'Cancel',exact:true}).click();
    await expect(page.locator('[data-previous-workspace]')).toBeVisible();
    const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
    await page.locator('[data-previous-workspace]').click();
    await expect(page.locator('#id_asset')).toHaveValue(asset);
    await expect(page.locator('#id_kind')).toHaveValue('DEPOSIT');
    await expect(page.locator('#id_amount')).toHaveValue('123.45');
    await expect(page.locator('#id_date')).toHaveValue('21/09/2026');
    await expect(page.locator('#money-fields')).toBeVisible();await expect(page.locator('#funding-section')).toBeVisible();
    expect(posts).toEqual([]);
});

test('simulation returns with month overrides beyond the initial twelve rows', async ({page}, info) => {
    await signup(page, info);
    await page.goto('/sandbox/simulation/');
    await page.locator('#id_draft_name').fill('Twenty four months');
    await page.getByRole('button', {name:'Save draft',exact:true}).click();
    await page.locator('#id_months').fill('24');
    await page.locator('summary').filter({hasText: 'Change individual months'}).click();
    await page.getByRole('button', {name: 'Update month rows'}).click();
    await expect(page.locator('[name="contribution_23"]')).toHaveCount(1);
    const months = page.locator('details').filter({has: page.getByText('Change individual months', {exact: true})});
    if (!(await months.getAttribute('open') !== null)) await months.locator('summary').click();
    await expect(page.locator('[name="contribution_23"]')).toBeVisible();
    await page.locator('[name="contribution_23"]').fill('456.78');
    await page.getByRole('link', {name: 'Delete draft', exact:true}).click();
    await page.locator('[data-previous-workspace]').click();
    await expect(page.locator('#id_months')).toHaveValue('24');
    await expect(page.locator('[name="contribution_23"]')).toHaveValue('456.78');
});
