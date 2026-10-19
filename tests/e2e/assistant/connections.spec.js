// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test, expect} = require('@playwright/test');

async function signup(page, info) {
    const response = await page.request.get('/accounts/signup/');
    const token = (await response.text()).match(/name="csrfmiddlewaretoken" value="([^"]+)"/)[1];
    const name = `connection-${info.workerIndex}-${Date.now()}`;
    const created = await page.request.post('/accounts/signup/', {form: {
        csrfmiddlewaretoken: token, username: name, email: `${name}@example.test`,
        password1: 'Tuxedo-E2E-2026!', password2: 'Tuxedo-E2E-2026!',
    }, headers: {Referer: response.url()}, maxRedirects: 0});
    expect(created.status()).toBe(302);
}

for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    test(`Assistant connection preparation is local and keyboard accessible (${theme}, ${width})`, async ({page}, info) => {
        const external = [];
        const origin = new URL(info.project.use.baseURL).origin;
        page.on('request', request => { if (new URL(request.url()).origin !== origin) external.push(request.url()); });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        await page.setViewportSize({width, height: 844});
        await signup(page, info);
        await page.goto('/accounts/settings/');
        const link = page.getByRole('link', {name: 'Assistant settings', exact: true});
        await link.focus();
        await link.press('Enter');
        await expect(page).toHaveURL(/\/assistant\/connections\/$/);
        await expect(page.getByRole('heading', {name: 'Assistant settings', exact: true})).toBeVisible();
        await expect(page.getByRole('button', {name: 'Continue with ChatGPT', exact: true})).toBeDisabled();
        await expect(page.getByText('No ChatGPT account is linked.', {exact: true})).toBeVisible();
        await expect(page.locator('main')).toContainText('Sending messages remains unavailable');
        await expect(page.locator('main')).toContainText('Real sign-in is disabled');
        const geometry = await page.locator('main').evaluate(main => ({scroll: main.scrollWidth, width: main.clientWidth}));
        expect(geometry.scroll).toBeLessThanOrEqual(geometry.width);
        if (width < 1024) {
            const note = page.getByText('No ChatGPT account is linked.', {exact: true});
            await note.scrollIntoViewIfNeeded();
            const bottom = (await note.boundingBox()).y + (await note.boundingBox()).height;
            const dock = await page.locator('.app-bottom-navigation').boundingBox();
            expect(bottom).toBeLessThanOrEqual(dock.y);
        }
        await page.screenshot({path: info.outputPath(`assistant-connections-${theme}-${width}.png`)});
        // Connection settings are ordinary navigation: chat must not bypass a
        // financial form's deliberate departure confirmation or lose its draft.
        await page.goto('/transactions/create/');
        const title = page.locator('#id_title');
        await title.fill('Keep this draft before account settings');
        const launcher = page.getByRole('button', {name: 'Open Tuxedo assistant', exact: true});
        await launcher.press('Enter');
        const panel = page.locator('#assistant-panel');
        await panel.getByRole('link', {name: 'Assistant settings', exact: true}).press('Enter');
        await expect(page.locator('#departure-confirm')).toBeVisible();
        await page.locator('[data-departure-stay]').press('Enter');
        await expect(page).toHaveURL(/\/transactions\/create\/$/);
        await expect(title).toHaveValue('Keep this draft before account settings');
        await expect(panel).toBeHidden();
        await launcher.press('Enter');
        await panel.getByRole('link', {name: 'Assistant settings', exact: true}).press('Enter');
        await page.locator('[data-departure-leave]').press('Enter');
        await expect(page).toHaveURL(/\/assistant\/connections\/$/);
        expect(external).toEqual([]);
    });
}

test('Assistant connection page retains native Portuguese reading without JavaScript', async ({browser}, info) => {
    const context = await browser.newContext({javaScriptEnabled: false, baseURL: info.project.use.baseURL,
        locale: 'pt-BR', viewport: {width: 390, height: 844}});
    const page = await context.newPage();
    await signup(page, info);
    await page.goto('/assistant/connections/');
    await expect(page.getByRole('heading', {name: 'Configurações do assistente', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: 'Continuar com ChatGPT', exact: true})).toBeDisabled();
    await page.screenshot({path: info.outputPath('assistant-connections-native-pt.png')});
    await context.close();
});
