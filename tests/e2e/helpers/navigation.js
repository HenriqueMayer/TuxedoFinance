// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const { expect } = require('@playwright/test');

function requestPath(value) {
    const url = new URL(value);
    return url.pathname + url.search;
}

async function contextualTarget(link, expectedPath, origin) {
    const target = new URL(await link.getAttribute('href'), link.page().url());
    if (expectedPath instanceof RegExp) expect(target.pathname).toMatch(expectedPath);
    else expect(target.pathname).toBe(expectedPath);
    expect(target.searchParams.get('next')).toBe(origin);
    return target;
}

async function expectContextualDestination(page, expectedPath, origin) {
    await expect(page).toHaveURL(url => url.pathname === expectedPath && url.searchParams.get('next') === origin);
}

module.exports = { requestPath, contextualTarget, expectContextualDestination };
