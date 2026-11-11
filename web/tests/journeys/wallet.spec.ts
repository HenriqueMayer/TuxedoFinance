import { expect, test } from "@playwright/test";
import { apiPost, choose, freshUser, prepareWallet } from "./support";

test("the owner creates an account and a card in the Wallet", async ({ page }) => {
  await freshUser(page, "/wallet");
  await expect(page.getByText("No accounts yet")).toBeVisible();

  await page.getByRole("link", { name: "New account" }).click();
  let window = page.getByRole("dialog", { name: "New account" });
  await window.getByLabel("Bank").fill("Itaú");
  await window.getByLabel("Account name").fill("Corrente");
  await window.getByLabel(/Opening balance/).fill("2.500,00");
  await window.getByRole("button", { name: "Create account" }).click();
  await expect(window).toBeHidden();

  await expect(page.getByRole("heading", { name: "Itaú" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Corrente/ })).toContainText("R$ 2.500,00");
  await expect(page.getByText("In your accounts")).toBeVisible();

  await page.getByRole("link", { name: "New card" }).click();
  window = page.getByRole("dialog", { name: "New card" });
  await window.getByLabel("Card name").fill("Visa Infinite");
  await window.getByLabel("Closing day").fill("25");
  await window.getByLabel("Due day").fill("5");
  await window.getByRole("button", { name: "Add" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByRole("link", { name: /Visa Infinite/ })).toContainText("Nothing due");
});

test("the owner pays an invoice and undoes the payment", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page, { confirmPayments: true });
  await apiPost(page, "/api/ledger/transactions", {
    title: "Mercado",
    amount: "120.00",
    category_id: wallet.category,
    instrument: wallet.card,
  });
  await apiPost(page, "/api/ledger/transactions", {
    title: "Notebook",
    amount: "900.00",
    category_id: wallet.category,
    instrument: wallet.card,
    installments: 3,
  });
  await page.goto("/wallet");

  // The card shows what is owed on the next invoice.
  const card = page.getByRole("link", { name: /Platinum/ });
  await expect(card).toContainText("R$ 420,00");
  await expect(card).toContainText("Open");
  await card.click();

  const cardWindow = page.getByRole("dialog", { name: "Card" });
  await expect(cardWindow.getByRole("link")).toHaveCount(3); // Three statements hold the installments.
  await cardWindow.getByRole("link").last().click(); // The oldest month is last.

  const invoice = page.getByRole("dialog", { name: "Invoice" });
  await expect(invoice.getByRole("link", { name: /Mercado/ })).toContainText("R$ 120,00");
  await expect(invoice.getByRole("link", { name: /Notebook/ })).toContainText("R$ 300,00");
  // The form offers the remaining amount; one press records the payment.
  await expect(invoice.getByLabel(/Amount/)).toHaveValue("420,00");
  await invoice.getByRole("button", { name: "Record payment" }).click();

  await expect(invoice.getByText("Paid", { exact: true }).first()).toBeVisible();
  await expect(invoice.getByRole("button", { name: "Record payment" })).toBeHidden();
  await expect(invoice.getByText("R$ 0,00")).toBeVisible();

  // The account behind the windows lost the paid amount.
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Account Conta/ })).toContainText("R$ 580,00");

  // Undoing the payment reopens the invoice and returns the money.
  await page.getByRole("link", { name: /Platinum/ }).click();
  await page.getByRole("dialog", { name: "Card" }).getByRole("link").last().click();
  await invoice.getByRole("button", { name: "Undo" }).click();
  await expect(invoice.getByRole("button", { name: "Record payment" })).toBeVisible();
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Account Conta/ })).toContainText("R$ 1.000,00");
});

test("a payment larger than the invoice is refused at the amount", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page, { confirmPayments: true });
  await apiPost(page, "/api/ledger/transactions", {
    title: "Mercado",
    amount: "120.00",
    category_id: wallet.category,
    instrument: wallet.card,
  });
  await page.goto("/wallet");
  await page.getByRole("link", { name: /Platinum/ }).click();
  await page.getByRole("dialog", { name: "Card" }).getByRole("link").first().click();
  const invoice = page.getByRole("dialog", { name: "Invoice" });
  await invoice.getByLabel(/Amount/).fill("500");
  await invoice.getByRole("button", { name: "Record payment" }).click();
  await expect(invoice.getByLabel(/Amount/)).toHaveAttribute("aria-invalid", "true");
  await expect(invoice.getByText("Payments cannot exceed")).toBeVisible();
});

test("the owner transfers between accounts and undoes it", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await apiPost(page, "/api/banking/accounts", {
    bank_name: "Nubank",
    name: "Reserva",
    opening_balance: "0",
  });
  await page.goto("/wallet");

  await page.getByRole("link", { name: "Transfer" }).click();
  const window = page.getByRole("dialog", { name: "Transfer" });
  await window.getByLabel("Amount", { exact: true }).fill("250");
  await choose(window.getByLabel("From", { exact: true }), "Nubank · Conta");
  await choose(window.getByLabel("To", { exact: true }), "Nubank · Reserva");
  await window.getByRole("button", { name: "Transfer" }).click();
  await expect(window).toBeHidden();

  await expect(page.getByRole("link", { name: /Account Conta/ })).toContainText("R$ 750,00");
  await expect(page.getByRole("link", { name: /Account Reserva/ })).toContainText("R$ 250,00");
  // The total of the accounts does not change with a transfer.
  await expect(page.getByText("R$ 1.000,00")).toBeVisible();

  await page.getByRole("link", { name: /Account Reserva/ }).click();
  const account = page.getByRole("dialog", { name: "Account" });
  await expect(account.getByText("+R$ 250,00")).toBeVisible();
  await account.getByRole("button", { name: "Undo" }).click();
  await expect(account.getByText("No movements yet.")).toBeVisible();
});

test("the owner corrects an account and deletes an unused one", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await apiPost(page, "/api/banking/accounts", {
    bank_name: "Itaú",
    name: "Antiga",
    opening_balance: "10",
  });
  await page.goto("/wallet");

  await page.getByRole("link", { name: /Account Conta/ }).click();
  const account = page.getByRole("dialog", { name: "Account" });
  await account.getByText("Edit account").click();
  await account.getByLabel(/Opening balance/).fill("1.200,00");
  await account.getByRole("button", { name: "Save" }).click();
  await expect(account.getByText("R$ 1.200,00").first()).toBeVisible();
  // This account has a card, so it cannot be deleted. The reason is shown.
  await account.getByRole("button", { name: "Delete", exact: true }).click();
  await account.getByRole("button", { name: "Delete for good" }).click();
  await expect(account.getByRole("alert")).toContainText("This account has records");
  await page.keyboard.press("Escape");

  await page.getByRole("link", { name: /Account Antiga/ }).click();
  await account.getByText("Edit account").click();
  await account.getByRole("button", { name: "Delete", exact: true }).click();
  await account.getByRole("button", { name: "Delete for good" }).click();
  await expect(account).toBeHidden();
  await expect(page.getByRole("heading", { name: "Itaú" })).toBeHidden();
});
