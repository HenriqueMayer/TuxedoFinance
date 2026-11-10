import { expect, type Page, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

async function seed(page: Page) {
  const wallet = await prepareWallet(page, { confirmPayments: true });
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
    title: "Feira",
    amount: "120.00",
    category_id: category("Groceries"),
    instrument: wallet.account,
  });
  await apiPost(page, "/api/ledger/transactions", {
    title: "Cinema",
    amount: "60.00",
    category_id: category("Hobbies & Entertainment"),
    instrument: wallet.card,
  });
  return wallet;
}

test("Home answers the questions of the month", async ({ page }) => {
  await freshUser(page);
  // A new owner sees where to start, and the blocks with a hint each.
  await expect(page.getByText("Record your first entry to see your month here.")).toBeVisible();
  await expect(page.getByText("No entries this month yet.")).toBeVisible();
  await expect(page.getByText("Nothing is due in the next 45 days.")).toBeVisible();

  await seed(page);
  await page.reload();
  await expect(page.getByText("Your records are up to date.")).toBeVisible();

  const left = page.getByRole("link", { name: /Left to spend/ });
  await expect(left).toContainText("R$ 4.820,00");
  await expect(left).toContainText("R$ 5.000,00");
  await expect(left).toContainText("R$ 180,00");

  const spending = page.getByRole("link", { name: /Where the money went/ });
  await expect(spending).toContainText("Groceries");
  await expect(spending).toContainText("R$ 120,00");
  await expect(spending).toContainText("R$ 60,00");

  await expect(page.getByRole("link", { name: /Platinum/ })).toContainText("R$ 60,00");
});

test("the owner chooses the Home blocks and their order", async ({ page }) => {
  await freshUser(page);
  const titles = () =>
    page
      .locator("main")
      .getByText(/^(Left to spend|Where the money went|Due soon|Net worth)$/)
      .allTextContents();
  expect(await titles()).toEqual([
    "Left to spend",
    "Where the money went",
    "Due soon",
    "Net worth",
  ]);

  await page.getByRole("link", { name: "Edit Home" }).click();
  const window = page.getByRole("dialog", { name: "Edit Home" });
  // The saved choice arrives a moment after the press, so the state is awaited.
  await window.getByRole("checkbox", { name: "Left to spend" }).click();
  await expect(window.getByRole("checkbox", { name: "Left to spend" })).not.toBeChecked();
  await window.getByRole("button", { name: "Move Due soon up" }).click();
  await expect(window.getByRole("checkbox").first()).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();

  // The page behind already shows the new choice, and a reload keeps it.
  expect(await titles()).toEqual(["Due soon", "Where the money went", "Net worth"]);
  await page.reload();
  await expect(page.getByRole("link", { name: "Edit Home" })).toBeVisible();
  expect(await titles()).toEqual(["Due soon", "Where the money went", "Net worth"]);

  // Hiding every block leaves a way back.
  await page.getByRole("link", { name: "Edit Home" }).click();
  await window.getByRole("checkbox", { name: "Due soon" }).click();
  await expect(window.getByRole("checkbox", { name: "Due soon" })).not.toBeChecked();
  await window.getByRole("checkbox", { name: "Where the money went" }).click();
  await expect(window.getByRole("checkbox", { name: "Where the money went" })).not.toBeChecked();
  await window.getByRole("checkbox", { name: "Net worth" }).click();
  await expect(window.getByRole("checkbox", { name: "Net worth" })).not.toBeChecked();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Home has no blocks.")).toBeVisible();
});

test("the month window changes month in place and keeps its address", async ({ page }) => {
  await freshUser(page);
  await seed(page);
  await page.reload();

  await page.getByRole("link", { name: /Left to spend/ }).click();
  const window = page.getByRole("dialog", { name: "Month" });
  await expect(window.getByText("By category")).toBeVisible();
  await expect(window.getByRole("table")).toContainText("R$ 5.000,00");
  const current = (await window.locator("nav p").textContent()) ?? "";

  await window.getByRole("button", { name: "Previous month" }).click();
  await expect(page).toHaveURL(/w=month&wm=\d{4}-\d{2}/);
  await expect(window.locator("nav p")).not.toHaveText(current);
  await expect(window.getByText("No entries this month yet.").first()).toBeVisible();
  // The window stayed open: the same dialog, with the next-month control focused in it.
  await expect(window).toBeVisible();

  // The address reopens the same month.
  await page.reload();
  await expect(window.locator("nav p")).not.toHaveText(current);
  await window.getByRole("button", { name: "Next month" }).click();
  await expect(window.locator("nav p")).toHaveText(current);

  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();
  await expect(page).toHaveURL(/\/$/);
});

test("a due invoice opens from Home and leaves the block when it is paid", async ({ page }) => {
  await freshUser(page);
  await seed(page);
  await page.reload();

  await page.getByRole("link", { name: /Platinum/ }).click();
  const invoice = page.getByRole("dialog", { name: "Invoice" });
  await expect(invoice.getByRole("link", { name: /Cinema/ })).toBeVisible();
  await invoice.getByRole("button", { name: "Record payment" }).click();
  await expect(invoice.getByText("Paid", { exact: true }).first()).toBeVisible();
  await page.keyboard.press("Escape");

  await expect(page.getByText("Nothing is due in the next 45 days.")).toBeVisible();
});
