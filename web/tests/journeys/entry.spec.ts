import { expect, type Page, test } from "@playwright/test";
import { apiPost, choose, freshUser, prepareWallet, settled } from "./support";

const row = (page: Page, title: string) => page.getByRole("link", { name: new RegExp(title) });

test("first use: the owner creates an account and records an expense", async ({ page }) => {
  await freshUser(page, "/transactions");
  await expect(page.getByText("No entries yet")).toBeVisible();

  await page.getByRole("main").getByRole("link", { name: "Add entry" }).click();
  const window = page.getByRole("dialog", { name: "Add entry" });
  // No account yet: the window asks for one first.
  await expect(window.getByText("First, where does your money live?")).toBeVisible();
  await expect(window.getByLabel("Bank")).toBeFocused();
  await window.getByLabel("Bank").fill("Nubank");
  await window.getByLabel(/Balance today/).fill("1.000,00");
  await window.getByRole("button", { name: "Create account" }).click();

  // The entry form replaces it. Typing starts at the amount.
  await expect(window.getByLabel(/Amount/)).toBeFocused();
  await window.getByLabel(/Amount/).fill("45,90");
  await window.getByLabel("Description").fill("Feira");
  await choose(window.getByLabel("Category"), "Groceries");
  await window.getByRole("button", { name: "Save" }).click();

  await expect(window).toBeHidden();
  await expect(row(page, "Feira")).toContainText("−R$ 45,90");
  await expect(row(page, "Feira")).toContainText("Groceries · Nubank · Checking");
  await expect(page.getByText("1 entry")).toBeVisible();
});

test("a known description fills the category, so an entry needs two typed values", async ({
  page,
}) => {
  await freshUser(page, "/transactions");
  const wallet = await prepareWallet(page);
  await apiPost(page, "/api/ledger/transactions", {
    title: "Padaria",
    amount: "18.00",
    category_id: wallet.category,
    instrument: wallet.card,
  });

  await page.keyboard.press("n");
  const window = page.getByRole("dialog", { name: "Add entry" });
  await expect(window).toBeVisible();
  await window.getByLabel(/Amount/).fill("12,5");
  await window.getByLabel("Description").fill("padaria");
  await window.getByLabel("Description").press("Tab");
  // The category and the card of the earlier entry are suggested.
  await expect(window.getByLabel("Category")).not.toHaveAttribute("data-value", "");
  await expect(window.getByLabel("Account or card")).toHaveAttribute("data-value", wallet.card);
  await window.getByLabel("Description").press("Enter");

  await expect(window).toBeHidden();
  await expect(page.getByText("2 entries")).toBeVisible();
  await expect(row(page, "padaria")).toContainText("−R$ 12,50");
});

test("the N shortcut does not fire while the owner types", async ({ page }) => {
  await freshUser(page, "/transactions");
  await prepareWallet(page);
  await page.getByLabel("Search").fill("banana");
  await page.getByLabel("Search").press("n");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByLabel("Search")).toHaveValue("bananan");
});

test("an invalid entry shows its errors at the fields and saves nothing", async ({ page }) => {
  await freshUser(page, "/transactions");
  await prepareWallet(page);
  await page.keyboard.press("n");
  const window = page.getByRole("dialog", { name: "Add entry" });

  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText("Type an amount greater than zero")).toBeVisible();

  await window.getByLabel(/Amount/).fill("10");
  await window.getByRole("button", { name: "Save" }).click();
  // The server refuses the missing description and category, each at its field.
  await expect(window.getByLabel("Description")).toHaveAttribute("aria-invalid", "true");
  await expect(window.getByLabel("Category")).toHaveAttribute("aria-invalid", "true");
  await expect(window).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByText("No entries yet")).toBeVisible();
});

test("income goes to an account and is shown as a gain", async ({ page }) => {
  await freshUser(page, "/transactions");
  await prepareWallet(page);
  await page.keyboard.press("n");
  const window = page.getByRole("dialog", { name: "Add entry" });
  await window.getByText("Income", { exact: true }).click();
  // A card cannot receive income: only the account is offered.
  await window.getByLabel("Account or card").click();
  await expect(page.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Escape");
  // The amount takes its separators while it is typed, and its decimals when the field is left.
  const amount = window.getByLabel(/Amount/);
  await amount.pressSequentially("12345");
  await expect(amount).toHaveValue("12.345");
  // Backspace on the separator deletes the digit before it.
  await amount.press("ArrowLeft");
  await amount.press("ArrowLeft");
  await amount.press("ArrowLeft");
  await amount.press("Backspace");
  await expect(amount).toHaveValue("1.345");
  // The two keys are different: the point groups thousands and the comma starts the decimals.
  await amount.fill("");
  await amount.pressSequentially("2.000,50");
  await expect(amount).toHaveValue("2.000,50");
  await amount.fill("");
  await amount.pressSequentially("5000,5");
  await expect(amount).toHaveValue("5.000,5");
  // A point is the thousands separator here: it shows when typed, and "12.5" left as it is
  // is one hundred and twenty-five.
  await amount.fill("");
  await amount.pressSequentially("12.5");
  await expect(amount).toHaveValue("12.5");
  await amount.blur();
  await expect(amount).toHaveValue("125,00");
  // Backspace after the decimal comma deletes the comma alone.
  await amount.fill("");
  await amount.pressSequentially("7,");
  await amount.press("Backspace");
  await expect(amount).toHaveValue("7");
  await amount.fill("5000");
  await expect(amount).toHaveValue("5.000");
  await amount.blur();
  await expect(amount).toHaveValue("5.000,00");
  await window.getByLabel("Description").fill("Salário");
  await window.getByLabel("Category").click();
  await page.getByRole("option").first().click();
  await window.getByRole("button", { name: "Save" }).click();
  await expect(row(page, "Salário")).toContainText("+R$ 5.000,00");
});

test("the owner changes and deletes an entry in its window", async ({ page }) => {
  await freshUser(page, "/transactions");
  const wallet = await prepareWallet(page);
  await apiPost(page, "/api/ledger/transactions", {
    title: "Cinema",
    amount: "60.00",
    category_id: wallet.category,
    instrument: wallet.account,
  });
  await page.reload();

  await row(page, "Cinema").click();
  const window = page.getByRole("dialog", { name: "Edit entry" });
  await expect(window.getByLabel(/Amount/)).toHaveValue("60,00");
  await window.getByLabel(/Amount/).fill("75,00");
  await window.getByLabel("Description").fill("Cinema e pipoca");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();
  await expect(row(page, "Cinema e pipoca")).toContainText("−R$ 75,00");

  await row(page, "Cinema e pipoca").click();
  await window.getByRole("button", { name: "Delete", exact: true }).click();
  // The first press only asks. The record is still there.
  await expect(window.getByRole("button", { name: "Delete for good" })).toBeVisible();
  await window.getByRole("button", { name: "Delete for good" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByText("No entries yet")).toBeVisible();
});

test("filters live in the address and do not move the page", async ({ page }) => {
  await freshUser(page, "/transactions");
  const wallet = await prepareWallet(page);
  for (let number = 1; number <= 30; number += 1) {
    await apiPost(page, "/api/ledger/transactions", {
      title: number % 2 ? `Mercado ${number}` : `Farmácia ${number}`,
      amount: `${number}.00`,
      category_id: wallet.category,
      instrument: wallet.account,
    });
  }
  await page.setViewportSize({ width: 1280, height: 500 });
  await page.reload();
  await expect(page.getByText("30 entries")).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, 150));
  const position = () => page.evaluate(() => window.scrollY);
  // Focusing a field can scroll it into view. That is the browser, not the
  // filter, so the position is read after the focus.
  await page.getByLabel("Search").focus();
  const start = await position();
  expect(start).toBeGreaterThan(0);

  await page.getByLabel("Search").pressSequentially("farm");
  await expect(page).toHaveURL(/q=farm/);
  await expect(page.getByText("15 entries")).toBeVisible();
  expect(await position()).toBe(start);

  await page.getByRole("group", { name: "Type" }).getByText("Income").click();
  await expect(page).toHaveURL(/type=INCOME/);
  await expect(page.getByText("Nothing matches these filters.")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("30 entries")).toBeVisible();

  // A row far down opens in a window; closing it leaves the page where it was.
  // The click scrolls the row into view first, so the position is read with
  // the window open.
  await page
    .getByRole("link")
    .filter({ has: page.getByText("Mercado 1", { exact: true }) })
    .click();
  await expect(page.getByRole("dialog", { name: "Edit entry" })).toBeVisible();
  await settled(page);
  const behind = await position();
  expect(behind).toBeGreaterThan(300);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  expect(await position()).toBe(behind);

  // The filters survive a reload and Back does not step through each of them.
  await page.getByLabel("Search").fill("mercado 2");
  await expect(page).toHaveURL(/q=mercado/);
  await page.reload();
  await expect(page.getByLabel("Search")).toHaveValue("mercado 2");
  await expect(page.getByText("5 entries")).toBeVisible();
});

test("month navigation shows the billed month of an installment purchase", async ({ page }) => {
  await freshUser(page, "/transactions");
  const wallet = await prepareWallet(page);
  await apiPost(page, "/api/ledger/transactions", {
    title: "Notebook",
    amount: "3000.00",
    category_id: wallet.category,
    instrument: wallet.card,
    installments: 3,
  });
  await page.reload();

  // The label of the month opens the months; every month is one of the choices.
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "All months" }).click();
  await expect(page).toHaveURL(/month=all/);
  await expect(page.getByRole("button", { name: "Period: All months" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next month" })).toBeDisabled();
  await expect(row(page, "Notebook")).toContainText("−R$ 3.000,00");
  await expect(row(page, "Notebook")).toContainText("in 3 installments");

  // In one month, the row shows the installment of that month and the total.
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "This month" }).click();
  await expect(page).not.toHaveURL(/month=/);
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
  await expect(row(page, "Notebook")).toContainText("−R$ 1.000,00");
  await expect(row(page, "Notebook")).toContainText("of R$ 3.000,00");
});

test("categories are managed from Settings", async ({ page }) => {
  await freshUser(page);
  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  await page.getByRole("link", { name: "Manage categories" }).click();
  const window = page.getByRole("dialog", { name: "Categories" });
  await expect(window).toBeVisible();

  await window.getByLabel("New category").fill("Viagens");
  await window.getByRole("button", { name: "Add" }).click();
  await expect(window.getByLabel("Name: Viagens")).toBeVisible();

  await window.getByLabel("Name: Viagens").fill("Viagens e passeios");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByLabel("Name: Viagens e passeios")).toBeVisible();

  await window.getByRole("button", { name: "Delete: Viagens e passeios" }).click();
  await expect(window.getByLabel("Name: Viagens e passeios")).toBeHidden();

  // A duplicate name is refused with the message of the server.
  await window.getByLabel("New category").fill("Groceries");
  await window.getByRole("button", { name: "Add" }).click();
  await expect(window.getByRole("alert")).toBeVisible();
});
