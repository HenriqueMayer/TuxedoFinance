/**
 * Amounts travel as decimal strings ("120.50") and are never calculated on in
 * the client. This module only shows them and reads what the owner types.
 */

const formatters = new Map<string, Intl.NumberFormat>();

/** Show an amount in its currency, for example "R$ 1.234,50". The currency sets the separators. */
export function formatAmount(amount: string, currency: string): string {
  let formatter = formatters.get(currency);
  if (!formatter) {
    // The locale follows the currency, not the interface language: a BRL
    // amount is written the Brazilian way in English too.
    formatter = new Intl.NumberFormat(LOCALE_OF[currency] ?? "en-US", {
      style: "currency",
      currency,
    });
    formatters.set(currency, formatter);
  }
  return formatter.format(Number(amount));
}

const LOCALE_OF: Record<string, string> = {
  BRL: "pt-BR",
  USD: "en-US",
  EUR: "de-DE",
  GBP: "en-GB",
  JPY: "ja-JP",
  CHF: "de-CH",
};

/** True when the currency writes decimals after a comma. */
export function usesDecimalComma(currency: string): boolean {
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

/** Show a stored amount the way the owner types it in this currency: "1234,50". */
export function editableAmount(amount: string, currency: string): string {
  return usesDecimalComma(currency) ? amount.replace(".", ",") : amount;
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
  return Number(value).toLocaleString(language, { maximumFractionDigits: 8 });
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
  return `${Number(value).toLocaleString(language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}
