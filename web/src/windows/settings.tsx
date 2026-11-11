import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useId } from "react";
import type { components } from "../api/schema";
import { setLanguage, useLanguage, useMessages } from "../i18n";
import { currencySymbol } from "../lib/money";
import { setTheme, useTheme } from "../lib/theme";
import { sessionQuery, useSavePreferences, useSignOut } from "../session";
import { ChevronRightIcon, ExchangeIcon, TagIcon } from "../ui/icons";
import { Segmented } from "../ui/Segmented";
import { type Choice, Select } from "../ui/Select";
import { OpenWindow } from "./host";

type Preferences = components["schemas"]["PreferencesOut"];

export const CURRENCIES: Preferences["base_currency"][] = [
  "BRL",
  "USD",
  "EUR",
  "GBP",
  "JPY",
  "CHF",
];

const ROW_LINK =
  "flex items-center gap-2.5 text-sm font-medium transition-colors duration-150 hover:text-accent-ink";

/** The currencies as the choices of a select: the code, and the name in the interface language. */
export function useCurrencyChoices(codes: readonly string[] = CURRENCIES): Choice[] {
  const language = useLanguage();
  const names = new Intl.DisplayNames([language], { type: "currency" });
  return codes.map((code) => {
    const name = names.of(code) ?? "";
    return { value: code, label: code, hint: name.charAt(0).toUpperCase() + name.slice(1) };
  });
}

export function SettingsWindow() {
  const t = useMessages();
  const language = useLanguage();
  const theme = useTheme();
  const navigate = useNavigate();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const signOut = useSignOut();
  const currencyId = useId();

  const save = useSavePreferences();
  const currencies = useCurrencyChoices();

  const preferences = session.preferences;
  if (!session.user || !preferences) return null;

  return (
    <div className="grid grid-cols-1 gap-5">
      {/* One row for each choice: the name on the left, a small control on the right. */}
      <div className="divide-y divide-line *:py-3.5 *:first:pt-0">
        <Segmented
          inline
          label={t.settings.language}
          value={language}
          onChange={setLanguage}
          options={[
            { value: "en", label: "English" },
            { value: "pt-BR", label: "Português" },
          ]}
        />
        <Segmented
          inline
          label={t.settings.theme}
          value={theme}
          onChange={setTheme}
          options={[
            { value: "light", label: t.settings.light },
            { value: "dark", label: t.settings.dark },
          ]}
        />
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-0.5">
            <label htmlFor={currencyId} className="text-sm font-medium">
              {t.settings.currency}
            </label>
            <p id={`${currencyId}-help`} className="max-w-sm text-sm text-muted">
              {t.settings.currencyHelp}
            </p>
          </div>
          {/* One control: the symbol of the chosen currency, then its code. */}
          <Select
            compact
            id={currencyId}
            aria-describedby={`${currencyId}-help`}
            className="shrink-0"
            lead={currencySymbol(preferences.base_currency)}
            value={preferences.base_currency}
            options={currencies}
            onChange={(value) =>
              save.mutate({ base_currency: value as Preferences["base_currency"] })
            }
          />
        </div>
        <Segmented
          inline
          label={t.settings.numberFormat}
          value={preferences.number_format}
          onChange={(value) => save.mutate({ number_format: value })}
          // An example number shows each format: the thousands and the decimals.
          options={[
            { value: "COMMA", label: "1.234,56" },
            { value: "POINT", label: "1,234.56" },
          ]}
        />
        <Segmented
          inline
          label={t.settings.dateFormat}
          value={preferences.date_format}
          onChange={(value) => save.mutate({ date_format: value })}
          // An example date shows each order without letters to decode.
          options={[
            { value: "DMY", label: "31/12/2026" },
            { value: "MDY", label: "12/31/2026" },
          ]}
        />
        <OpenWindow w="categories" className={ROW_LINK}>
          <TagIcon />
          {t.categories.manage}
          <span className="ml-auto text-muted">
            <ChevronRightIcon />
          </span>
        </OpenWindow>
        <OpenWindow w="rates" className={ROW_LINK}>
          <ExchangeIcon />
          {t.rates.title}
          <span className="ml-auto text-muted">
            <ChevronRightIcon />
          </span>
        </OpenWindow>
      </div>
      {save.isError && (
        <p role="alert" className="text-sm text-negative">
          {t.settings.saveFailed}
        </p>
      )}
      <div className="flex items-center justify-between gap-4 border-t border-line pt-5">
        <p className="text-sm text-muted">
          {t.settings.signedInAs}{" "}
          <span className="font-medium text-ink">{session.user.username}</span>
        </p>
        <button
          type="button"
          className="action"
          disabled={signOut.isPending}
          onClick={() =>
            signOut.mutate(undefined, {
              onSuccess: () => navigate({ to: "/login", replace: true }),
            })
          }
        >
          {t.nav.signOut}
        </button>
      </div>
    </div>
  );
}
