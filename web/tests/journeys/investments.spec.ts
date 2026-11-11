import { expect, test } from "@playwright/test";
import { choose, freshUser, prepareWallet } from "./support";

test("the owner updates the value of an investment and the net worth follows", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/wallet");

  // Create the investment with what it already holds.
  await page.getByRole("link", { name: "New investment" }).click();
  const create = page.getByRole("dialog", { name: "New investment" });
  await expect(create.getByLabel("Name")).toBeFocused();
  await create.getByLabel("Name").fill("Reserva");
  // The one institution of the owner is the choice already.
  await expect(create.getByLabel("Institution")).toContainText("Nubank");
  await create.getByLabel(/Balance today/).fill("2.000,00");
  await create.getByRole("button", { name: "Create investment" }).click();
  await expect(create).toBeHidden();

  const card = page.getByRole("link", { name: /Reserva/ });
  await expect(card).toContainText("R$ 2.000,00");
  await expect(page.getByText("In investments")).toBeVisible();
  // The opening balance moved no money: the account is as it was.
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 1.000,00");

  await page.goto("/");
  const worth = page.getByRole("link", { name: /Net worth/ });
  await expect(worth).toContainText("R$ 3.000,00");

  // One field records the balance of today; the increase is a yield.
  await page.goto("/wallet");
  await card.click();
  const window = page.getByRole("dialog", { name: "Investment" });
  const balance = window.getByLabel(/Balance today/);
  await expect(balance).toHaveValue("2.000,00");
  await balance.fill("2.150,00");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText("R$ 2.150,00").first()).toBeVisible();
  await expect(window.getByRole("listitem").filter({ hasText: "Yield" })).toContainText(
    "+R$ 150,00",
  );
  await expect(balance).toHaveValue("2.150,00");

  // A lower balance is refused with the reason, and nothing changes.
  await balance.fill("1.000,00");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText(/Record a withdrawal instead/)).toBeVisible();

  await page.goto("/");
  await expect(worth).toContainText("R$ 3.150,00");
  // The investment is held since today, so all of it is new since the end of last month.
  await expect(worth).toContainText("R$ 2.150,00 more than at the end of last month");
  await worth.click();
  const detail = page.getByRole("dialog", { name: "Net worth" });
  await expect(detail.getByText("Accounts").locator("..")).toContainText("R$ 1.000,00");
  await expect(detail.getByText("Investments").locator("..")).toContainText("R$ 2.150,00");
  await expect(detail.getByRole("row")).toHaveCount(13); // The header and twelve months.
});

test("a deposit and a withdrawal move money and keep the net worth", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/wallet");
  await page.getByRole("link", { name: "New investment" }).click();
  const create = page.getByRole("dialog", { name: "New investment" });
  await create.getByLabel("Name").fill("CDB");
  // The institutions are a list of the application, and a new one is typed.
  await choose(create.getByLabel("Institution"), "Another institution…");
  await create.getByLabel("Name of the institution").fill("XP");
  await create.getByRole("button", { name: "Create investment" }).click();
  await expect(create).toBeHidden();

  await page.getByRole("link", { name: /CDB/ }).click();
  const window = page.getByRole("dialog", { name: "Investment" });
  await expect(window.getByText("No operations yet.")).toBeVisible();
  await window.getByText("Deposit", { exact: true }).click();
  await window.getByLabel(/Amount/).fill("300");
  await expect(window.getByLabel("From the account")).toContainText("Nubank · Conta");
  await window.getByRole("button", { name: "Deposit" }).click();
  await expect(window.getByText("R$ 300,00").first()).toBeVisible();
  await expect(window.getByRole("listitem").filter({ hasText: "Deposit" })).toContainText("Conta");

  // More than the investment holds is refused on the amount.
  await window.getByText("Withdrawal", { exact: true }).click();
  await window.getByLabel(/Amount/).fill("500");
  await window.getByRole("button", { name: "Withdrawal" }).click();
  await expect(window.getByText(/exceeds the available position/)).toBeVisible();
  await window.getByLabel(/Amount/).fill("100");
  await window.getByRole("button", { name: "Withdrawal" }).click();
  await expect(window.getByRole("listitem").filter({ hasText: "Withdrawal" })).toContainText(
    "−R$ 100,00",
  );

  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 800,00");
  await expect(page.getByRole("link", { name: /CDB/ })).toContainText("R$ 200,00");
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Net worth/ })).toContainText("R$ 1.000,00");

  // Undoing the deposit is refused while the withdrawal needs it; undoing both returns the money.
  await page.goto("/wallet");
  await page.getByRole("link", { name: /CDB/ }).click();
  const rows = window.getByRole("listitem");
  await rows.filter({ hasText: "Withdrawal" }).getByRole("button", { name: "Undo" }).click();
  await expect(rows.filter({ hasText: "Withdrawal" })).toHaveCount(0);
  await rows.filter({ hasText: "Deposit" }).getByRole("button", { name: "Undo" }).click();
  await expect(window.getByText("No operations yet.")).toBeVisible();
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 1.000,00");
});

test("an investment in units is valued by the price of today", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/wallet");
  await page.getByRole("link", { name: "New investment" }).click();
  const create = page.getByRole("dialog", { name: "New investment" });
  await create.getByLabel("Name").fill("Ações");
  await create.getByText("Units and price").click();
  await create.getByLabel("Quantity").fill("2");
  await create.getByLabel(/Price paid/).fill("100");
  await create.getByRole("button", { name: "Create investment" }).click();
  await expect(create).toBeHidden();

  const card = page.getByRole("link", { name: /Ações/ });
  await expect(card).toContainText("R$ 200,00");
  await expect(card).toContainText("2 units");
  await card.click();
  const window = page.getByRole("dialog", { name: "Investment" });
  await expect(window.getByText(/No price recorded yet/)).toBeVisible();
  await window.getByLabel(/Unit price today/).fill("150,5");
  await window.getByRole("button", { name: "Save" }).click();
  await expect(window.getByText("R$ 301,00").first()).toBeVisible();
  await expect(window.getByText("Gain").locator("..")).toContainText("+R$ 101,00");

  // Rename, then archive: the card leaves the grid and stays reachable.
  await window.getByText("Edit investment").click();
  await window.getByLabel("Name").fill("Ações Brasil");
  await window.getByRole("button", { name: "Archive", exact: true }).click();
  await window.getByRole("button", { name: "Save" }).last().click();
  await expect(window.getByText(/This investment is archived/)).toBeVisible();
  await page.goto("/wallet");
  await expect(page.getByRole("link", { name: "Ações Brasil" })).toBeVisible();
  await expect(page.getByText("2 units")).toBeHidden();
});
