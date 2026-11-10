import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useId } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { setLanguage, useLanguage, useMessages } from "../i18n";
import { setTheme, useTheme } from "../lib/theme";
import { sessionQuery, useSignOut } from "../session";
import { Segmented } from "../ui/Segmented";
import { OpenWindow } from "./host";

type Preferences = components["schemas"]["PreferencesOut"];

const CURRENCIES: Preferences["base_currency"][] = ["BRL", "USD", "EUR", "GBP", "JPY", "CHF"];

export function SettingsWindow() {
  const t = useMessages();
  const language = useLanguage();
  const theme = useTheme();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const signOut = useSignOut();
  const currencyId = useId();
  const dateId = useId();

  const save = useMutation({
    mutationFn: (body: components["schemas"]["PreferencesIn"]) =>
      unwrap(api.PATCH("/api/session/preferences", { body })),
    onSuccess: (preferences) =>
      queryClient.setQueryData(sessionQuery.queryKey, { ...session, preferences }),
  });

  const preferences = session.preferences;
  if (!session.user || !preferences) return null;

  return (
    <div className="grid gap-6">
      <Segmented
        label={t.settings.language}
        value={language}
        onChange={setLanguage}
        options={[
          { value: "en", label: "English" },
          { value: "pt-BR", label: "Português" },
        ]}
      />
      <Segmented
        label={t.settings.theme}
        value={theme}
        onChange={setTheme}
        options={[
          { value: "light", label: t.settings.light },
          { value: "dark", label: t.settings.dark },
        ]}
      />
      <div className="grid gap-1.5">
        <label htmlFor={currencyId} className="text-sm font-medium">
          {t.settings.currency}
        </label>
        <select
          id={currencyId}
          className="field w-fit"
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
        <p id={`${currencyId}-help`} className="text-sm text-muted">
          {t.settings.currencyHelp}
        </p>
      </div>
      <div className="grid gap-1.5">
        <label htmlFor={dateId} className="text-sm font-medium">
          {t.settings.dateFormat}
        </label>
        <select
          id={dateId}
          className="field w-fit"
          value={preferences.date_format}
          onChange={(event) =>
            save.mutate({ date_format: event.target.value as Preferences["date_format"] })
          }
        >
          <option value="DMY">DD/MM/YYYY</option>
          <option value="MDY">MM/DD/YYYY</option>
        </select>
      </div>
      <OpenWindow w="categories" className="link w-fit">
        {t.categories.manage}
      </OpenWindow>
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
          className="button-quiet"
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
