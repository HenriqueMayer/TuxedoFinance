/**
 * A path of this application to return to after sign-in, or undefined.
 * An absolute or protocol-relative address is dropped, so a crafted link
 * cannot send the owner to another site.
 */
export function localPath(value: unknown): string | undefined {
  return typeof value === "string" && /^\/(?![/\\])/.test(value) ? value : undefined;
}
