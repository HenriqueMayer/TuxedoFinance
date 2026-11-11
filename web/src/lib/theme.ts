import { createStoredValue } from "./store";

export type Theme = "light" | "dark";

// public/theme.js applies the same key before the first paint.
const theme = createStoredValue<Theme>("tuxedo.theme", () =>
  matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
);

export function setTheme(next: Theme) {
  theme.set(next);
  document.documentElement.dataset.theme = next;
}

export function useTheme(): Theme {
  return theme.use();
}
