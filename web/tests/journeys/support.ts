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

let counter = 0;

/**
 * Create a new user and sign in as it, so a journey starts with no records
 * and does not depend on another journey.
 */
export async function freshUser(page: Page, path = "/") {
  counter += 1;
  const username = `owner-${Date.now()}-${counter}`;
  await page.goto("/login");
  const status = await page.evaluate(async (name) => {
    await fetch("/api/session");
    const token = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
    const response = await fetch("/api/session/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify({
        username: name,
        email: `${name}@example.test`,
        password: "journey-passphrase-42",
      }),
    });
    return response.status;
  }, username);
  expect(status).toBe(200);
  await page.goto(path);
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

/** Call the API as the signed-in user of the page. Used to prepare records quickly. */
export async function apiPost<T>(page: Page, path: string, body: unknown): Promise<T> {
  const result = await page.evaluate(
    async ([url, payload]) => {
      const token = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
      const response = await fetch(url as string, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify(payload),
      });
      return { status: response.status, body: await response.json() };
    },
    [path, body] as const,
  );
  expect(result.status, JSON.stringify(result.body)).toBe(200);
  return result.body as T;
}

/** An account, a card and the first category of a fresh user. */
export async function prepareWallet(page: Page) {
  const account = await apiPost<{ id: string }>(page, "/api/banking/accounts", {
    bank_name: "Nubank",
    name: "Conta",
    opening_balance: "1000.00",
  });
  const card = await apiPost<{ id: string }>(page, "/api/banking/credit-cards", {
    account: account.id,
    name: "Platinum",
    closing_day: 24,
    due_day: 1,
  });
  const categories = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  return { account: account.id, card: card.id, category: categories[0].id as number };
}
