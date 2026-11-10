import createClient, { type Middleware } from "openapi-fetch";
import { currentLanguage } from "../i18n";
import type { paths } from "./schema";

/** The body of every error response of the API. */
export type ApiErrorBody = {
  detail?: string;
  /** Messages by field name. `__all__` holds messages without a field. */
  errors?: Record<string, string[]>;
};

/** A response with an error status. `status` 0 means that no response arrived. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.detail ?? `Request failed (${status})`);
  }

  /** Messages for one field, or the messages without a field when `field` is omitted. */
  messages(field = "__all__"): string[] {
    return this.body.errors?.[field] ?? [];
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

const headers: Middleware = {
  onRequest({ request }) {
    request.headers.set("Accept-Language", currentLanguage());
    if (!SAFE_METHODS.has(request.method)) {
      // Django compares this header with the csrftoken cookie.
      request.headers.set("X-CSRFToken", cookie("csrftoken") ?? "");
    }
    return request;
  },
};

/**
 * The typed API client. Its `fetch` option is the single seam for data: the
 * public demonstration replaces it with an in-browser implementation.
 */
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
  // The demonstration build answers from recorded data. Another build has no such code.
  ...(import.meta.env.MODE === "demo"
    ? {
        fetch: (request: Request) =>
          import("../demo/fetch").then((demo) => demo.demoFetch(request)),
      }
    : {}),
});
api.use(headers);

/** Return the data of a call, or throw `ApiError`. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, {});
  }
  if (!result.response.ok) {
    const body = result.error && typeof result.error === "object" ? result.error : {};
    throw new ApiError(result.response.status, body as ApiErrorBody);
  }
  return result.data as T;
}
