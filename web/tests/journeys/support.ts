import { expect, type Page } from "@playwright/test";

/** The user that tests/journeys/serve.sh creates. */
export const USER = { username: "journey", password: "journey-passphrase-42" };

/** Sign in through the page, as the owner does. */
export async function signIn(page: Page, path = "/") {
  await page.goto(path);
  await page.getByLabel("Username").fill(USER.username);
  await page.getByLabel("Password").fill(USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

/** Wait until every running animation has ended, so sizes and positions are final. */
export async function settled(page: Page) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
}
