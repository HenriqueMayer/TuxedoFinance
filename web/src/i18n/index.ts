import { createStoredValue } from "../lib/store";
import { en, type Messages } from "./en";
import { ptBR } from "./pt-BR";

export type Language = "en" | "pt-BR";

const MESSAGES: Record<Language, Messages> = { en, "pt-BR": ptBR };

const language = createStoredValue<Language>("tuxedo.language", () =>
  navigator.language.toLowerCase().startsWith("pt") ? "pt-BR" : "en",
);

export function currentLanguage(): Language {
  return language.get();
}

/** Select a language and mark the document with it. `main.tsx` calls this once at startup. */
export function setLanguage(next: Language) {
  language.set(next);
  document.documentElement.lang = next;
}

/** The messages of the selected language. The component renders again when the language changes. */
export function useMessages(): Messages {
  return MESSAGES[language.use()];
}

export function useLanguage(): Language {
  return language.use();
}
