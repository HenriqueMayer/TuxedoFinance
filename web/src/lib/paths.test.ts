import { expect, test } from "vitest";
import { localPath } from "./paths";

test("a local path is kept", () => {
  expect(localPath("/transactions?month=2026-11")).toBe("/transactions?month=2026-11");
});

test.each([
  "https://example.test/",
  "//example.test/",
  "/\\example.test/",
  "transactions",
  "",
  42,
  undefined,
])("%s is dropped", (value) => {
  expect(localPath(value)).toBeUndefined();
});
