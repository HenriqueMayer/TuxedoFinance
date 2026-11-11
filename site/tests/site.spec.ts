import { expect, test } from "@playwright/test";

test("the page shows the product in use and asks nothing of another server", async ({ page }) => {
  const outside: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith("http://127.0.0.1:") && !url.startsWith("data:")) outside.push(url);
  });
  await page.goto("./");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "How much can I still spend this month?",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  // The application runs inside the page, with the fictional data.
  const app = page.frameLocator("iframe");
  await expect(app.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(app.getByText("Demonstration with fictional data. Nothing is saved.")).toBeVisible();
  await expect(app.getByRole("link", { name: /Left to spend/ })).toContainText("R$");

  // A destination and a window open in place.
  await app.getByRole("link", { name: "Wallet" }).click();
  await app.getByRole("link", { name: /Platinum/ }).first().click();
  await expect(app.getByRole("dialog", { name: "Card" })).toBeVisible();
  await page.keyboard.press("Escape");

  // A save is refused with the reason.
  await app.getByRole("link", { name: "Plan" }).click();
  await app.getByRole("link", { name: /Left of the limit|Over the limit/ }).click();
  const limit = app.getByRole("dialog", { name: "Limit of the month" });
  await limit.getByRole("button", { name: "Save" }).click();
  await expect(limit.getByText(/This is the demonstration/)).toBeVisible();

  expect(outside).toEqual([]);
});

test("the Portuguese page runs the demonstration in Portuguese", async ({ page }) => {
  await page.goto("./pt-br/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Quanto ainda posso gastar este mês?",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");
  const app = page.frameLocator("iframe");
  await expect(app.getByRole("link", { name: "Carteira" })).toBeVisible();
  await expect(app.getByText("Demonstração com dados fictícios. Nada é gravado.")).toBeVisible();
  // The search of the demonstration filters the recorded rows of the month.
  await app.getByRole("link", { name: "Transações" }).click();
  await app.getByLabel("Buscar").fill("aluguel");
  await expect(app.getByText("1 lançamento")).toBeVisible();
});

test("the demonstration opens in full screen and keeps a window in its address", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("link", { name: "Open the demonstration in full screen" }).first().click();
  await expect(page).toHaveURL(/app\/index\.html/);
  await page.getByRole("link", { name: "Plan" }).click();
  await page.getByRole("link", { name: /Open the sheet/ }).click();
  await expect(page.getByRole("dialog", { name: "Sheet" })).toBeVisible();
  // The address after "#" survives a reload on static hosting.
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Sheet" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Balance at the end/ })).toBeVisible();
});

test("an unknown address answers with the page that says so", async ({ page }) => {
  const response = await page.goto("./nothing-here/");
  expect(response?.status()).toBe(404);
  await expect(page.getByText("This page does not exist.")).toBeVisible();
});
