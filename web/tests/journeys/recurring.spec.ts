import { expect, test } from "@playwright/test";
import { choose, freshUser, pickDate, pickMonth, prepareWallet } from "./support";

/** "YYYY-MM-DD" of the first day of the month that is `offset` months from now. */
function firstOfMonth(offset: number): string {
  const now = new Date();
  const date = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
}

function label(offset: number): string {
  const now = new Date();
  return new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(
    new Date(now.getFullYear(), now.getMonth() + offset, 1),
  );
}

test("the owner records a monthly bill, confirms a month and changes its amount", async ({
  page,
}) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.reload();

  // A rent that started last month, repeats, and asks for confirmation.
  await page.keyboard.press("n");
  const add = page.getByRole("dialog", { name: "Add entry" });
  await add.getByLabel(/Amount/).fill("1500");
  await add.getByLabel("Description").fill("Aluguel");
  await choose(add.getByLabel("Category"), "Services");
  await pickDate(add.getByLabel("Date"), firstOfMonth(-1));
  // The options of an entry are in view: one press turns one on and shows its field.
  await add.getByRole("button", { name: "Repeats every month" }).click();
  await expect(add.getByRole("button", { name: "Repeats every month" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await add.getByRole("button", { name: "Ask me to confirm each month" }).click();
  await add.getByRole("button", { name: "Save" }).click();
  await expect(add).toBeHidden();

  // Home lists the bill in Due soon. A row opens the monthly schedule.
  const due = page.getByRole("link", { name: /Aluguel/ });
  await expect(due.first()).toContainText("R$ 1.500,00");
  await due.first().click();
  const schedule = page.getByRole("dialog", { name: "Monthly schedule" });
  await expect(schedule.getByText("Aluguel")).toBeVisible();

  // Last month was before the confirmation started: it is only scheduled.
  // The first list holds the months; the list of amount changes comes after it.
  const row = (offset: number) =>
    schedule
      .getByRole("list")
      .first()
      .getByRole("listitem")
      .filter({ hasText: label(offset) });
  await expect(row(-1)).toContainText("Scheduled");

  // Confirming this month records it; Undo returns it.
  await schedule.getByRole("button", { name: `Confirm: ${label(0)}` }).click();
  await expect(row(0)).toContainText("Confirmed");
  await schedule.getByRole("button", { name: `Undo: ${label(0)}` }).click();
  await expect(row(0)).not.toContainText("Confirmed");
  await schedule.getByRole("button", { name: `Confirm: ${label(0)}` }).click();
  await expect(row(0)).toContainText("Confirmed");

  // Skipping a month removes its amount from that month.
  await schedule.getByRole("button", { name: `Skip: ${label(2)}` }).click();
  await expect(row(2)).toContainText("Skipped");
  await schedule.getByRole("button", { name: `Undo: ${label(2)}` }).click();
  await expect(row(2)).not.toContainText("Skipped");

  // A new amount applies from next month and leaves this month as it was.
  await pickMonth(schedule.getByLabel("From"), firstOfMonth(1).slice(0, 7));
  await schedule.getByLabel(/New amount/).fill("1650");
  await schedule.getByRole("button", { name: "Apply" }).click();
  await expect(schedule.getByText(`from ${label(1)}`)).toBeVisible();
  await expect(row(1)).toContainText("R$ 1.650,00");
  await expect(row(0)).toContainText("R$ 1.500,00");
  await page.keyboard.press("Escape");

  // The confirmed month left the account; the Transactions list shows the bill in each month.
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Account Conta/ })).toContainText("-R$ 2.000,00");
  await page.goto("/transactions");
  await expect(page.getByRole("link", { name: /Aluguel/ })).toContainText("Recurring");
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(page.getByRole("link", { name: /Aluguel/ })).toContainText("R$ 1.650,00");
});

test("a repeating entry with past months changes its amount only in the schedule", async ({
  page,
}) => {
  await freshUser(page);
  const wallet = await prepareWallet(page);
  await page.evaluate(
    async ([category, instrument, date]) => {
      const token = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
      await fetch("/api/ledger/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({
          title: "Internet",
          amount: "110.00",
          category_id: category,
          instrument,
          date,
          is_fixed: true,
        }),
      });
    },
    [wallet.category, wallet.account, firstOfMonth(-2)] as const,
  );
  await page.goto("/transactions");

  await page.getByRole("link", { name: /Internet/ }).click();
  const edit = page.getByRole("dialog", { name: "Edit entry" });
  await expect(edit.getByText("This entry has past months.")).toBeVisible();
  await expect(edit.getByLabel(/Amount/)).toBeDisabled();
  await expect(edit.getByLabel("Date")).toBeDisabled();
  // The description still changes here.
  await edit.getByLabel("Description").fill("Internet fibra");
  await edit.getByRole("button", { name: "Save" }).click();
  await expect(edit).toBeHidden();
  await expect(page.getByRole("link", { name: /Internet fibra/ })).toBeVisible();

  await page.getByRole("link", { name: /Internet fibra/ }).click();
  await edit.getByRole("link", { name: "Monthly schedule" }).click();
  await expect(page.getByRole("dialog", { name: "Monthly schedule" })).toBeVisible();
});
