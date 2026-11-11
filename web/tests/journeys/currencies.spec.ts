import { expect, test } from "@playwright/test";
import { choose, chooseValue, freshUser, prepareWallet } from "./support";

test("an account in another currency counts in the totals after its rate", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/wallet");

  // A new account chooses its currency.
  await page.getByRole("link", { name: "New account" }).click();
  const create = page.getByRole("dialog", { name: "New account" });
  await create.getByLabel("Bank").fill("Wise");
  await create.getByLabel("Name").fill("Dollars");
  await chooseValue(create.getByLabel("Currency"), "USD");
  await create.getByLabel("Opening balance (USD)").fill("100");
  await create.getByRole("button", { name: /Create/ }).click();
  await expect(create).toBeHidden();
  await expect(page.getByRole("link", { name: /Dollars/ })).toContainText("$100,00");

  // Without a rate, the net worth leaves the dollars out and says so.
  await page.goto("/");
  const worth = page.getByRole("link", { name: /Net worth/ });
  await expect(worth).toContainText("R$ 1.000,00");
  await worth.click();
  const detail = page.getByRole("dialog", { name: "Net worth" });
  await expect(detail.getByText(/Amounts in USD have no exchange rate/)).toBeVisible();
  await detail.getByRole("link", { name: "Record a rate" }).click();

  // The rate is typed once and the totals follow.
  const rates = page.getByRole("dialog", { name: "Exchange rates" });
  await expect(rates.getByText("Without a rate: USD.")).toBeVisible();
  await expect(rates.getByLabel("Currency")).toHaveAttribute("data-value", "USD");
  await rates.getByLabel(/1 unit in BRL/).fill("abc");
  await rates.getByRole("button", { name: "Record rate" }).click();
  await expect(rates.getByText("Enter a rate greater than zero.")).toBeVisible();
  await rates.getByLabel(/1 unit in BRL/).fill("5,25");
  await rates.getByRole("button", { name: "Record rate" }).click();
  await expect(rates.getByText("1 USD = 5.25 BRL")).toBeVisible();
  await expect(rates.getByText("Without a rate: USD.")).toBeHidden();
  await page.keyboard.press("Escape");
  await expect(rates).toBeHidden();
  await expect(worth).toContainText("R$ 1.525,00");

  // A transfer between the currencies asks for what arrives.
  await page.goto("/wallet");
  await page.getByRole("link", { name: "Transfer" }).click();
  const transfer = page.getByRole("dialog", { name: "Transfer" });
  await choose(transfer.getByLabel("From"), "Nubank · Conta");
  await choose(transfer.getByLabel("To", { exact: true }), "Wise · Dollars");
  await transfer.getByLabel("Amount (BRL)").fill("525");
  await transfer.getByRole("button", { name: "Transfer" }).click();
  await expect(transfer.getByLabel("Amount received (USD)")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await transfer.getByLabel("Amount received (USD)").fill("100");
  await transfer.getByRole("button", { name: "Transfer" }).click();
  await expect(transfer).toBeHidden();
  await expect(page.getByRole("link", { name: /Dollars/ })).toContainText("$200,00");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 475,00");

  // The rates are reached from Settings too, and a rate can be deleted.
  await page.goto("/wallet?w=settings");
  await page
    .getByRole("dialog", { name: "Settings" })
    .getByRole("link", { name: "Exchange rates" })
    .click();
  await rates.getByRole("button", { name: "Delete" }).click();
  await expect(rates.getByText("No exchange rate yet.")).toBeVisible();
});
