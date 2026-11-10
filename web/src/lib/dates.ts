/** Calendar dates travel as ISO strings ("2026-11-10"). They are never converted to instants. */

let frozen: string | null = null;

/**
 * Make `todayIso()` return one day. The public demonstration shows the day
 * of its recorded data, not the day of the visit.
 */
export function freezeToday(iso: string | null): void {
  frozen = iso;
}

/** Today's calendar date on this device, as an ISO string. */
export function todayIso(given?: Date): string {
  if (!given && frozen) return frozen;
  const now = given ?? new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** The month of an ISO date or month, as "YYYY-MM". */
export function monthOf(iso: string): string {
  return iso.slice(0, 7);
}

/** The month that is `offset` months from "YYYY-MM". */
export function shiftMonth(month: string, offset: number): string {
  const [year = 0, number = 1] = month.split("-").map(Number);
  const index = year * 12 + (number - 1) + offset;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** True for a real month written as "YYYY-MM". */
export function isMonth(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
}

/** "November 2026" in the interface language. */
export function monthLabel(month: string, language: string): string {
  const [year = 0, number = 1] = month.split("-").map(Number);
  const label = new Intl.DateTimeFormat(language, { month: "long", year: "numeric" }).format(
    new Date(year, number - 1, 1),
  );
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** "Nov 26" in the interface language, for a row of a series that spans two years. */
export function shortMonthLabel(month: string, language: string): string {
  const [year = 0, number = 1] = month.split("-").map(Number);
  const label = new Intl.DateTimeFormat(language, { month: "short", year: "2-digit" })
    .format(new Date(year, number - 1, 1))
    .replace(". de ", "/")
    .replace(/\.$/, "");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** A date in the owner's preferred order: "10/11/2026" or "11/10/2026". */
export function formatDate(iso: string, order: "DMY" | "MDY"): string {
  const [year, month, day] = iso.split("-");
  return order === "DMY" ? `${day}/${month}/${year}` : `${month}/${day}/${year}`;
}

/** "Tuesday, 10 November" in the interface language, for a group of rows. */
export function dayLabel(iso: string, language: string): string {
  const [year = 0, month = 1, day = 1] = iso.split("-").map(Number);
  const label = new Intl.DateTimeFormat(language, {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(year, month - 1, day));
  return label.charAt(0).toUpperCase() + label.slice(1);
}
