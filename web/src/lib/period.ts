/**
 * The period of the analysis: a run of whole months, each written "YYYY-MM".
 * Two months compare as text, because the year comes first.
 */
import { shiftMonth } from "./dates";

/** A period that one click chooses. */
export type Preset = "3" | "6" | "12" | "year" | "all";

export const PRESETS: Preset[] = ["3", "6", "12", "year", "all"];

/** The server gives at most this number of months. */
export const MAX_MONTHS = 60;

/** Every month from `first` to `last`, oldest first. */
export function monthsBetween(first: string, last: string): string[] {
  const months: string[] = [];
  for (let month = first; month <= last && months.length < 1200; month = shiftMonth(month, 1)) {
    months.push(month);
  }
  return months;
}

/** The oldest month that a period ending at `last` can start at. */
export function oldestStart(first: string, last: string): string {
  const limit = shiftMonth(last, -(MAX_MONTHS - 1));
  return first > limit ? first : limit;
}

/** The first and the last month of a preset. `first` is the month of the oldest record. */
export function presetPeriod(preset: Preset, first: string, last: string): [string, string] {
  if (preset === "year") return [`${last.slice(0, 4)}-01`, last];
  if (preset === "all") return [oldestStart(first, last), last];
  return [shiftMonth(last, -(Number(preset) - 1)), last];
}

/** The preset that gives this period, or "" for a period that the owner set by hand. */
export function presetOf(start: string, end: string, first: string, last: string): Preset | "" {
  return (
    PRESETS.find((preset) => {
      const [from, to] = presetPeriod(preset, first, last);
      return from === start && to === end;
    }) ?? ""
  );
}

/** "2026-06_2026-11": a period as one value of the address. */
export function isPeriod(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4}-(0[1-9]|1[0-2]))_(\d{4}-(0[1-9]|1[0-2]))$/.exec(value);
  return match !== null && (match[1] ?? "") <= (match[3] ?? "");
}
