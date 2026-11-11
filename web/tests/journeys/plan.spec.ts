import { expect, type Page, test } from "@playwright/test";
import { apiPost, choose, chooseValue, freshUser, prepareWallet } from "./support";

async function spend(page: Page, instrument: string, title: string, amount: string, name: string) {
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  await apiPost(page, "/api/ledger/transactions", {
    title,
    amount,
    category_id: categories.find((item) => item.name === name)?.id,
    instrument,
  });
}

test("the owner sets a limit and Left to spend follows it", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  await spend(page, wallet.account, "Feira", "120.00", "Groceries");
  await page.goto("/plan");

  // Without a limit, the page says so and shows the expenses of the month.
  const card = page.getByRole("link", { name: /The month has no limit/ });
  await expect(card).toContainText("R$ 120,00");
  await card.click();
  const window = page.getByRole("dialog", { name: "Limit of the month" });
  const amount = window.getByLabel(/Limit for each month/);
  await expect(amount).toBeFocused();
  await amount.fill("abc");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText("Enter an amount greater than zero.")).toBeVisible();
  await amount.fill("3.000,00");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();

  const limit = page.getByRole("link", { name: /Left of the limit/ });
  await expect(limit).toContainText("R$ 2.880,00");
  await expect(limit).toContainText("R$ 120,00 spent of R$ 3.000,00");

  // Home counts from the limit, and a new entry lowers what is left.
  await page.goto("/");
  const left = page.getByRole("link", { name: /Left to spend/ });
  await expect(left).toContainText("R$ 2.880,00");
  await expect(left).toContainText("of the limit of R$ 3.000,00");
  await spend(page, wallet.account, "Jantar", "80.00", "Groceries");
  await page.reload();
  await expect(left).toContainText("R$ 2.800,00");

  // A limit below the expenses is named as exceeded; removing it returns the first answer.
  await page.goto("/plan");
  await limit.click();
  await expect(amount).toHaveValue("3.000,00");
  await amount.fill("150");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByRole("link", { name: /Over the limit/ })).toContainText("R$ 50,00");
  await page.getByRole("link", { name: /Over the limit/ }).click();
  await window.getByRole("button", { name: "Remove limit" }).click();
  await expect(window).toBeHidden();
  await expect(card).toBeVisible();
});

test("a category budget shows what the category spent", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  await spend(page, wallet.account, "Feira", "120.00", "Groceries");
  await page.goto("/plan");
  await expect(page.getByText("No category has a budget.")).toBeVisible();

  // A category with expenses is offered; its window names the category.
  await page.getByRole("link", { name: /Groceries/ }).click();
  const window = page.getByRole("dialog", { name: "Budget" });
  await expect(window.getByText("This month so far: R$ 120,00.")).toBeVisible();
  await window.getByLabel(/Limit for each month/).fill("400");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window).toBeHidden();
  const row = page.getByRole("link", { name: /Groceries/ });
  await expect(row).toContainText("R$ 120,00 of R$ 400,00");
  await expect(row).toContainText("R$ 280,00 left");

  // Another category is chosen from the list of all categories.
  await page.getByRole("link", { name: "New budget" }).click();
  const create = page.getByRole("dialog", { name: "New budget" });
  await choose(create.getByLabel("Category"), "Hobbies & Entertainment");
  await create.getByLabel(/Limit for each month/).fill("50");
  await create.getByRole("button", { name: "Save" }).click();
  await expect(create).toBeHidden();
  await spend(page, wallet.account, "Cinema", "60.00", "Hobbies & Entertainment");
  await page.reload();
  await expect(page.getByRole("link", { name: /Hobbies/ })).toContainText("R$ 10,00 over");

  await row.click();
  await window.getByRole("button", { name: "Remove budget" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByText("R$ 280,00 left")).toBeHidden();
});

test("the owner creates a goal and reserves a balance for it", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/plan");

  await page.getByRole("link", { name: "New goal" }).click();
  const create = page.getByRole("dialog", { name: "New goal" });
  await expect(create.getByLabel("Name")).toBeFocused();
  await create.getByLabel("Name").fill("Viagem");
  await create.getByLabel("Target amount").fill("5.000,00");
  await create.getByRole("button", { name: "Create goal" }).click();

  // The new goal opens in the place of the form.
  const window = page.getByRole("dialog", { name: "Goal" });
  await expect(window.getByText("No balance is reserved for this goal yet.")).toBeVisible();
  await expect(window.getByLabel("Balance", { exact: true })).toContainText(
    "Nubank · Conta · R$ 1.000,00 free",
  );
  const amount = window.getByLabel(/Amount for this goal/);
  await amount.fill("1.500,00");
  await window.getByRole("button", { name: "Reserve" }).click();
  await expect(window.getByText(/has 1000.00 free/)).toBeVisible();
  await amount.fill("400");
  await window.getByRole("button", { name: "Reserve" }).click();
  await expect(window.getByText("R$ 400,00").first()).toBeVisible();
  await expect(window.getByText("8% of R$ 5.000,00")).toBeVisible();
  await expect(window.getByText("R$ 4.600,00 to go")).toBeVisible();
  await expect(window.getByRole("listitem").filter({ hasText: "Nubank · Conta" })).toContainText(
    "R$ 400,00",
  );
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();

  // The reservation moved no money, and Home shows the goal.
  const card = page.getByRole("link", { name: /Viagem/ });
  await expect(card).toContainText("R$ 400,00");
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 1.000,00");
  await page.goto("/");
  const goal = page.getByRole("link", { name: /Viagem/ });
  await expect(goal).toContainText("8% · R$ 4.600,00 to go");

  // The goal opens from Home too. Archived, it leaves Home and stays on Plan.
  await goal.click();
  await window.getByRole("button", { name: "Remove" }).click();
  await expect(window.getByText("No balance is reserved for this goal yet.")).toBeVisible();
  await window.getByText("Edit goal").click();
  await window.getByLabel("Name").fill("Japão");
  await window.getByLabel(/Archived/).check();
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText(/This goal is archived/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("No goals yet.")).toBeVisible();
  await page.goto("/plan");
  await expect(page.getByRole("link", { name: "Japão" })).toBeVisible();
});

test("the months ahead follow the records and the sheet tries a change", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  // A repeating expense that starts next month: every month ahead has it.
  const next = new Date();
  next.setDate(1);
  next.setMonth(next.getMonth() + 1);
  const date = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-05`;
  await apiPost(page, "/api/ledger/transactions", {
    title: "Aluguel",
    amount: "300.00",
    category_id: categories.find((item) => item.name === "Services")?.id,
    instrument: wallet.account,
    date,
    is_fixed: true,
  });
  await page.goto("/plan");
  await expect(page.getByText("Accounts today: R$ 1.000,00")).toBeVisible();
  const card = page.getByRole("link", { name: /Open the sheet/ });
  await expect(card).toContainText("R$ 700,00");
  await expect(card).toContainText("R$ 400,00");

  // The sheet opens at full size with one row for the repeating expense.
  await card.click();
  const window = page.getByRole("dialog", { name: "Sheet" });
  const cells = window.getByRole("textbox", { name: /^Aluguel, / });
  await expect(cells).toHaveCount(6);
  await expect(cells.nth(1)).toHaveValue("300,00");
  await expect(window.getByRole("row", { name: /Balance at the end/ })).toContainText("R$ 700,00");

  // A changed cell changes the balance in the sheet, and the recorded balance stays in view.
  await cells.nth(1).fill("500");
  await cells.nth(1).press("Enter");
  await expect(window.getByRole("row", { name: /Balance at the end/ })).toContainText("R$ 500,00");
  await expect(window.getByRole("row", { name: /Balance without the changes/ })).toContainText(
    "R$ 700,00",
  );
  // Letters do not enter a cell, and an amount is written with its separators.
  await cells.nth(2).fill("abc");
  await expect(cells.nth(2)).toHaveValue("");
  await cells.nth(2).pressSequentially("1500");
  await expect(cells.nth(2)).toHaveValue("1.500");
  await cells.nth(2).fill("");
  await cells.nth(2).press("Enter");

  // An added row has its amount in every month.
  await window.getByLabel("Name", { exact: true }).fill("Freela");
  await chooseValue(window.getByLabel("Kind"), "income");
  await window.getByLabel("Amount for each month").fill("1.000,00");
  await window.getByRole("button", { name: "Add a row" }).click();
  await expect(window.getByRole("textbox", { name: /^Freela, / }).first()).toHaveValue("1.000,00");
  await expect(window.getByRole("row", { name: /^Income R\$/ })).toContainText("R$ 1.000,00");

  // The sheet is saved under a name and opens again with its changes. No record changed.
  await window.getByLabel("Name of the sheet").fill("Plano B");
  await window.getByRole("button", { name: "Save sheet" }).click();
  await expect(window.getByRole("button", { name: "Delete sheet" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();
  await expect(card).toContainText("R$ 700,00");
  await page.getByRole("link", { name: "Plano B" }).click();
  await expect(window.getByRole("textbox", { name: /^Aluguel, / }).nth(1)).toHaveValue("500,00");
  await expect(window.getByRole("textbox", { name: /^Freela, / })).toHaveCount(6);
  await window.getByText("12 months").click();
  await expect(window.getByRole("textbox", { name: /^Aluguel, / })).toHaveCount(12);
  await window.getByRole("button", { name: "Delete sheet" }).click();
  await window.getByRole("button", { name: "Delete for good" }).click();
  await expect(window).toBeHidden();
  await expect(page.getByRole("link", { name: "Plano B" })).toBeHidden();
});

test("the calculators answer without saving", async ({ page }) => {
  await freshUser(page);
  await page.goto("/plan");
  await page.getByRole("link", { name: /Net salary/ }).click();
  const salary = page.getByRole("dialog", { name: "Net salary (CLT)" });
  await expect(salary.getByLabel(/Gross salary/)).toBeFocused();
  await salary.getByRole("button", { name: "Calculate" }).click();
  await expect(salary.getByText("Enter a number.")).toBeVisible();
  await salary.getByLabel(/Gross salary/).fill("5.000,00");
  await salary.getByRole("button", { name: "Calculate" }).click();
  // 5000.00 less 501.51 of INSS; the 2026 reduction leaves no income tax.
  await expect(salary.getByText("R$ 4.498,49").first()).toBeVisible();
  await expect(salary.getByText("Tables of 2026.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(salary).toBeHidden();

  await page.getByRole("link", { name: /Compound growth/ }).click();
  const growth = page.getByRole("dialog", { name: "Compound growth" });
  await growth.getByLabel(/Initial amount/).fill("100");
  await growth.getByLabel("Contribution for each month").fill("100");
  await growth.getByLabel("Rate (%)").fill("1");
  await growth.getByText("for each month", { exact: true }).click();
  await growth.getByLabel("Months").fill("2");
  await growth.getByRole("button", { name: "Calculate" }).click();
  await expect(growth.getByText("R$ 303,01").first()).toBeVisible();
  await expect(growth.getByText("R$ 3,01")).toBeVisible();
});
