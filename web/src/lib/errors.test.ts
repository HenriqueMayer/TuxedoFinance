import { expect, test } from "vitest";
import { ApiError } from "../api/client";
import { en } from "../i18n/en";
import { fieldMessages, formMessage } from "./errors";

test("no error gives no message", () => {
  expect(formMessage(null, en)).toBeUndefined();
});

test("a request without a response is a network message", () => {
  expect(formMessage(new ApiError(0, {}), en)).toBe(en.errors.network);
});

test("a throttled request has its own message", () => {
  expect(formMessage(new ApiError(429, { detail: "Too many requests." }), en)).toBe(
    en.errors.tooMany,
  );
});

test("the server message without a field is shown as it is", () => {
  const error = new ApiError(400, { errors: { __all__: ["Wrong password."] } });
  expect(formMessage(error, en)).toBe("Wrong password.");
});

test("field errors alone give no form message, because each field shows its own", () => {
  const error = new ApiError(400, { errors: { email: ["Required."] } });
  expect(formMessage(error, en)).toBeUndefined();
  expect(fieldMessages(error, "email")).toEqual(["Required."]);
  expect(fieldMessages(error, "username")).toEqual([]);
});

test("an unknown failure has a generic message", () => {
  expect(formMessage(new Error("boom"), en)).toBe(en.errors.unexpected);
  expect(formMessage(new ApiError(500, {}), en)).toBe(en.errors.unexpected);
});
