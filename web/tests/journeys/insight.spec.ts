import { expect, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

test("an item of the Wallet opens its analysis above its own window", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  const category = (name: string) => categories.find((item) => item.name === name)?.id;
  await apiPost(page, "/api/ledger/transactions", {
    title: "Salário",
    amount: "5000.00",
    transaction_type: "INCOME",
    category_id: category("Services"),
    instrument: wallet.account,
  });
  await apiPost(page, "/api/ledger/transactions", {
    title: "Cinema",
    amount: "60.00",
    category_id: category("Hobbies & Entertainment"),
    instrument: wallet.card,
  });
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
  const position = await apiPost<{ id: number }>(page, "/api/investments/positions", {
    name: "ETF global",
    institution_name: "XP",
    currency: "BRL",
    opening_balance: "1000.00",
    opening_date: iso,
  });
  await apiPost(page, "/api/investments/positions", {
    name: "Reserva",
    institution_name: "Nubank",
    currency: "BRL",
    opening_balance: "9000.00",
    opening_date: iso,
  });

  // An account: its balance month by month, and the account among the accounts.
  await page.goto(`/wallet?w=${wallet.account}`);
  const account = page.getByRole("dialog", { name: "Account" });
  await account.getByRole("button", { name: "Analysis" }).click();
  const insight = page.getByRole("dialog", { name: "Analysis" });
  await expect(page).toHaveURL(/w2=insight/);
  await expect(insight.getByText("Balance today")).toBeVisible();
  await expect(
    insight
      .getByRole("table", { name: "Balance at the end of each month" })
      .getByRole("row")
      .last(),
  ).toContainText("R$ 6.000,00");
  await expect(insight.getByRole("heading", { name: "Among your accounts" })).toBeVisible();
  // Escape closes the analysis; the window of the account stays below.
  await page.keyboard.press("Escape");
  await expect(insight).toBeHidden();
  await expect(account).toBeVisible();

  // A card: its statements and where it was used.
  await page.goto(`/wallet?w=${wallet.card.replace("credit", "card")}`);
  await page
    .getByRole("dialog", { name: "Card" })
    .getByRole("button", { name: "Analysis" })
    .click();
  await expect(insight.getByText("Owed today")).toBeVisible();
  await expect(insight.getByRole("heading", { name: "Where this card was used" })).toBeVisible();
  await expect(insight.getByText("Hobbies & Entertainment")).toBeVisible();

  // An investment: its part of everything invested, 1.000 of 10.000.
  await page.goto(`/wallet?w=investment:${position.id}`);
  await page
    .getByRole("dialog", { name: "Investment" })
    .getByRole("button", { name: "Analysis" })
    .click();
  await expect(insight.getByText("Value today")).toBeVisible();
  await expect(insight.getByText("of R$ 10.000,00 invested")).toBeVisible();
  await expect(insight.getByText("10,0%").first()).toBeVisible();
  await expect(insight.getByText("this one")).toBeVisible();
});
