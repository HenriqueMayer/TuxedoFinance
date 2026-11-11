import { expect, test } from "vitest";
import {
  isPeriod,
  monthsBetween,
  oldestStart,
  presetMarks,
  presetOf,
  presetPeriod,
} from "./period";

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

test("the preset that the owner chose names a period that two presets give", () => {
  // The records start in January: "this year" and "all" are the same months.
  expect(presetOf("2026-01", "2026-11", "2026-01", "2026-11")).toBe("year");
  expect(presetOf("2026-01", "2026-11", "2026-01", "2026-11", "all")).toBe("all");
  expect(presetOf("2026-01", "2026-11", "2026-01", "2026-11", "year")).toBe("year");
  // A chosen preset that does not give the period names nothing.
  expect(presetOf("2026-06", "2026-11", "2026-01", "2026-11", "all")).toBe("6");
  expect(presetOf("2026-05", "2026-10", "2026-01", "2026-11", "all")).toBe("");
});

test("each preset has a mark where its period starts on the track", () => {
  // Records older than twelve months: the track starts at the oldest one.
  const long = monthsBetween("2024-01", "2026-11");
  expect(presetMarks(long, "2024-01", "2026-11", "6")).toEqual([
    { preset: "3", position: 32, on: false },
    { preset: "6", position: 29, on: true },
    { preset: "12", position: 23, on: false },
    { preset: "year", position: 24, on: false },
    { preset: "all", position: 0, on: false },
  ]);
  // Records from January: the track is twelve months, and two presets share one position.
  const year = monthsBetween("2025-12", "2026-11");
  expect(presetMarks(year, "2026-01", "2026-11", "6")).toEqual([
    { preset: "3", position: 9, on: false },
    { preset: "6", position: 6, on: true },
    { preset: "12", position: 0, on: false },
    { preset: "year", position: 1, on: false },
  ]);
  // The active preset takes the shared position.
  expect(presetMarks(year, "2026-01", "2026-11", "all")).toContainEqual({
    preset: "all",
    position: 1,
    on: true,
  });
  expect(presetMarks(year, "2026-01", "2026-11", "all").map((mark) => mark.preset)).toEqual([
    "3",
    "6",
    "12",
    "all",
  ]);
  // Three months of records: "all" is the three months.
  expect(presetMarks(year, "2026-09", "2026-11", "").map((mark) => mark.position)).toEqual([
    9, 6, 0, 1,
  ]);
  // In January, "this year" starts at the last position.
  const january = monthsBetween("2026-02", "2027-01");
  expect(presetMarks(january, "2026-06", "2027-01", "")).toContainEqual({
    preset: "year",
    position: 11,
    on: false,
  });
});

test("a period of the address has two months in order", () => {
  expect(isPeriod("2026-06_2026-11")).toBe(true);
  expect(isPeriod("2026-11_2026-06")).toBe(false);
  expect(isPeriod("2026-13_2026-14")).toBe(false);
  expect(isPeriod("2026-06")).toBe(false);
  expect(isPeriod(undefined)).toBe(false);
});
