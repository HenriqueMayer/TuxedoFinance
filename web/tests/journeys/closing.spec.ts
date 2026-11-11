import { expect, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

test("the owner closes the month before: balances, result and the next limit", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  // One expense on the first day of the month before.
  const before = new Date();
  before.setDate(1);
  before.setMonth(before.getMonth() - 1);
  const iso = `${before.getFullYear()}-${String(before.getMonth() + 1).padStart(2, "0")}-01`;
  const name = new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(before);
  await apiPost(page, "/api/ledger/transactions", {
    title: "Feira",
    amount: "100.00",
    date: iso,
    category_id: categories.find((item) => item.name === "Groceries")?.id,
    instrument: wallet.account,
  });

  // Home asks for the closing of that month.
  await page.goto("/");
  await expect(page.getByText(`${name} is not closed yet.`)).toBeVisible();
  await page.getByRole("link", { name: "Close the month" }).click();
  const window = page.getByRole("dialog", { name: "Month closing" });
  await expect(window.getByText(name, { exact: true })).toBeVisible();

  // The bank shows 20 less than the records: the difference is named and adjusted.
  await expect(window.getByText("Recorded: R$ 900,00")).toBeVisible();
  const bank = window.getByLabel("At the bank: Nubank · Conta");
  // Letters do not enter a field for an amount.
  await bank.fill("abc");
  await expect(bank).toHaveValue("");
  // A minus sign alone is not a balance.
  await bank.fill("-");
  await bank.press("Enter");
  await expect(window.getByText("Enter a balance.")).toBeVisible();
  await bank.fill("880,00");
  await bank.press("Enter");
  await expect(window.getByText("Difference of -R$ 20,00.")).toBeVisible();
  await window.getByRole("button", { name: "Adjust the recorded balance" }).click();
  await expect(window.getByText("Adjusted to the bank balance.")).toBeVisible();
  await expect(window.getByText("Recorded: R$ 880,00")).toBeVisible();

  // The result of the month, and the limit from the current month on.
  await expect(window.getByText("-R$ 100,00").first()).toBeVisible();
  await expect(window.getByText("No limit is set.")).toBeVisible();
  await window.getByLabel(/Limit for each month/).fill("2.500,00");
  await window.getByRole("button", { name: `Close ${name}` }).click();
  await expect(window.getByText(/^Closed on /)).toBeVisible();
  await expect(window.getByLabel(/Limit for each month/)).toHaveValue("2.500,00");
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();

  // Home no longer asks, the limit holds, and the adjustment is in the account.
  await expect(page.getByText(`${name} is not closed yet.`)).toBeHidden();
  await expect(page.getByRole("link", { name: /Left to spend/ })).toContainText(
    "of the limit of R$ 2.500,00",
  );
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 880,00");

  // A later entry in the closed month is said, and the month can be reopened.
  await apiPost(page, "/api/ledger/transactions", {
    title: "Esquecido",
    amount: "40.00",
    date: iso,
    category_id: categories.find((item) => item.name === "Groceries")?.id,
    instrument: wallet.account,
  });
  await page.goto("/");
  await expect(page.getByText(`${name} changed after its closing.`)).toBeVisible();
  await page.getByRole("link", { name: "Review it" }).click();
  await expect(window.getByText("Its entries changed after the closing.")).toBeVisible();
  await expect(window.getByText("-R$ 140,00").first()).toBeVisible();
  await window.getByRole("button", { name: "Reopen the month" }).click();
  await expect(window.getByText(/A short review/)).toBeVisible();

  // The window moves to another month in place.
  await window.getByRole("button", { name: "Next month" }).click();
  await expect(window.getByText(name, { exact: true })).toBeHidden();
  await expect(window.getByRole("button", { name: "Next month" })).toBeDisabled();
});
