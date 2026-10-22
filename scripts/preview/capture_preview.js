const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('@playwright/test');

const baseURL = process.env.PREVIEW_BASE_URL;
const outputRoot = process.env.PREVIEW_OUTPUT_DIR;
const password = process.env.PREVIEW_PASSWORD;

if (!baseURL || !outputRoot || !password) {
    throw new Error('PREVIEW_BASE_URL, PREVIEW_OUTPUT_DIR and PREVIEW_PASSWORD are required.');
}

const profiles = [
    { language: 'en', username: 'preview-en', locale: 'en-US' },
    { language: 'pt-br', username: 'preview-pt', locale: 'pt-BR' },
];

const screens = [
    ['dashboard-light.png', '/dashboard/'],
    ['reports-light.png', '/analytics/'],
    ['analytics-investments-light.png', '/analytics/investments/'],
    ['transactions-light.png', '/transactions/'],
    ['new-entry-light.png', '/transactions/create/'],
    ['banking-light.png', '/banking/'],
    ['investments-light.png', '/investments/'],
    ['planning-light.png', '/planning/'],
];

const screenshotOptions = {
    animations: 'disabled',
    caret: 'hide',
};

async function settle(page) {
    await page.waitForLoadState('networkidle');
    // Keep hover navigation and contextual help closed in the public tour.
    await page.mouse.move(4, 80);
    await page.evaluate(async () => {
        if (document.fonts && document.fonts.ready) await document.fonts.ready;
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
        window.scrollTo(0, 0);
    });
    await page.waitForTimeout(180);
    if (await page.evaluate(() => window.scrollX !== 0 || window.scrollY !== 0)) {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(80);
    }
    const scrollPosition = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
    if (scrollPosition.x !== 0 || scrollPosition.y !== 0) {
        throw new Error(`Page would be captured away from the origin: ${JSON.stringify(scrollPosition)}`);
    }
}

async function setTheme(page, theme) {
    await page.evaluate(value => localStorage.setItem('theme', value), theme);
}

async function login(page, profile) {
    await page.goto(`${baseURL}/accounts/login/`);
    if (profile.language === 'pt-br') {
        await page.locator('#language-select-public').selectOption('pt-br');
        await page.waitForURL(`${baseURL}/accounts/login/`);
    }
    await page.locator('#id_username').fill(profile.username);
    await page.locator('#id_password').fill(password);
    await Promise.all([
        page.waitForURL(`${baseURL}/dashboard/`),
        page.locator('form button[type="submit"]').click(),
    ]);
    await page.goto(`${baseURL}/dashboard/`);
    await settle(page);
    const actualLanguage = await page.locator('html').getAttribute('lang');
    if (actualLanguage !== profile.language) {
        throw new Error(`Expected ${profile.language}, received ${actualLanguage}.`);
    }
}

async function captureProfile(browser, profile) {
    const context = await browser.newContext({
        // Capture the full workspace, including its left-edge navigation.
        viewport: { width: 1440, height: 1000 },
        deviceScaleFactor: 1,
        locale: profile.locale,
        colorScheme: 'light',
        reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text());
    });

    await login(page, profile);
    const outputDirectory = path.join(outputRoot, profile.language);
    await fs.mkdir(outputDirectory, { recursive: true });

    for (const theme of ['light', 'dark']) {
        await setTheme(page, theme);
        for (const [filename, route] of screens) {
            await page.goto(`${baseURL}${route}`);
            if (route === '/banking/') {
                // Demonstrate the real internal workspace, not an artificially
                // expanded collection of every institution in the overview.
                await page.locator('[data-bank-open]').filter({ hasText: 'Tuxedo Demo Bank' }).click();
                await page.locator('.bank-workspace-panel').waitFor();
            } else if (route === '/planning/') {
                await page.locator('[data-monthly-available]').waitFor();
            } else if (route === '/transactions/create/') {
                // Expose the real conditional payment board without submitting
                // an entry or replacing native controls with staged artwork.
                await page.locator('#id_transaction_type input[value="EXPENSE"]').check();
                await page.locator('#id_payment_channel input[value="CREDIT_CARD"]').check();
                await page.locator('#credit-card-fields .payment-choice-art').first().waitFor();
            }
            await settle(page);
            await page.screenshot({
                path: path.join(outputDirectory, filename.replace('-light.png', `-${theme}.png`)),
                ...screenshotOptions,
            });
        }
    }

    if (errors.length) {
        throw new Error(`Browser errors for ${profile.language}:\n${errors.join('\n')}`);
    }
    await context.close();
}

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        for (const profile of profiles) await captureProfile(browser, profile);
    } finally {
        await browser.close();
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
