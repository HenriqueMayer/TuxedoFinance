import { expect, test } from "@playwright/test";
import { freshUser, prepareWallet } from "./support";

test("points are recorded, redeemed for money and undone", async ({ page }) => {
  await freshUser(page);
  await prepareWallet(page);
  await page.goto("/wallet");

  // Without a program the Wallet shows one link only.
  await expect(page.getByRole("heading", { name: "Points and miles" })).toBeHidden();
  await page.getByRole("link", { name: "Add a points or miles program" }).click();
  const create = page.getByRole("dialog", { name: "New program" });
  await expect(create.getByLabel("Name")).toBeFocused();
  await create.getByLabel("Name").fill("Livelo");
  await create.getByRole("button", { name: "Create program" }).click();

  // The new program opens in the place of the form.
  const window = page.getByRole("dialog", { name: "Program" });
  await expect(window.getByText("0 points")).toBeVisible();
  await window.getByLabel("How many points").fill("10000");
  await window.getByRole("button", { name: "Record" }).click();
  await expect(window.getByText("10.000 points")).toBeVisible();

  // More points than the program has cannot leave it.
  await window.getByText("Used", { exact: true }).click();
  await window.getByLabel("How many points").fill("20000");
  await window.getByRole("button", { name: "Record" }).click();
  await expect(window.getByText("The program does not have enough points.")).toBeVisible();
  await window.getByLabel("How many points").fill("1500");
  await window.getByLabel("Note (optional)").fill("Passagem");
  await window.getByRole("button", { name: "Record" }).click();
  await expect(window.getByText("8.500 points")).toBeVisible();

  // A redemption turns points into money in the account.
  await window.getByText("Redeem", { exact: true }).click();
  await window.getByLabel("How many points").fill("4000");
  await window.getByLabel("Amount received (BRL)").fill("120,00");
  await expect(window.getByLabel("Account that receives")).toContainText("Nubank · Conta");
  await window.getByRole("button", { name: "Redeem" }).click();
  await expect(window.getByText("4.500 points")).toBeVisible();
  const redeemed = window.getByRole("listitem").filter({ hasText: "Redeemed" });
  await expect(redeemed).toContainText("R$ 120,00 in Conta");
  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();

  await expect(page.getByRole("link", { name: /Livelo/ })).toContainText("4.500 points");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 1.120,00");

  // The undo returns the points and takes the money back.
  await page.getByRole("link", { name: /Livelo/ }).click();
  await redeemed.getByRole("button", { name: "Undo" }).click();
  await expect(window.getByText("8.500 points")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: /Conta/ }).first()).toContainText("R$ 1.000,00");
});
