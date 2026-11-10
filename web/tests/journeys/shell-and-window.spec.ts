import { expect, test } from "@playwright/test";
import { settled, signIn } from "./support";

test("the four destinations are reachable and show which one is current", async ({ page }) => {
  await signIn(page);
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const name of ["Transactions", "Wallet", "Plan", "Home"]) {
    await nav.getByRole("link", { name }).click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(nav.getByRole("link", { name })).toHaveAttribute("aria-current", "page");
  }
});

test("a window has an address, keeps the page behind it and returns focus when it closes", async ({
  page,
}) => {
  await signIn(page, "/transactions");
  const nav = page.getByRole("navigation", { name: "Main" });
  const opener = nav.getByRole("link", { name: "Settings" });
  await opener.click();

  const window = page.getByRole("dialog", { name: "Settings" });
  await expect(window).toBeVisible();
  await expect(page).toHaveURL(/\/transactions\?w=settings$/);
  // The page behind is still the Transactions page, and it is still current.
  await expect(page.getByRole("heading", { level: 1, name: "Transactions" })).toBeAttached();
  await expect(nav.getByRole("link", { name: "Transactions" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.keyboard.press("Escape");
  await expect(window).toBeHidden();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(opener).toBeFocused();

  // Back and Forward close and reopen the window like any other address.
  await opener.click();
  await expect(window).toBeVisible();
  await page.goBack();
  await expect(window).toBeHidden();
  await page.goForward();
  await expect(window).toBeVisible();
  await window.getByRole("button", { name: "Close" }).click();
  await expect(window).toBeHidden();
  await expect(page).toHaveURL(/\/transactions$/);
});

test("a window opens from a link and closes to its page without a history entry before it", async ({
  page,
}) => {
  await signIn(page, "/login?redirect=/wallet?w=settings");
  const window = page.getByRole("dialog", { name: "Settings" });
  await expect(window).toBeVisible();
  await window.getByRole("button", { name: "Close" }).click();
  await expect(window).toBeHidden();
  await expect(page).toHaveURL(/\/wallet$/);
  await expect(page.getByRole("heading", { level: 1, name: "Wallet" })).toBeVisible();
});

test("the window expands to full size and restores", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  const window = page.getByRole("dialog", { name: "Settings" });
  await expect(window).toBeVisible();
  await settled(page);
  const before = await window.boundingBox();
  await window.getByRole("button", { name: "Expand to full size" }).click();
  await expect
    .poll(async () => (await window.boundingBox())?.width)
    .toBeGreaterThan((before?.width ?? 0) + 100);
  await window.getByRole("button", { name: "Restore size" }).click();
  await expect.poll(async () => (await window.boundingBox())?.width).toBe(before?.width);
});

test("language and theme change at once and survive a reload; currency is saved on the server", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
  const window = page.getByRole("dialog");

  // The radio itself is visually hidden; the owner clicks its label.
  await window.getByText("Português").click();
  await expect(page.getByRole("dialog", { name: "Ajustes" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");

  await window.getByText("Escuro").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await window.getByLabel("Moeda dos totais").selectOption("USD");
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Ajustes" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByLabel("Moeda dos totais")).toHaveValue("USD");

  // Leave the shared server state as the other journeys expect it.
  await page.getByLabel("Moeda dos totais").selectOption("BRL");
  await expect(page.getByLabel("Moeda dos totais")).toHaveValue("BRL");
});

test.describe("with reduced motion", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("the window opens with a short fade and no travel", async ({ page }) => {
    await signIn(page);
    await page.getByRole("navigation").getByRole("link", { name: "Settings" }).click();
    const motion = await page.evaluate(() => {
      const animation = document.querySelector("dialog")?.getAnimations()[0];
      const effect = animation?.effect as KeyframeEffect | undefined;
      return {
        duration: effect?.getTiming().duration,
        transforms: effect?.getKeyframes().map((frame) => frame.transform),
      };
    });
    expect(motion.duration).toBe(120);
    expect(motion.transforms).toEqual(["none", "none"]);
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 375, height: 760 } });

  test("the dock holds the same destinations and a window fills the screen", async ({ page }) => {
    await signIn(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    for (const name of ["Home", "Transactions", "Wallet", "Plan", "Settings"]) {
      await expect(nav.getByRole("link", { name })).toBeVisible();
    }
    // The page does not scroll sideways at this width.
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);

    await nav.getByRole("link", { name: "Settings" }).click();
    const window = page.getByRole("dialog", { name: "Settings" });
    await expect(window).toBeVisible();
    await expect
      .poll(async () => await window.boundingBox())
      .toEqual({
        x: 0,
        y: 0,
        width: 375,
        height: 760,
      });
    await window.getByRole("button", { name: "Close" }).click();
    await expect(window).toBeHidden();
  });
});
