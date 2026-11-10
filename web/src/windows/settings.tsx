import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useId } from "react";
import type { components } from "../api/schema";
import { setLanguage, useLanguage, useMessages } from "../i18n";
import { currencySymbol } from "../lib/money";
import { setTheme, useTheme } from "../lib/theme";
import { sessionQuery, useSavePreferences, useSignOut } from "../session";
import { ChevronDownIcon, ChevronRightIcon, ExchangeIcon, TagIcon } from "../ui/icons";
import { Segmented } from "../ui/Segmented";
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

export function SettingsWindow() {
  const t = useMessages();
  const language = useLanguage();
  const theme = useTheme();
  const navigate = useNavigate();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const signOut = useSignOut();
  const currencyId = useId();

  const save = useSavePreferences();

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
          {/* The symbol of the chosen currency, then its code. */}
          <span className="relative inline-flex h-8 shrink-0 items-center rounded-(--radius-control) border border-control bg-surface text-sm has-focus-visible:outline-2 has-focus-visible:outline-accent has-focus-visible:outline-offset-2">
            <span
              aria-hidden="true"
              className="amount grid h-full min-w-9 place-items-center border-line border-r px-2 font-medium text-muted"
            >
              {currencySymbol(preferences.base_currency)}
            </span>
            <select
              id={currencyId}
              className="h-full cursor-pointer appearance-none rounded-r-(--radius-control) bg-surface pr-7 pl-2.5 font-medium outline-none"
              value={preferences.base_currency}
              aria-describedby={`${currencyId}-help`}
              onChange={(event) =>
                save.mutate({ base_currency: event.target.value as Preferences["base_currency"] })
              }
            >
              {CURRENCIES.map((code) => (
                <option key={code}>{code}</option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-2 text-muted">
              <ChevronDownIcon />
            </span>
          </span>
        </div>
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
