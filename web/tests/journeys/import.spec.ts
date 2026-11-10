import { expect, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

/** The first days of the current month, so every row is on or before today. */
function day(number: number) {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return {
    iso: `${now.getFullYear()}-${month}-0${number}`,
    text: `0${number}/${month}/${now.getFullYear()}`,
  };
}

test("a CSV statement is read, reviewed, confirmed and undone", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  // One row of the statement is already recorded, and one description is known.
  await apiPost(page, "/api/ledger/transactions", {
    title: "Feira",
    amount: "80.00",
    date: day(1).iso,
    category_id: categories.find((item) => item.name === "Groceries")?.id,
    instrument: wallet.account,
  });
  const csv = [
    "Data;Histórico;Valor;Identificador",
    `${day(1).text};FEIRA LIVRE;-80,00;a1`,
    `${day(1).text};Feira;-45,50;a2`,
    `${day(1).text};Salário;5.000,00;a3`,
    `${day(1).text};Tarifa;-12,00;a4`,
  ].join("\n");

  await page.goto("/transactions?month=all");
  // The import is a rare action: it is in the menu of the page.
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Import statement" }).click();
  const start = page.getByRole("dialog", { name: "Statement import" });
  await start.getByRole("button", { name: "Read the file" }).click();
  await expect(start.getByText("Choose a file.")).toBeVisible();
  // The file is given to the field in the page, as a chosen file would be.
  await start.getByLabel("File").evaluate((input: HTMLInputElement, text) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([text], "extrato.csv", { type: "text/csv" }));
    input.files = transfer.files;
  }, csv);
  await start.getByRole("button", { name: "Read the file" }).click();

  // The account has an opening balance without a date: the import says so and leads to it.
  const window = page.getByRole("dialog", { name: "Statement import" });
  await expect(window.getByText(/opening balance without a date/)).toBeVisible();
  const batch = new URL(page.url()).searchParams.get("w");
  await window.getByRole("link", { name: "Open the account" }).click();
  const account = page.getByRole("dialog", { name: "Account" });
  await account.getByText("Edit account").click();
  await account.getByLabel(/Opening date/).fill(`${new Date().getFullYear() - 1}-01-01`);
  await account.getByRole("button", { name: "Save" }).click();
  await page.goto(`/transactions?month=all&w=${batch}`);

  // The columns are proposed from the names in the file.
  await expect(window.getByText(/opening balance without a date/)).toBeHidden();
  await expect(window.getByLabel("Date", { exact: true })).toHaveValue("Data");
  await expect(window.getByLabel("Description")).toHaveValue("Histórico");
  await expect(window.getByLabel("Amount")).toHaveValue("Valor");
  await expect(window.getByLabel("Dates are written as")).toHaveValue("%d/%m/%Y");
  await expect(window.getByLabel("Decimals use")).toHaveValue(",");
  await window.getByRole("button", { name: "Read the rows" }).click();

  // The recorded row is matched and the known description has its category.
  await expect(window.getByLabel("Decision for FEIRA LIVRE")).toHaveValue("MATCH");
  await expect(window.getByLabel("Decision for Feira", { exact: true })).toHaveValue("CREATE");
  await expect(window.getByLabel("Category: Feira", { exact: true })).not.toHaveValue("");
  await expect(window.getByText("2 rows wait for a decision.")).toBeVisible();
  await expect(window.getByRole("button", { name: "Confirm the import" })).toBeDisabled();

  await window.getByLabel("Decision for Salário").selectOption("CREATE");
  await window.getByLabel("Category: Salário").selectOption({ label: "Services" });
  await expect(window.getByText("1 row waits for a decision.")).toBeVisible();
  await window.getByRole("button", { name: "Skip the rows without a decision" }).click();
  await expect(window.getByText("Every row has a decision.")).toBeVisible();
  await expect(window.getByLabel("Decision for Tarifa")).toHaveValue("SKIP");

  await window.getByRole("button", { name: "Confirm the import" }).click();
  await expect(window.getByText("3 rows were imported.")).toBeVisible();
  await expect(window.getByText("1 row was skipped.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();

  // Two entries are new; the matched one was not repeated.
  const list = page.getByRole("main");
  await expect(list.getByText("Salário")).toBeVisible();
  await expect(list.getByText("Feira", { exact: true })).toHaveCount(2);
  await expect(list.getByText("FEIRA LIVRE")).toHaveCount(0);
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 5.874,50");

  // The import is found again and undone.
  await page.goto("/transactions?month=all&w=import");
  await start.getByRole("link", { name: /extrato.csv/ }).click();
  await window.getByRole("button", { name: "Undo this import" }).click();
  await expect(window.getByText(/This import was undone/)).toBeVisible();
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 920,00");
});
