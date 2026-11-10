import { expect, type Page, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

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
  await expect(amount).toHaveValue("3000,00");
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
  await create.getByLabel("Category").selectOption({ label: "Hobbies & Entertainment" });
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
