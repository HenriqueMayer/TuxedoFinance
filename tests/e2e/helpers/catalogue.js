// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {resolve, sep} = require('node:path');
const {projectRoot} = require('./paths');

const documents = new Set([
    'docs/design-system.html', 'docs/design-system.css', 'docs/design-system.js',
    'docs/design-system-layers.js', 'docs/design-system-calendar.js',
]);
const types = {html: 'text/html', css: 'text/css', js: 'application/javascript',
    woff2: 'font/woff2', png: 'image/png', jpg: 'image/jpeg', ico: 'image/x-icon'};

async function openCatalogue(page, {hash = '', theme, fixedTime, waitForFonts = false} = {}) {
    // Calendar scenarios freeze Date only; timers, native events and RAF stay real.
    if (fixedTime !== undefined) await page.clock.setFixedTime(fixedTime);
    if (theme !== undefined) await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await page.route('**/catalogue/**', async route => {
        const pathname = new URL(route.request().url()).pathname;
        const name = pathname.slice('/catalogue/'.length);
        if (!pathname.startsWith('/catalogue/')
                || (!documents.has(name) && !name.startsWith('static/'))
                || name.split('/').includes('..')) return route.abort();
        const path = resolve(projectRoot, name);
        if (!path.startsWith(projectRoot + sep)) return route.abort();
        await route.fulfill({path, contentType: types[name.split('.').pop()]});
    });
    await page.goto(`/catalogue/docs/design-system.html${hash}`);
    if (waitForFonts) await page.evaluate(() => document.fonts.ready);
}

module.exports = {openCatalogue};
