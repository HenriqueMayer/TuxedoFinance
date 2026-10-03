// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test,expect}=require('@playwright/test');
const {selectChoice}=require('./helpers/forms');

async function post(page,path,values){
    const response=await page.request.get(path),csrf=(await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const saved=await page.request.post(path,{form:{csrfmiddlewaretoken:csrf,...values},headers:{Referer:response.url()},maxRedirects:0});
    const errors=(await saved.text()).match(/<p[^>]*data-field-error[^>]*>.*?<\/p>/g);
    expect(saved.status(),`${path}: ${errors||'unexpected response'}`).toBe(302);
}

for(const [theme,language] of [['light','en'],['dark','pt-br']]){
    test(`card-funded redemption IOF is visible after save and without JavaScript (${theme}, ${language})`,async({page,browser},info)=>{
        await page.addInitScript(value=>localStorage.setItem('theme',value),theme);
        const username=`redemption-${info.workerIndex}-${Date.now()}`;
        await post(page,'/accounts/signup/',{username,email:`${username}@example.test`,password1:'Tuxedo-Rewards-2026!',password2:'Tuxedo-Rewards-2026!'});
        await post(page,'/banking/create/',{name:'Receiving bank'});
        await post(page,'/banking/create/',{name:'Funding bank'});
        await page.goto('/banking/accounts/create/');
        const receiving=await page.locator('#id_bank option').filter({hasText:'Receiving bank'}).getAttribute('value');
        const funding=await page.locator('#id_bank option').filter({hasText:'Funding bank'}).getAttribute('value');
        await post(page,'/banking/accounts/create/',{bank:receiving,name:'Reward account',currency:'BRL',opening_balance:'0'});
        await post(page,'/banking/accounts/create/',{bank:funding,name:'IOF account',currency:'USD',opening_balance:'100'});
        await page.goto('/banking/credit-cards/create/');
        const account=await page.locator('#id_account option').filter({hasText:'IOF account'}).getAttribute('value');
        await post(page,'/banking/credit-cards/create/',{account,name:'IOF card',card_type:'PHYSICAL',closing_day:'20',due_day:'28'});
        await post(page,'/banking/loyalty/create/',{name:'Independent rewards',unit_name:'Miles'});
        await page.goto('/banking/loyalty-entries/create/');
        const program=await page.locator('#id_program option').last().getAttribute('value');
        await post(page,'/banking/loyalty-entries/create/',{program,direction:'CREDIT',kind:'ADJUSTMENT',amount:'1000',date:'2026-09-01'});
        await post(page,'/banking/exchange-rates/create/',{from_currency:'USD',to_currency:'BRL',rate:'5',effective_date:'2026-09-01'});
        await page.context().addCookies([{name:'django_language',value:language,url:info.project.use.baseURL}]);
        await page.goto('/banking/rewards/redeem/');
        await expect(page.locator('html')).toHaveAttribute('lang',language);
        await selectChoice(page.locator('#id_program-search'),program);
        await page.locator('#id_points').fill('100');
        await selectChoice(page.locator('#id_target_account-search'),{label:'Receiving bank - Reward account (BRL)'});
        await page.locator('#id_target_amount').fill('25');await page.locator('#id_iof_amount').fill('2.50');
        await selectChoice(page.locator('#id_iof_credit_card-search'),{label:'IOF card'});
        await page.locator('#id_date').fill('21/09/2026');
        await page.locator('#id_notes').fill('Redemption reference');
        const save=page.getByRole('button',{name:language==='en'?'Save':'Salvar',exact:true});
        await page.locator('#id_points').fill('1001');await save.press('Enter');
        await expect(page.locator('[data-field-error]')).toContainText(language==='en'?'The program does not have enough points.':'O programa não tem pontos suficientes.');
        await expect(page.locator('#id_iof_credit_card')).not.toHaveValue('');await expect(page.locator('#id_iof_amount')).toHaveValue('2.50');
        await page.locator('#id_points').fill('100');await save.press('Enter');
        await expect(page).toHaveURL(new RegExp(`/banking/${receiving}/#reward-redemptions$`));
        const history=page.locator('#reward-redemptions');
        await expect(history).toContainText(language==='en'?'IOF on reward redemption':'IOF sobre resgate de pontos');
        await expect(history).toContainText('IOF card');await expect(history).toContainText(/USD 2[,.]50/);
        await expect(history).toContainText(/\+BRL 25[,.]00/);
        await expect(history).toContainText('28/10/2026');await expect(history).toContainText('Redemption reference');
        await history.screenshot({path:info.outputPath(`redemption-${theme}.png`)});
        await page.goto('/dashboard/reports/?instrument_month=2026-10');
        const mark=page.locator('#instrument-activity [data-chart-layer="instrument-interactions"] [data-point]').first();
        await mark.focus();await page.keyboard.press('Control');
        const composition=page.getByRole('region',{name:language==='en'?'Composition details':'Detalhes da composição',exact:true});
        await expect(composition).toContainText('IOF');await expect(composition).toContainText(/BRL 12[,.]50/);
        const source=composition.getByRole('link');
        await expect(source).toHaveAttribute('href',/\/banking\/rewards\/\d+\/edit\/$/);
        await source.press('Enter');
        await expect(page.getByRole('form',{name:language==='en'?'Edit redemption':'Editar resgate',exact:true})).toBeVisible();
        await page.goto('/transactions/');
        const row=page.locator('li').filter({has:page.getByText(language==='en'?'IOF on reward redemption':'IOF sobre resgate de pontos',{exact:true})});
        await expect(row).toContainText(/USD 2[,.]50/);
        await expect(row.getByRole('link',{name:language==='en'?'Edit':'Editar',exact:true})).toHaveCount(0);
        await expect(row.getByRole('link',{name:language==='en'?'Delete':'Excluir',exact:true})).toHaveCount(0);
        await row.getByRole('link',{name:language==='en'?'View redemption':'Ver resgate',exact:true}).press('Enter');
        await history.getByRole('link',{name:language==='en'?'Edit redemption':'Editar resgate',exact:true}).press('Enter');
        const edit=page.getByRole('form',{name:language==='en'?'Edit redemption':'Editar resgate',exact:true});
        await expect(edit.locator('#id_redemption-iof_credit_card-search')).toHaveValue('IOF card');
        await edit.locator('#id_redemption-points').fill('1001');await edit.getByRole('button',{name:language==='en'?'Save':'Salvar',exact:true}).press('Enter');
        await expect(page.locator('[data-field-error]')).toContainText(language==='en'?'The program does not have enough points.':'O programa não tem pontos suficientes.');
        await expect(edit.locator('#id_redemption-iof_credit_card-search')).toHaveValue('IOF card');
        await edit.locator('#id_redemption-points').fill('100');
        await selectChoice(edit.locator('#id_redemption-iof_account-search'),{label:'Funding bank - IOF account (USD)'});
        await expect(edit.locator('#id_redemption-iof_credit_card')).toHaveValue('');
        await edit.locator('#id_redemption-iof_amount').fill('0');
        await expect(edit.locator('#id_redemption-iof_account-search')).toBeHidden();
        await edit.locator('#id_redemption-iof_amount').fill('3.75');
        await expect(edit.locator('#id_redemption-iof_account')).toHaveValue('');
        await selectChoice(edit.locator('#id_redemption-iof_credit_card-search'),{label:'IOF card'});
        await edit.locator('#id_redemption-iof_credit_card-search').press('Tab');
        await expect(edit.locator('#id_redemption-iof_credit_card-search').locator('..').getByRole('button')).toBeFocused();
        await page.keyboard.press('Tab');await expect(edit.locator('#id_redemption-date')).toBeFocused();
        await page.screenshot({path:info.outputPath(`redemption-inline-${theme}.png`)});
        await edit.getByRole('button',{name:language==='en'?'Save':'Salvar',exact:true}).press('Enter');
        await expect(history.locator('form')).toHaveCount(0);await expect(history).toContainText(/USD 3[,.]75/);
        await page.goto(`/banking/${funding}/`);
        await expect(page.locator('#reward-redemptions')).toContainText('IOF card');
        const invoices=page.locator('section').filter({has:page.getByRole('heading',{name:language==='en'?'Credit card invoices':'Faturas de cartão de crédito',exact:true})});
        await expect(invoices).toContainText(/USD 3[,.]75/);
        await page.reload();await expect(invoices.locator('li')).toHaveCount(1);
        const native=await browser.newContext({javaScriptEnabled:false,storageState:await page.context().storageState()});
        try{
            const p=await native.newPage();await p.goto(`/banking/${receiving}/`);
            await expect(p.locator('#reward-redemptions')).toContainText('IOF card');
            await expect(p.locator('#reward-redemptions')).toContainText('28/10/2026');
            await p.getByRole('link',{name:language==='en'?'Edit redemption':'Editar resgate',exact:true}).click();
            const nativeEdit=p.getByRole('form',{name:language==='en'?'Edit redemption':'Editar resgate',exact:true});
            await expect(nativeEdit.locator('#id_redemption-iof_credit_card option:checked')).toHaveText('IOF card');
            await nativeEdit.locator('#id_redemption-iof_amount').fill('4.25');
            await nativeEdit.getByRole('button',{name:language==='en'?'Save':'Salvar',exact:true}).click();
            await expect(p.locator('#reward-redemptions')).toContainText(/USD 4[,.]25/);
        }finally{await native.close();}
    });
}
