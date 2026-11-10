import { expect, test } from "vitest";
import { editableAmount, formatAmount, parseAmount } from "./money";

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
  expect(editableAmount("1234.50", "BRL")).toBe("1234,50");
  expect(editableAmount("1234.50", "USD")).toBe("1234.50");
  expect(parseAmount(editableAmount("1234.50", "BRL"), "BRL")).toBe("1234.50");
});
