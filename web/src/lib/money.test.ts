import { afterEach, expect, test } from "vitest";
import {
  currencySymbol,
  editableAmount,
  editableDecimal,
  finishedAmount,
  formatAmount,
  formatPercent,
  formatQuantity,
  parseAmount,
  parseDecimal,
  pastedAmount,
  sameAmount,
  setNumberFormat,
  typedAmount,
} from "./money";

test.each([
  ["12", "12.00"],
  ["12,5", "12.50"],
  ["12.5", "12.50"],
  ["12,50", "12.50"],
  ["12.50", "12.50"],
  ["1.234,56", "1234.56"],
  ["1,234.56", "1234.56"],
  ["1.234", "1234.00"],
  ["1.234.567", "1234567.00"],
  ["R$ 1.234,50", "1234.50"],
  [",5", "0.50"],
  ["007", "7.00"],
])("BRL: %s is %s", (text, expected) => {
  expect(parseAmount(text, "BRL")).toBe(expected);
});

test.each([
  ["1,234", "1234.00"],
  ["1,234.5", "1234.50"],
  ["12,5", "12.50"],
  ["$ 99.99", "99.99"],
])("USD: %s is %s", (text, expected) => {
  expect(parseAmount(text, "USD")).toBe(expected);
});

test.each([
  ["", "BRL"],
  ["abc", "BRL"],
  ["0", "BRL"],
  ["0,00", "BRL"],
  ["12,345", "BRL"], // Three decimals in a comma currency: refused, not guessed.
  ["1.234", "USD"], // Three decimals in a dot currency: refused, not guessed.
  ["1,2,3", "USD"],
  ["12.345,678", "BRL"],
])("%s in %s is refused", (text, currency) => {
  expect(parseAmount(text, currency)).toBeNull();
});

test("an amount is shown the way its currency writes it, in any interface language", () => {
  expect(formatAmount("1234.5", "BRL").replace(/\s/g, " ")).toBe("R$ 1.234,50");
  expect(formatAmount("1234.5", "USD")).toBe("$1,234.50");
});

test("a stored amount is offered for editing with the separator of its currency", () => {
  expect(editableAmount("1234.50", "BRL")).toBe("1.234,50");
  expect(editableAmount("1234.50", "USD")).toBe("1,234.50");
  // What the field shows is read back as the same amount.
  expect(parseAmount(editableAmount("1234.50", "BRL"), "BRL")).toBe("1234.50");
  expect(parseAmount(editableAmount("1234.50", "USD"), "USD")).toBe("1234.50");
});

test("a quantity or a unit price has up to eight decimals after a comma or a dot", () => {
  expect(parseDecimal("2")).toBe("2");
  expect(parseDecimal("0,00012345")).toBe("0.00012345");
  expect(parseDecimal(" 1.234 ")).toBe("1.234");
  expect(parseDecimal("1.234,5")).toBeNull();
  expect(parseDecimal("0.123456789")).toBeNull();
  expect(parseDecimal("0")).toBeNull();
  expect(parseDecimal("-1")).toBeNull();
  expect(parseDecimal("abc")).toBeNull();
});

test("a stored quantity is offered for editing without trailing zeros", () => {
  expect(editableDecimal("150.50000000", "BRL")).toBe("150,5");
  expect(editableDecimal("2.00000000", "USD")).toBe("2");
  expect(editableDecimal("100", "BRL")).toBe("100");
  expect(parseDecimal(editableDecimal("0.00012345", "BRL"))).toBe("0.00012345");
  expect(formatQuantity("2.50000000", "en")).toBe("2.5");
});

test("a typed amount equals a stored one when only the decimals are written differently", () => {
  expect(sameAmount("2500.00", "2500.00")).toBe(true);
  expect(sameAmount("0", "0.00")).toBe(true);
  expect(sameAmount("-20.5", "-20.50")).toBe(true);
  expect(sameAmount("2500.00", "2500.01")).toBe(false);
  expect(sameAmount("2500.00", null)).toBe(false);
});

test("a currency has a short symbol", () => {
  expect(currencySymbol("BRL")).toBe("R$");
  expect(currencySymbol("USD")).toBe("$");
  expect(currencySymbol("EUR")).toBe("€");
  expect(currencySymbol("GBP")).toBe("£");
  expect(currencySymbol("JPY")).toBe("¥");
  // The franc has no symbol of its own; its usual short form is used.
  expect(currencySymbol("CHF")).toBe("Fr");
});

test("an amount groups its thousands while the owner types", () => {
  // The text and the place of the caret, after each key.
  expect(typedAmount("2", 1, "BRL")).toMatchObject({ text: "2", caret: 1 });
  expect(typedAmount("200", 3, "BRL")).toMatchObject({ text: "200", caret: 3 });
  expect(typedAmount("2000", 4, "BRL")).toMatchObject({ text: "2.000", caret: 5 });
  expect(typedAmount("2.0000", 6, "BRL")).toMatchObject({ text: "20.000", caret: 6 });
  expect(typedAmount("1234567", 7, "BRL")).toMatchObject({ text: "1.234.567", caret: 9 });
  // The dollar groups with a comma and has a decimal point.
  expect(typedAmount("2000", 4, "USD")).toMatchObject({ text: "2,000", caret: 5 });
});

test("the decimals of a typed amount stay as typed, two at most", () => {
  expect(typedAmount("2.000,", 6, "BRL")).toMatchObject({ text: "2.000,", caret: 6 });
  expect(typedAmount("2.000,5", 7, "BRL")).toMatchObject({ text: "2.000,5", caret: 7 });
  expect(typedAmount("2.000,567", 9, "BRL")).toMatchObject({ text: "2.000,56", caret: 8 });
  expect(typedAmount(",5", 2, "BRL")).toMatchObject({ text: "0,5", caret: 3 });
  // A second decimal separator is not kept.
  expect(typedAmount("1,2,3", 5, "BRL")).toMatchObject({ text: "1,23", caret: 4 });
});

test("the caret stays beside the digit that the owner changed", () => {
  // A digit typed in the middle: "2.000" with a 5 after the 2.
  expect(typedAmount("25.000", 2, "BRL")).toMatchObject({ text: "25.000", caret: 2 });
  // A digit deleted in the middle: "12.345" without the 2.
  expect(typedAmount("1.345", 1, "BRL")).toMatchObject({ text: "1.345", caret: 1 });
  expect(typedAmount("1345", 1, "BRL")).toMatchObject({ text: "1.345", caret: 1 });
});

test("letters and leading zeros leave a typed amount", () => {
  expect(typedAmount("R$ 12a", 6, "BRL").text).toBe("12");
  expect(typedAmount("007", 3, "BRL").text).toBe("7");
  expect(typedAmount("0", 1, "BRL").text).toBe("0");
  expect(typedAmount("", 0, "BRL")).toMatchObject({ text: "", caret: 0 });
});

test("a balance can be negative; another amount cannot", () => {
  expect(typedAmount("-1500", 5, "BRL", true).text).toBe("-1.500");
  expect(typedAmount("-1500", 5, "BRL").text).toBe("1.500");
  expect(typedAmount("-", 1, "BRL", true).text).toBe("-");
});

test("a finished amount has its two decimals", () => {
  expect(finishedAmount("2000", "BRL")).toBe("2.000,00");
  expect(finishedAmount("2.000,5", "BRL")).toBe("2.000,50");
  expect(finishedAmount("0", "BRL")).toBe("0,00");
  expect(finishedAmount("1234.5", "USD")).toBe("1,234.50");
  expect(finishedAmount("-1500", "BRL", true)).toBe("-1.500,00");
  // An empty field stays empty: it has a meaning of its own in some forms.
  expect(finishedAmount("", "BRL")).toBe("");
  expect(finishedAmount("-", "BRL", true)).toBe("");
});

test("a pasted amount is read with either separator", () => {
  // In a field of reais, "1234.56" is one thousand and some, not 123 thousand.
  expect(pastedAmount("1234.56", "BRL")).toBe("1.234,56");
  expect(pastedAmount("1.234,56", "BRL")).toBe("1.234,56");
  expect(pastedAmount("R$ 1.234,56", "BRL")).toBe("1.234,56");
  expect(pastedAmount("abc", "BRL")).toBe("");
});

test("a typed amount is finished by the rule of its keys, not by a guess", () => {
  // The owner left the field in the middle of a number typed with its separators.
  expect(finishedAmount("1.00", "BRL")).toBe("100,00");
  expect(finishedAmount("1.", "BRL")).toBe("1,00");
  expect(finishedAmount("1,00", "USD")).toBe("100.00");
});

test("a thousands separator that the owner types stays where it was typed", () => {
  const typed = (text: string, currency = "USD") =>
    typedAmount(text, text.length, currency, false, true);
  // The key is seen at once, and the number goes on from it.
  expect(typed("1,")).toEqual({ text: "1,", caret: 2, manual: true });
  expect(typed("1,0")).toEqual({ text: "1,0", caret: 3, manual: true });
  expect(typed("1,00")).toEqual({ text: "1,00", caret: 4, manual: true });
  // Three digits complete the group: the text is the one that the field writes itself.
  expect(typed("1,000")).toEqual({ text: "1,000", caret: 5, manual: false });
  expect(typed("1,000,")).toEqual({ text: "1,000,", caret: 6, manual: true });
  // A fourth digit does not fit the group: the field groups again.
  expect(typed("1,0000")).toEqual({ text: "10,000", caret: 6, manual: false });
  // The decimals end the typing of the whole part.
  expect(typed("1,5.")).toEqual({ text: "15.", caret: 3, manual: false });
  // A separator has a digit before it.
  expect(typed(",")).toEqual({ text: "", caret: 0, manual: false });
  expect(typed("1,,")).toEqual({ text: "1,", caret: 2, manual: true });
  // The same with a point for thousands.
  expect(typed("1.", "BRL")).toEqual({ text: "1.", caret: 2, manual: true });
});

test("a separator that the field wrote is not kept as a typed one", () => {
  // "2.000" without its last digit is 200, not "2.00".
  expect(typedAmount("2.00", 4, "BRL").text).toBe("200");
  expect(typedAmount("1,", 2, "USD").text).toBe("1");
});

test("with a format chosen, a typed amount is read by its keys", () => {
  setNumberFormat("POINT");
  // A comma only groups: "1,00" in the middle of a number is one hundred.
  expect(parseAmount("1,00", "BRL")).toBe("100.00");
  expect(parseAmount("1,000.5", "BRL")).toBe("1000.50");
  expect(parseAmount("0.50", "BRL")).toBe("0.50");
  expect(parseAmount("1.5.5", "BRL")).toBeNull();
  expect(parseAmount("1.555", "BRL")).toBeNull();
  setNumberFormat("COMMA");
  expect(parseAmount("1.00", "USD")).toBe("100.00");
  expect(parseAmount("0,50", "USD")).toBe("0.50");
});

test("a stored amount is shown as the field writes it", () => {
  expect(editableAmount("1234.50", "BRL")).toBe("1.234,50");
  expect(editableAmount("1234.50", "USD")).toBe("1,234.50");
  expect(editableAmount("60.00", "BRL")).toBe("60,00");
  expect(editableAmount("-1500.00", "BRL")).toBe("-1.500,00");
});

// The owner's choice of separators lasts for one test.
afterEach(() => setNumberFormat(null));

test("with a decimal point chosen, every currency is written and typed with it", () => {
  setNumberFormat("POINT");
  // The symbol and its place stay the ones of the currency.
  expect(formatAmount("1234.50", "BRL").replace(/\s/g, " ")).toBe("R$ 1,234.50");
  expect(formatAmount("-80.00", "BRL").replace(/\s/g, " ")).toBe("-R$ 80.00");
  expect(typedAmount("2000", 4, "BRL")).toMatchObject({ text: "2,000", caret: 5 });
  expect(finishedAmount("2000", "BRL")).toBe("2,000.00");
  expect(editableAmount("1234.50", "BRL")).toBe("1,234.50");
  expect(parseAmount("2,000.50", "BRL")).toBe("2000.50");
  expect(parseAmount("1,234", "BRL")).toBe("1234.00");
  expect(formatPercent("12.5", "pt-BR")).toBe("12.5%");
  expect(formatQuantity("1234.5", "pt-BR")).toBe("1,234.5");
});

test("with a decimal comma chosen, a dollar amount is written with it too", () => {
  setNumberFormat("COMMA");
  expect(formatAmount("1234.50", "USD")).toBe("$1.234,50");
  expect(typedAmount("2000", 4, "USD")).toMatchObject({ text: "2.000", caret: 5 });
  expect(finishedAmount("2000", "USD")).toBe("2.000,00");
  expect(parseAmount("1.234", "USD")).toBe("1234.00");
  expect(formatPercent("12.5", "en")).toBe("12,5%");
});

test("without a choice, the currency gives the separators", () => {
  expect(formatAmount("1234.50", "USD")).toBe("$1,234.50");
  expect(finishedAmount("2000", "USD")).toBe("2,000.00");
  expect(finishedAmount("2000", "BRL")).toBe("2.000,00");
});
