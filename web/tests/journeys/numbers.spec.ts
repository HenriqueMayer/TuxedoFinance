import { expect, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

test("the owner chooses how numbers are written, and every amount follows", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  await apiPost(page, "/api/ledger/transactions", {
    title: "Salário",
    amount: "5000.00",
    transaction_type: "INCOME",
    category_id: categories.find((item) => item.name === "Services")?.id,
    instrument: wallet.account,
  });

  // A new owner has a point for thousands and a comma for decimals.
  await page.goto("/wallet");
  await expect(page.getByText(/R\$\s6\.000,00/).first()).toBeVisible();

  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings.getByRole("radio", { name: "1.234,56" })).toBeChecked();
  await settings.getByText("1,234.56").click();
  await expect(settings.getByRole("radio", { name: "1,234.56" })).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(settings).toBeHidden();

  // The page behind writes its amounts again, with the symbol of the currency as before.
  await expect(page.getByText(/R\$\s6,000\.00/).first()).toBeVisible();

  // A typed amount follows the same choice.
  await page
    .getByRole("navigation")
    .getByRole("link", { name: /Add entry/ })
    .click();
  const amount = page.getByRole("dialog", { name: "Add entry" }).getByLabel(/Amount/);
  await amount.pressSequentially("2000");
  await expect(amount).toHaveValue("2,000");
  await amount.blur();
  await expect(amount).toHaveValue("2,000.00");
  // The keys change places with the choice: the comma groups and the point starts the decimals.
  await amount.fill("");
  await amount.pressSequentially("1,500.5");
  await expect(amount).toHaveValue("1,500.5");
  // The comma key answers at once, and the number goes on from it.
  await amount.fill("");
  await amount.pressSequentially("1,");
  await expect(amount).toHaveValue("1,");
  await amount.pressSequentially("00");
  await expect(amount).toHaveValue("1,00");
  await amount.pressSequentially("0");
  await expect(amount).toHaveValue("1,000");
  // Left in the middle of a group, the number is its digits: one hundred.
  await amount.fill("");
  await amount.pressSequentially("1,00");
  await amount.blur();
  await expect(amount).toHaveValue("100.00");
  // Backspace after the decimal point deletes the point, not the digit before it.
  await amount.fill("");
  await amount.pressSequentially("1.");
  await expect(amount).toHaveValue("1.");
  await amount.press("Backspace");
  await expect(amount).toHaveValue("1");
  // Backspace after a typed comma deletes the comma alone too.
  await amount.pressSequentially(",");
  await expect(amount).toHaveValue("1,");
  await amount.press("Backspace");
  await expect(amount).toHaveValue("1");
  await page.keyboard.press("Escape");

  // The choice is saved for the owner.
  await page.reload();
  await expect(page.getByText(/R\$\s6,000\.00/).first()).toBeVisible();
});
