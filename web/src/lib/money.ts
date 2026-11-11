/**
 * Amounts travel as decimal strings ("120.50") and are never calculated on in
 * the client. This module only shows them and reads what the owner types.
 */

const formatters = new Map<string, Intl.NumberFormat>();

/** How numbers are written: 1.234,56 (COMMA) or 1,234.56 (POINT). */
export type NumberFormat = "COMMA" | "POINT";

// The owner's choice. Null before the session is known: the currency of an
// amount then gives its separators.
let chosen: NumberFormat | null = null;

/**
 * Set how every number is written and read. The shell sets the owner's
 * preference before its pages render; null returns to the rule of the
 * currency.
 */
export function setNumberFormat(format: NumberFormat | null): void {
  chosen = format;
}

/** The locale that writes a plain number as the owner chose, or the given one without a choice. */
function numberLocale(fallback: string): string {
  return chosen === null ? fallback : chosen === "COMMA" ? "pt-BR" : "en-US";
}

/**
 * Show an amount in its currency, for example "R$ 1.234,50". The currency
 * gives the symbol and its place. The separators are the owner's choice, or
 * the ones of the currency without a choice.
 */
export function formatAmount(amount: string, currency: string): string {
  let formatter = formatters.get(currency);
  if (!formatter) {
    // The locale follows the currency, not the interface language: a BRL
    // amount keeps its "R$" before the number in English too.
    formatter = new Intl.NumberFormat(LOCALE_OF[currency] ?? "en-US", {
      style: "currency",
      currency,
    });
    formatters.set(currency, formatter);
  }
  if (chosen === null) return formatter.format(Number(amount));
  const { decimal, group } = separators(currency);
  return formatter
    .formatToParts(Number(amount))
    .map((part) => (part.type === "group" ? group : part.type === "decimal" ? decimal : part.value))
    .join("");
}

const LOCALE_OF: Record<string, string> = {
  BRL: "pt-BR",
  USD: "en-US",
  EUR: "de-DE",
  GBP: "en-GB",
  JPY: "ja-JP",
  CHF: "de-CH",
};

/**
 * True when amounts have their decimals after a comma: the owner's choice,
 * or the way of the currency without a choice.
 */
export function usesDecimalComma(currency: string): boolean {
  if (chosen !== null) return chosen === "COMMA";
  return currency === "BRL" || currency === "EUR";
}

/**
 * Read a typed amount and return it as a decimal string, or null when it is
 * not a positive amount with at most two decimals.
 *
 * Both separators are accepted, because a phone keypad may offer only one:
 * - "12,5" and "12.5" are twelve and a half in every currency.
 * - With both kinds, the last one is the decimal separator: "1.234,56".
 * - One separator before exactly three digits is ambiguous ("1.234"). It is a
 *   thousands separator only if the currency uses it as one; otherwise the
 *   text is refused instead of guessed.
 */
export function parseAmount(text: string, currency: string): string | null {
  // With a format chosen, a field writes its text by that format: read it the same way.
  return chosen === null ? looseAmount(text, currency) : strictAmount(text, currency);
}

/**
 * Read an amount by the meaning of its separators: the thousands separator
 * only groups, and the decimal separator comes once, before two digits at
 * most. "1,00" with a comma for thousands is one hundred.
 */
function strictAmount(text: string, currency: string): string | null {
  const { decimal, group } = separators(currency);
  const cleaned = text
    .replace(/[^\d.,]/g, "")
    .split(group)
    .join("");
  const [whole = "", cents = "", ...more] = cleaned.split(decimal);
  if (more.length > 0 || cents.length > 2 || (whole === "" && cents === "")) return null;
  const value = `${whole.replace(/^0+(?=\d)/, "") || "0"}.${cents.padEnd(2, "0")}`;
  return Number(value) > 0 ? value : null;
}

/** Read an amount that was not typed in a field: a paste, or a text before the session is known. */
function looseAmount(text: string, currency: string): string | null {
  const cleaned = text.replace(/[^\d.,]/g, "");
  if (!/\d/.test(cleaned)) return null;

  const decimalComma = usesDecimalComma(currency);
  const lastComma = cleaned.lastIndexOf(",");
  const lastDot = cleaned.lastIndexOf(".");
  let decimalAt = -1;

  if (lastComma >= 0 && lastDot >= 0) {
    decimalAt = Math.max(lastComma, lastDot);
  } else if (lastComma >= 0 || lastDot >= 0) {
    const at = Math.max(lastComma, lastDot);
    const separator = cleaned[at];
    const repeated = cleaned.indexOf(separator as string) !== at;
    const digitsAfter = cleaned.length - at - 1;
    if (repeated) {
      decimalAt = -1; // "1.234.567": the same separator twice groups thousands.
    } else if (digitsAfter === 3) {
      const isThousands = separator === (decimalComma ? "." : ",");
      if (!isThousands) return null;
    } else {
      decimalAt = at;
    }
  }

  const wholeText = decimalAt >= 0 ? cleaned.slice(0, decimalAt) : cleaned;
  // Thousands separators must be one kind and must group exactly three digits.
  if (/[.,]/.test(wholeText) && !/^\d{1,3}([.,])\d{3}(\1\d{3})*$/.test(wholeText)) return null;
  const whole = wholeText.replace(/[.,]/g, "");
  const cents = decimalAt >= 0 ? cleaned.slice(decimalAt + 1) : "";
  if (!/^\d*$/.test(cents) || cents.length > 2 || (whole === "" && cents === "")) return null;

  const value = `${whole.replace(/^0+(?=\d)/, "") || "0"}.${cents.padEnd(2, "0")}`;
  return Number(value) > 0 ? value : null;
}

/** The decimal separator of a currency and the one that groups its thousands. */
function separators(currency: string): { decimal: string; group: string } {
  return usesDecimalComma(currency) ? { decimal: ",", group: "." } : { decimal: ".", group: "," };
}

/** "1234567" as "1.234.567". */
function grouped(whole: string, group: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, group);
}

/** The two separators of an amount field: the owner's choice, or the ones of the currency. */
export function amountSeparators(currency: string): { decimal: string; group: string } {
  return separators(currency);
}

/**
 * Format an amount while the owner types it: "2000" becomes "2.000". The
 * thousands are grouped, the decimals stay as typed (two at most), and
 * letters and leading zeros leave. `caret` is the place of the caret in
 * `text`; the result has its place in the new text, beside the same digit.
 *
 * The decimal separator starts the decimals. The other separator groups:
 * the field writes it by itself. With `manual`, the owner is typing that
 * separator by hand, and it stays where it was typed while the digits after
 * it can still complete a group of three ("1," then "1,0", "1,00", "1,000").
 * The result says in `manual` whether the text still waits for that group.
 *
 * With `signed`, a minus sign at the start is kept: a balance can be negative.
 */
export function typedAmount(
  text: string,
  caret: number,
  currency: string,
  signed = false,
  manual = false,
): { text: string; caret: number; manual: boolean } {
  const { decimal, group } = separators(currency);
  const minusAt = text.trimStart().startsWith("-") ? text.indexOf("-") : -1;
  const negative = signed && minusAt >= 0;

  // The characters that stay, each with its side of the caret.
  type Kept = { char: string; before: boolean };
  let whole: Kept[] = [];
  let cents: Kept[] = [];
  let point: Kept | null = null;
  [...text].forEach((char, index) => {
    const kept = { char, before: index < caret };
    if (/\d/.test(char)) (point ? cents : whole).push(kept);
    else if (char === decimal && !point) point = kept;
    // A typed thousands separator has a digit before it, and comes once.
    else if (char === group && manual && !point && whole.at(-1) && whole.at(-1)?.char !== group) {
      whole.push(kept);
    }
  });
  // Zeros before the first digit that counts leave; one zero alone stays.
  while (whole.length > 1 && whole[0]?.char === "0" && /\d/.test(whole[1]?.char ?? "")) {
    whole = whole.slice(1);
  }
  cents = cents.slice(0, 2);

  const settled = point as Kept | null;
  const digits = whole.filter((kept) => kept.char !== group);
  const number = digits.map((kept) => kept.char).join("");
  const typed = whole.map((kept) => kept.char).join("");
  // The typed separators stay while they can still become the grouping of the number.
  const escaped = group === "." ? "\\." : group;
  const waits =
    manual &&
    !settled &&
    typed !== grouped(number, group) &&
    new RegExp(`^\\d{1,3}(${escaped}\\d{3})*(${escaped}\\d{0,2})?$`).test(typed);

  // ",5" is "0,5": the zero is written for the owner.
  const written = number === "" && settled !== null;
  const shownWhole = waits ? typed : written ? "0" : grouped(number, group);
  const body = `${shownWhole}${settled ? decimal : ""}${cents.map((kept) => kept.char).join("")}`;
  const result = `${negative ? "-" : ""}${body}`;

  // The caret goes after the same number of characters that stayed.
  const stayed = [...(waits ? whole : digits), ...(settled ? [settled] : []), ...cents];
  let wanted = (negative && minusAt < caret ? 1 : 0) + stayed.filter((kept) => kept.before).length;
  if (wanted === 0) return { text: result, caret: 0, manual: waits };
  let place = 0;
  for (let index = 0; index < result.length && wanted > 0; index += 1) {
    const char = result[index] as string;
    // A separator that the field wrote and the zero that it wrote do not count.
    const counts = (waits || char !== group) && !(written && index === (negative ? 1 : 0));
    if (counts) wanted -= 1;
    place = index + 1;
  }
  return { text: result, caret: place, manual: waits };
}

/**
 * Write a typed amount in full when the owner leaves the field: "2000"
 * becomes "2.000,00". The text is read by the meaning of its keys, so a
 * number left in the middle of a group is still the digits that were typed.
 * An empty field stays empty.
 */
export function finishedAmount(text: string, currency: string, signed = false): string {
  const { decimal } = separators(currency);
  const sign = signed && text.trim().startsWith("-") ? "-" : "";
  const typed = typedAmount(text, text.length, currency).text;
  if (typed === "") return "";
  const [whole = "0", cents = ""] = typed.split(decimal);
  return `${sign}${whole || "0"}${decimal}${cents.padEnd(2, "0")}`;
}

/**
 * Write in full an amount that was pasted, dropped or set by a script. It
 * is read with either separator: "1234.56" and "1.234,56" are the same
 * amount. A text that is not an amount gives an empty text.
 */
export function pastedAmount(text: string, currency: string, signed = false): string {
  const { decimal, group } = separators(currency);
  const read = looseAmount(text, currency);
  if (read === null) return finishedAmount(text, currency, signed);
  const sign = signed && text.trim().startsWith("-") ? "-" : "";
  const [whole = "0", cents = "00"] = read.split(".");
  return `${sign}${grouped(whole, group)}${decimal}${cents}`;
}

/** Show a stored amount the way its field writes it in this currency: "1.234,50". */
export function editableAmount(amount: string, currency: string): string {
  const { decimal, group } = separators(currency);
  const negative = amount.startsWith("-");
  const [whole = "0", cents = "00"] = amount.replace("-", "").split(".");
  return `${negative ? "-" : ""}${grouped(whole, group)}${decimal}${cents.padEnd(2, "0")}`;
}

/**
 * Read a typed quantity or unit price: a positive number with at most eight
 * decimals. A comma or a dot is the decimal separator; there is no thousands
 * separator, so "1.234" is one and a fraction.
 */
export function parseDecimal(text: string): string | null {
  const typed = text.trim();
  if (!/^\d+([.,]\d{1,8})?$/.test(typed)) return null;
  const value = typed.replace(",", ".");
  return Number(value) > 0 ? value : null;
}

/** Show a stored quantity or unit price the way the owner types it: no trailing zeros. */
export function editableDecimal(value: string, currency: string): string {
  const trimmed = value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  return usesDecimalComma(currency) ? trimmed.replace(".", ",") : trimmed;
}

/** Show a quantity in the interface language, with the decimals that it has. */
export function formatQuantity(value: string, language: string): string {
  return Number(value).toLocaleString(numberLocale(language), { maximumFractionDigits: 8 });
}

/**
 * True when a typed amount equals a stored one. Both are decimal strings; the
 * typed one may have fewer decimals ("0" and "0.00").
 */
export function sameAmount(typed: string, stored: string | null): boolean {
  if (stored === null) return false;
  const padded = typed.includes(".") ? typed.padEnd(typed.indexOf(".") + 3, "0") : `${typed}.00`;
  return padded === stored;
}

const SYMBOL_OF: Record<string, string> = { CHF: "Fr" };

/** The short symbol of a currency, for example "R$" or "€". */
export function currencySymbol(currency: string): string {
  const known = SYMBOL_OF[currency];
  if (known) return known;
  // One locale for every currency: the Japanese locale gives a full-width yen sign.
  const parts = new Intl.NumberFormat("en", {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
  }).formatToParts(0);
  return parts.find((part) => part.type === "currency")?.value ?? currency;
}

/** "12,5%": a percentage that the server calculated, with one decimal. */
export function formatPercent(value: string, language: string): string {
  const text = Number(value).toLocaleString(numberLocale(language), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${text}%`;
}
