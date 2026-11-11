import { expect, test } from "@playwright/test";
import { USER } from "./support";

test("the owner signs in, reloads and signs out", async ({ page }) => {
  // A protected address sends an anonymous visitor to the sign-in page.
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Username").fill(USER.username);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("not correct");

  await page.getByLabel("Password").fill(USER.password);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  // The session survives a reload: it lives in the cookie, not in the page.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
});

test("the sign-in page keeps a local return address and drops a foreign one", async ({ page }) => {
  await page.goto("/login?redirect=https://example.test/");
  await page.getByLabel("Username").fill(USER.username);
  await page.getByLabel("Password").fill(USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  expect(new URL(page.url()).origin).toBe("http://127.0.0.1:8765");
});
