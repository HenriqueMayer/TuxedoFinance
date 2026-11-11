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

/**
 * The preset that gives this period, or "" for a period that the owner set by
 * hand. Two presets can give the same months, for example "this year" and
 * "all" when the records start in January: `chosen`, the preset that the
 * owner pressed, then names the period. Without it, the first one in the list does.
 */
export function presetOf(
  start: string,
  end: string,
  first: string,
  last: string,
  chosen: Preset | "" = "",
): Preset | "" {
  const gives = (preset: Preset) => {
    const [from, to] = presetPeriod(preset, first, last);
    return from === start && to === end;
  };
  if (chosen && gives(chosen)) return chosen;
  return PRESETS.find(gives) ?? "";
}

/**
 * Where the period of each preset starts on a track of months. A preset that
 * starts before the track has no mark. Presets that start at the same month
 * share one mark: the active one, or the first one in the list.
 */
export function presetMarks(
  track: string[],
  first: string,
  last: string,
  active: Preset | "",
): { preset: Preset; position: number; on: boolean }[] {
  const marks = PRESETS.map((preset) => ({
    preset,
    position: track.indexOf(presetPeriod(preset, first, last)[0]),
    on: preset === active,
  })).filter((mark) => mark.position >= 0);
  return marks.filter((mark, index) => {
    const shared = marks.filter((other) => other.position === mark.position);
    return shared.some((other) => other.on) ? mark.on : marks.indexOf(shared[0] ?? mark) === index;
  });
}

/** "2026-06_2026-11": a period as one value of the address. */
export function isPeriod(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4}-(0[1-9]|1[0-2]))_(\d{4}-(0[1-9]|1[0-2]))$/.exec(value);
  return match !== null && (match[1] ?? "") <= (match[3] ?? "");
}
