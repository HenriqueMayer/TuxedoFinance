import { expect, test } from "vitest";
import { isPeriod, monthsBetween, oldestStart, presetOf, presetPeriod } from "./period";

test("the months of a period cross a year in order", () => {
  expect(monthsBetween("2025-11", "2026-02")).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
  expect(monthsBetween("2026-03", "2026-03")).toEqual(["2026-03"]);
  expect(monthsBetween("2026-04", "2026-03")).toEqual([]);
});

test("a preset ends at the current month", () => {
  expect(presetPeriod("3", "2024-01", "2026-11")).toEqual(["2026-09", "2026-11"]);
  expect(presetPeriod("12", "2024-01", "2026-11")).toEqual(["2025-12", "2026-11"]);
  expect(presetPeriod("year", "2024-01", "2026-11")).toEqual(["2026-01", "2026-11"]);
  expect(presetPeriod("all", "2024-01", "2026-11")).toEqual(["2024-01", "2026-11"]);
});

test("every month is at most sixty months", () => {
  expect(oldestStart("2010-05", "2026-11")).toBe("2021-12");
  expect(presetPeriod("all", "2010-05", "2026-11")).toEqual(["2021-12", "2026-11"]);
});

test("a period names its preset, and a period set by hand names none", () => {
  expect(presetOf("2026-06", "2026-11", "2024-01", "2026-11")).toBe("6");
  expect(presetOf("2026-01", "2026-11", "2024-01", "2026-11")).toBe("year");
  expect(presetOf("2026-05", "2026-10", "2024-01", "2026-11")).toBe("");
  // Two presets can give the same months: the first one in the list names them.
  expect(presetOf("2026-09", "2026-11", "2026-09", "2026-11")).toBe("3");
});

test("a period of the address has two months in order", () => {
  expect(isPeriod("2026-06_2026-11")).toBe(true);
  expect(isPeriod("2026-11_2026-06")).toBe(false);
  expect(isPeriod("2026-13_2026-14")).toBe(false);
  expect(isPeriod("2026-06")).toBe(false);
  expect(isPeriod(undefined)).toBe(false);
});
