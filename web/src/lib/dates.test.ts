import { expect, test } from "vitest";
import { formatDate, isMonth, monthLabel, monthOf, shiftMonth, todayIso } from "./dates";

test("today is the calendar date of the device, not the UTC date", () => {
  // 23:30 local time on 10 November is still the 10th, whatever the UTC date is.
  expect(todayIso(new Date(2026, 10, 10, 23, 30))).toBe("2026-11-10");
  expect(todayIso(new Date(2026, 0, 5, 0, 10))).toBe("2026-01-05");
});

test("months shift across years in both directions", () => {
  expect(shiftMonth("2026-11", 1)).toBe("2026-12");
  expect(shiftMonth("2026-12", 1)).toBe("2027-01");
  expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  expect(shiftMonth("2026-11", -11)).toBe("2025-12");
  expect(monthOf("2026-11-10")).toBe("2026-11");
});

test("only a real month is a month", () => {
  expect(isMonth("2026-11")).toBe(true);
  for (const value of ["2026-13", "2026-00", "2026-1", "all", "", 202611, undefined]) {
    expect(isMonth(value)).toBe(false);
  }
});

test("a date follows the owner's order and a month follows the language", () => {
  expect(formatDate("2026-11-10", "DMY")).toBe("10/11/2026");
  expect(formatDate("2026-11-10", "MDY")).toBe("11/10/2026");
  expect(monthLabel("2026-11", "en")).toBe("November 2026");
  expect(monthLabel("2026-11", "pt-BR")).toBe("Novembro de 2026");
});
