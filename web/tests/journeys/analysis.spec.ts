import { expect, type Page, test } from "@playwright/test";
import { apiPost, freshUser, prepareWallet } from "./support";

/** The day 5 of the month that is `back` months before the current one, as "YYYY-MM-DD". */
function day5(back: number): string {
  const now = new Date();
  const date = new Date(now.getFullYear(), now.getMonth() - back, 5);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-05`;
}

async function seed(page: Page) {
  const wallet = await prepareWallet(page);
  const categories: { id: number; name: string }[] = await page.evaluate(async () =>
    (await fetch("/api/ledger/categories")).json(),
  );
  const category = (name: string) => categories.find((item) => item.name === name)?.id;
  const entry = (title: string, amount: string, name: string, more: object = {}) =>
    apiPost(page, "/api/ledger/transactions", {
      title,
      amount,
      category_id: category(name),
      instrument: wallet.account,
      ...more,
    });
  await entry("Salário", "5000.00", "Services", { transaction_type: "INCOME" });
  await entry("Feira", "120.00", "Groceries");
  await entry("Cinema", "60.00", "Hobbies & Entertainment");
  await entry("Feira", "80.00", "Groceries", { date: day5(1) });
  await entry("Feira", "100.00", "Groceries", { date: day5(3) });
}

test("the analysis shows a period with its charts, and the owner changes the period", async ({
  page,
}) => {
  await freshUser(page);
  await seed(page);
  await page.reload();

  await page.getByRole("link", { name: "Analyze" }).click();
  const window = page.getByRole("dialog", { name: "Analysis" });
  await expect(window.getByRole("heading", { name: "Income and expenses" })).toBeVisible();
  // Without a choice, the period is the six months to the current one.
  await expect(window.getByRole("radio", { name: "6 months" })).toBeChecked();
  await expect(window.getByText("· 6 months")).toBeVisible();
  // The records start three months ago, so the six months before have nothing to compare with.
  await expect(window.getByText(/The period before starts before your records/)).toBeVisible();

  // Each chart has a table with its values.
  const flows = window.getByRole("table", { name: "Income and expenses" });
  await expect(flows.getByRole("row").last()).toContainText("R$ 5.000,00");
  await expect(flows.getByRole("row").last()).toContainText("R$ 180,00");
  await expect(window.getByRole("button", { name: /Groceries/ })).toContainText("R$ 300,00");

  // The values of a month float above the plot, in a label that does not cover the marks.
  const chart = window.getByRole("group", { name: "Income and expenses" });
  const plot = chart.locator("svg").first();
  const box = (await plot.boundingBox()) ?? { x: 0, y: 0, width: 0, height: 0 };
  // The six months share the width after the axis (48 px); the last one is the current month.
  const monthX = (index: number) => box.x + 48 + ((box.width - 56) / 6) * (index + 0.5);
  const middle = box.y + box.height / 2;
  await page.mouse.move(monthX(5), middle);
  const reading = chart.locator("[data-reading]");
  await expect(reading).toContainText("R$ 5.000,00");
  await expect(reading).toContainText("R$ 180,00");
  // Both are measured now: the window can still settle after it opens.
  const label = (await reading.boundingBox()) ?? { y: 0, height: 0 };
  const plotNow = (await plot.boundingBox()) ?? box;
  expect(label.y + label.height).toBeLessThanOrEqual(plotNow.y + 1);

  // A click on a month opens what its values are made of, in a window above the analysis.
  await page.mouse.click(monthX(5), middle);
  const origin = page.getByRole("dialog", { name: "Origin of the values" });
  await expect(page).toHaveURL(/w2=origin/);
  await expect(origin.getByRole("link", { name: /Salário/ })).toContainText("R$ 5.000,00");
  await expect(origin.getByRole("link", { name: /Feira/ })).toContainText("R$ 120,00");
  await expect(origin.getByRole("link", { name: "Open in Transactions" }).first()).toBeVisible();
  // An entry opens in the place of that window. Escape returns to it, then to the analysis.
  await origin.getByRole("link", { name: /Feira/ }).click();
  await expect(page.getByRole("dialog", { name: "Edit entry" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(origin).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(origin).toBeHidden();
  await expect(page).not.toHaveURL(/w2=/);
  // The analysis stayed below, with its period.
  await expect(window.getByText("· 6 months")).toBeVisible();

  // A drag over months gives their figures, from the server.
  // The chart is measured again each time: a press elsewhere can scroll the window.
  const drag = async () => {
    await plot.scrollIntoViewIfNeeded();
    const now = (await plot.boundingBox()) ?? box;
    const x = (index: number) => now.x + 48 + ((now.width - 56) / 6) * (index + 0.5);
    const y = now.y + now.height / 2;
    await page.mouse.move(x(2), y);
    await page.mouse.down();
    await page.mouse.move(x(3), y, { steps: 4 });
    await page.mouse.move(x(4), y, { steps: 4 });
    await page.mouse.up();
  };
  await drag();
  // Three months back to one month back: 100,00 and 80,00 of expenses, no income.
  const figures = chart.locator("[data-run]");
  await expect(figures).toContainText("Expenses R$ 180,00");
  await expect(figures).toContainText("Income R$ 0,00");
  await expect(chart.getByRole("button", { name: "Use as the period" })).toBeVisible();
  // With the pointer on the selected months, the label shows their figures, not one month.
  await page.mouse.move(monthX(3), middle);
  await expect(reading).toContainText("3 months");
  await expect(reading).toContainText("R$ 180,00");
  // Outside the selection, the label is of the month under the pointer again.
  await page.mouse.move(monthX(5), middle);
  await expect(reading).toContainText("R$ 5.000,00");
  await page.mouse.move(box.x + box.width / 2, box.y - 200);
  // Escape ends the selection, and the window stays open.
  await page.keyboard.press("Escape");
  await expect(figures).toBeHidden();
  await expect(window).toBeVisible();
  // A press outside the chart ends it too.
  await drag();
  await expect(figures).toBeVisible();
  await window.getByRole("heading", { name: "Where the money went" }).click();
  await expect(figures).toBeHidden();
  // So does its own button.
  await drag();
  await chart.getByRole("button", { name: "Clear the selection" }).click();
  await expect(figures).toBeHidden();

  // One category month by month.
  await window.getByRole("button", { name: /Hobbies/ }).click();
  await expect(
    window.getByRole("table", { name: "Hobbies & Entertainment, month by month" }),
  ).toContainText("R$ 60,00");

  // The net worth has the balance of the account, and no investment is held.
  await expect(
    window.getByRole("table", { name: "Net worth" }).getByRole("row").last(),
  ).toContainText("R$ 5.640,00");
  await expect(window.getByText("No investments in this period.")).toBeVisible();

  // A preset changes the period, and the address keeps it.
  await window.getByText("3 months").click();
  await expect(page).toHaveURL(/wp=\d{4}-\d{2}_\d{4}-\d{2}/);
  await expect(window.getByText("· 3 months")).toBeVisible();
  await expect(window.getByRole("button", { name: /Groceries/ })).toContainText("R$ 200,00");

  // The handles answer the keyboard: the last month moves one month back.
  await window.getByRole("slider", { name: "Last month of the period" }).press("ArrowLeft");
  await expect(window.getByText("· 2 months")).toBeVisible();
  await expect(window.getByRole("radio", { name: "3 months" })).not.toBeChecked();
  await expect(window.getByRole("button", { name: /Groceries/ })).toContainText("R$ 80,00");
  await expect(window.getByRole("button", { name: "One month forward" })).toBeEnabled();
  await window.getByRole("button", { name: "One month forward" }).click();
  await expect(window.getByRole("button", { name: /Groceries/ })).toContainText("R$ 200,00");

  // A reload opens the same period.
  await page.reload();
  await expect(window.getByText("· 2 months")).toBeVisible();

  // One month against the month before it: the changes are shown.
  const month = day5(0).slice(0, 7);
  await page.goto(`/?w=analysis&wp=${month}_${month}`);
  await expect(window.getByText(/Each change is against/)).toBeVisible();
  // Expenses: 180,00 now, 80,00 the month before.
  await expect(window.getByText("+R$ 100,00 · +125,0%")).toBeVisible();
});

test("a preset that gives the months of another one can be chosen", async ({ page }) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  // The records start two months ago: "3 months" and "All" are the same months.
  for (const back of [0, 2]) {
    await apiPost(page, "/api/ledger/transactions", {
      title: "Feira",
      amount: "100.00",
      category_id: wallet.category,
      instrument: wallet.account,
      date: day5(back),
    });
  }
  await page.goto("/?w=analysis");
  const window = page.getByRole("dialog", { name: "Analysis" });
  const preset = (name: string) => window.locator("label").filter({ hasText: name });
  await preset("3 months").click();
  await expect(window.getByRole("radio", { name: "3 months" })).toBeChecked();
  await preset("All").click();
  await expect(window.getByRole("radio", { name: "All" })).toBeChecked();
  await expect(window.getByText("· 3 months")).toBeVisible();
  // The mark under the track has the name of the chosen preset.
  await expect(window.locator(".range-mark[data-on]")).toHaveText("All");
  await preset("3 months").click();
  await expect(window.getByRole("radio", { name: "3 months" })).toBeChecked();
  await expect(window.locator(".range-mark[data-on]")).toHaveText("3 mo");
});

test("the bar of areas stays in the window, goes to an area and marks the area in view", async ({
  page,
}) => {
  await freshUser(page);
  await seed(page);
  await page.goto("/?w=analysis");
  const window = page.getByRole("dialog", { name: "Analysis" });
  const bar = window.getByRole("navigation", { name: "Areas of the analysis" });
  const tab = (name: string) => bar.getByRole("button", { name });
  await expect(tab("Income and expenses")).toHaveAttribute("aria-current", "true");

  // The last area is short: it cannot reach the top of the window. A press
  // still scrolls only the content, so the title and the bar stay in place.
  for (const name of ["Investments", "Net worth", "Where the money went"]) {
    await tab(name).click();
    await expect(tab(name)).toHaveAttribute("aria-current", "true");
    await expect(window.getByRole("heading", { name, exact: true })).toBeInViewport();
    await expect(window.getByRole("heading", { name: "Analysis" })).toBeInViewport();
    await expect(bar).toBeInViewport();
    expect(await window.evaluate((element) => element.scrollTop)).toBe(0);
  }

  // The wheel moves the content under the bar, and the mark follows.
  await window.getByRole("heading", { name: "Where the money went" }).hover();
  await page.mouse.wheel(0, -5000);
  await expect(tab("Income and expenses")).toHaveAttribute("aria-current", "true");
  await expect(bar).toBeInViewport();
  await page.mouse.wheel(0, 5000);
  await expect(tab("Investments")).toHaveAttribute("aria-current", "true");
  await expect(bar).toBeInViewport();
});

test("the cards of a period: every card together, one card alone and the later statements", async ({
  page,
}) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  const gold = await apiPost<{ id: string }>(page, "/api/banking/credit-cards", {
    account: wallet.account,
    name: "Gold",
    closing_day: 24,
    due_day: 1,
    confirm_payments: false,
  });
  const purchase = (title: string, amount: string, more: object) =>
    apiPost(page, "/api/ledger/transactions", {
      title,
      amount,
      category_id: wallet.category,
      ...more,
    });
  // Three installments: one in the statement of this month, two in the later ones.
  await purchase("Notebook", "900.00", { instrument: wallet.card, installments: 3 });
  await purchase("Jantar", "100.00", { instrument: gold.id, date: day5(1) });
  // An expense of the account is not of a card.
  await purchase("Feira", "50.00", { instrument: wallet.account });

  await page.goto("/?w=analysis");
  const window = page.getByRole("dialog", { name: "Analysis" });
  await window
    .getByRole("navigation", { name: "Areas of the analysis" })
    .getByRole("button", { name: "Cards" })
    .click();
  const cards = window.getByRole("region", { name: "Cards" });
  await expect(cards.getByRole("heading", { name: "Cards" })).toBeInViewport();

  // Every card together: the totals, the debt of today and one row for each card.
  const all = cards.getByRole("button", { name: /All cards/ });
  await expect(all).toHaveAttribute("aria-pressed", "true");
  await expect(all).toContainText("R$ 400,00");
  await expect(all).toContainText("owes R$ 900,00");
  await expect(cards.getByRole("button", { name: /Platinum/ })).toContainText("75,0%");
  await expect(cards.getByRole("button", { name: /Gold/ })).toContainText("R$ 100,00");
  const statements = cards.getByRole("table", { name: "All cards, the statement of each month" });
  await expect(statements.getByRole("row").last()).toContainText("R$ 300,00");
  // The statements after this month already have the two other installments.
  const later = cards.getByRole("table", { name: "All cards, later statements" });
  await expect(later.getByRole("row")).toHaveCount(3);
  await expect(later.getByRole("row").last()).toContainText("R$ 300,00");

  // One card alone: its figures, its chart and its categories.
  await cards.getByRole("button", { name: /Gold/ }).click();
  await expect(cards.getByRole("button", { name: /Gold/ })).toHaveAttribute("aria-pressed", "true");
  await expect(cards.getByText("Where it was used: Gold")).toBeVisible();
  await expect(
    cards.getByRole("table", { name: "Gold, the statement of each month" }),
  ).toContainText("R$ 100,00");
  await expect(
    cards.getByRole("table", { name: "Gold, later statements" }).getByRole("row").last(),
  ).toContainText("R$ 0,00");

  // A click on a month opens the card entries that its statement bills.
  await cards.getByRole("button", { name: /Platinum/ }).click();
  const plot = cards
    .getByRole("group", { name: "Platinum, the statement of each month" })
    .locator("svg")
    .first();
  await plot.scrollIntoViewIfNeeded();
  const box = (await plot.boundingBox()) ?? { x: 0, y: 0, width: 0, height: 0 };
  await page.mouse.click(box.x + 48 + ((box.width - 56) / 6) * 5.5, box.y + box.height / 2);
  const origin = page.getByRole("dialog", { name: "Origin of the values" });
  await expect(origin.getByRole("link", { name: /Notebook/ })).toContainText("R$ 300,00");
  await expect(origin.getByRole("link", { name: /Notebook/ })).toContainText("installment 1 of 3");
  await expect(origin.getByRole("link", { name: /Feira/ })).toHaveCount(0);
});
