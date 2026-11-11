import { ApiError } from "../api/client";
import type { Messages } from "../i18n/en";

/** The message to show for a failed request that has no field to attach to. */
export function formMessage(error: unknown, messages: Messages): string | undefined {
  if (!error) return undefined;
  if (!(error instanceof ApiError)) return messages.errors.unexpected;
  if (error.status === 0) return messages.errors.network;
  if (error.status === 429) return messages.errors.tooMany;
  return error.messages()[0] ?? (error.body.errors ? undefined : messages.errors.unexpected);
}

/** The messages of one field of a failed request. */
export function fieldMessages(error: unknown, field: string): string[] {
  return error instanceof ApiError ? error.messages(field) : [];
}
