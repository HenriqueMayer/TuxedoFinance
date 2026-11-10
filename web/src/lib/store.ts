import { useSyncExternalStore } from "react";

/**
 * A value saved in localStorage that React components can read and change.
 * Used for per-device choices only (language, theme). Server data lives in the
 * query cache; view state lives in the address.
 */
export function createStoredValue<T extends string>(key: string, fallback: () => T) {
  const listeners = new Set<() => void>();

  function read(): T {
    try {
      return (localStorage.getItem(key) as T | null) ?? fallback();
    } catch {
      return fallback(); // Storage can be blocked; the choice then lasts for the page.
    }
  }

  let value = read();

  function set(next: T) {
    value = next;
    try {
      localStorage.setItem(key, next);
    } catch {
      // See read().
    }
    for (const listener of listeners) listener();
  }

  function subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    get: () => value,
    set,
    use: () => useSyncExternalStore(subscribe, () => value),
  };
}
