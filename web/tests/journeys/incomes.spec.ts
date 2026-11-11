import { expect, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

test("a salary in two receipts: calculated, recorded, changed in its place and deleted", async ({
  page,
}) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/plan");

  await page.getByRole("link", { name: "New recurring income" }).click();
  const window = page.getByRole("dialog", { name: "New recurring income" });
  await window.getByLabel("Name").fill("Salário");
  await window.getByLabel("Category").click();
  await page.getByRole("option").first().click();

  // The server calculates the advance and the rest of a CLT salary.
  await window.getByRole("button", { name: "Calculate from a CLT salary" }).click();
  await window.getByLabel("Gross salary (BRL)").fill("5000");
  await window.getByRole("button", { name: "Calculate the receipts" }).click();
  await expect(window.getByText(/^Net pay R\$/)).toBeVisible();
  const days = window.getByLabel("Day", { exact: true });
  const amounts = window.getByLabel("Amount (BRL)");
  await expect(days).toHaveCount(2);
  await expect(days.first()).toHaveValue("20");
  // 40% of the gross salary, without deductions.
  await expect(amounts.first()).toHaveValue("2.000,00");
  await expect(amounts.last()).not.toHaveValue("");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();

  // Plan lists the income with its receipts.
  const incomes = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Recurring income" }),
  });
  const row = incomes.getByRole("link", { name: /Salário/ });
  await expect(row).toContainText("day 20: R$ 2.000,00");
  await expect(row).toContainText("day 5: R$");
  await expect(row).toContainText("each month");

  // A receipt is an entry of Transactions, and the income controls it.
  await page.goto("/transactions");
  await page
    .getByRole("link", { name: /Salário/ })
    .first()
    .click();
  const entry = page.getByRole("dialog", { name: "Edit entry" });
  await expect(entry.getByText(/receipt of a recurring income/)).toBeVisible();
  await expect(entry.getByRole("button", { name: "Save" })).toHaveCount(0);
  await entry.getByRole("link", { name: "Open the income" }).click();

  // The amount of a receipt changes in the income.
  const income = page.getByRole("dialog", { name: "Recurring income" });
  await income.getByLabel("Amount (BRL)").last().fill("2100");
  await income.getByRole("button", { name: "Save" }).click();
  await expect(income).toBeHidden();
  await page.goto("/plan");
  await expect(row).toContainText("day 20: R$ 2.100,00");

  // Deleting asks first, and takes the entries.
  await row.click();
  await income.getByRole("button", { name: "Delete", exact: true }).click();
  await income.getByRole("button", { name: "Delete for good" }).click();
  await expect(income).toBeHidden();
  await expect(incomes.getByRole("link", { name: /Salário/ })).toHaveCount(0);
  await page.goto("/transactions");
  await expect(page.getByRole("link", { name: /Salário/ })).toHaveCount(0);
});

test("the form of an income keeps its fields in place with long account names", async ({
  page,
}) => {
  await freshUser(page);
  for (const [bank, name] of [
    ["Inter", "HenriqueMayer - Internacional"],
    ["Nubank", "HenriqueMayer - Nacional"],
  ]) {
    await apiPost(page, "/api/banking/accounts", {
      bank_name: bank,
      name,
      opening_balance: "0.00",
    });
  }
  const window = page.getByRole("dialog", { name: "New recurring income" });
  const box = async (label: string) => {
    const found = await window.getByLabel(label, { exact: true }).boundingBox();
    expect(found, label).not.toBeNull();
    return found ?? { x: 0, y: 0, width: 0, height: 0 };
  };

  // A wide screen: two fields share a row, each in its column.
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/plan?w=new-income");
  await expect(window.getByLabel("Name")).toBeVisible();
  const account = await box("Account that receives");
  const category = await box("Category");
  expect(account.x + account.width).toBeLessThanOrEqual(category.x);
  // A help text of two lines does not move or stretch the field beside it.
  const first = await box("First month");
  const last = await box("Last month");
  expect(Math.abs(first.y - last.y)).toBeLessThan(1);
  expect(Math.abs(first.height - last.height)).toBeLessThan(1);

  // A phone: no field passes the edge of the window, with the calculation open too.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/plan?w=new-income");
  await expect(window.getByLabel("Name")).toBeVisible();
  await window.getByRole("button", { name: "Calculate from a CLT salary" }).click();
  await expect(window.getByLabel("Gross salary (BRL)")).toBeVisible();
  const edges = await window.evaluate((dialog) => {
    const frame = dialog.getBoundingClientRect();
    const fields = [...dialog.querySelectorAll(".field, form")].map((element) =>
      element.getBoundingClientRect(),
    );
    return {
      left: Math.min(...fields.map((rect) => rect.left)) - frame.left,
      right: frame.right - Math.max(...fields.map((rect) => rect.right)),
    };
  });
  expect(edges.left).toBeGreaterThanOrEqual(16);
  expect(edges.right).toBeGreaterThanOrEqual(16);
});

test("the form of an income says which categories it lists and creates an income category", async ({
  page,
}) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/plan?w=new-income");
  const window = page.getByRole("dialog", { name: "New recurring income" });
  await expect(window.getByText(/Expense categories are not listed/)).toBeVisible();

  // A category is created in the window, and it becomes the choice.
  await window.getByRole("button", { name: "New income category" }).click();
  await window.getByLabel("Name of the category").fill("Salário");
  await window.getByLabel("Name of the category").press("Enter");
  await expect(window.getByLabel("Category", { exact: true })).toContainText("Salário");
  await expect(window.getByLabel("Name of the category")).toBeHidden();
  // The same name again is refused, with the message of the server.
  await window.getByRole("button", { name: "New income category" }).click();
  await window.getByLabel("Name of the category").fill("Salário");
  await window.getByRole("button", { name: "Create", exact: true }).click();
  await expect(window.getByRole("alert")).toBeVisible();

  // The new category is an income category.
  const created = await page.evaluate(async () => {
    const all: { name: string; transaction_type: string | null }[] = await (
      await fetch("/api/ledger/categories")
    ).json();
    return all.find((item) => item.name === "Salário")?.transaction_type;
  });
  expect(created).toBe("INCOME");

  await window.getByLabel("Name", { exact: true }).fill("Salário CLT");
  await window.getByLabel("Amount (BRL)").fill("3000");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByRole("link", { name: /Salário CLT/ })).toContainText("R$ 3.000,00");
});

test("without an income category the form of an income says so and offers to create one", async ({
  page,
}) => {
  await freshUser(page);
  await prepareWallet(page);
  // Every category of the owner becomes an expense category.
  await page.evaluate(async () => {
    const token = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
    const all: { id: number; name: string; parent_id: number | null }[] = await (
      await fetch("/api/ledger/categories")
    ).json();
    for (const item of all) {
      await fetch(`/api/ledger/categories/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({
          name: item.name,
          transaction_type: "EXPENSE",
          parent_id: item.parent_id,
        }),
      });
    }
  });
  await page.goto("/plan?w=new-income");
  const window = page.getByRole("dialog", { name: "New recurring income" });
  await expect(window.getByText(/You have no income category yet/)).toBeVisible();
  // The field for the name is open already.
  await window.getByLabel("Name of the category").fill("Serviços");
  await window.getByRole("button", { name: "Create", exact: true }).click();
  await expect(window.getByLabel("Category", { exact: true })).toContainText("Serviços");
  await expect(window.getByText(/You have no income category yet/)).toBeHidden();
});
