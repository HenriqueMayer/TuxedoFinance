import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { worthQuery } from "../data/reports";
import { ratesQuery, useDeleteRate, useRecordRate } from "../data/wallet";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { parseDecimal } from "../lib/money";
import { sessionQuery, useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { autofocus } from "../ui/Window";
import { CURRENCIES } from "./settings";
import { Alert, values } from "./wallet";

type Currency = (typeof CURRENCIES)[number];

/** The exchange rates that the owner typed. The latest rate on or before a date converts it. */
export function RatesWindow() {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const { data: rates } = useSuspenseQuery(ratesQuery);
  const { data: worth } = useSuspenseQuery(worthQuery);
  const record = useRecordRate();
  const remove = useDeleteRate();
  const [invalid, setInvalid] = useState(false);
  const base = session.preferences?.base_currency ?? "BRL";
  const others = CURRENCIES.filter((code) => code !== base);
  const missing = worth.today.missing_currencies;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const rate = parseDecimal(typed.rate ?? "");
    setInvalid(rate === null);
    if (rate === null) return;
    const form = event.currentTarget;
    record.mutate(
      {
        from_currency: typed.from as Currency,
        rate,
        effective_date: typed.date || null,
      },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <p className="max-w-prose text-sm text-muted">{t.rates.help(base)}</p>
      {missing.length > 0 && <p className="text-sm">{t.rates.missing(missing.join(", "))}</p>}
      <form
        onSubmit={submit}
        className="flex flex-wrap items-start gap-4 rounded-(--radius-control) bg-sheet p-4"
        noValidate
      >
        <Field label={t.rates.from} errors={fieldMessages(record.error, "from_currency")}>
          {(control) => (
            <select
              {...control}
              name="from"
              className="field"
              defaultValue={missing[0] ?? others[0]}
            >
              {others.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label={t.rates.rate(base)}
          errors={invalid ? [t.rates.invalid] : fieldMessages(record.error, "rate")}
          className="w-44"
        >
          {(control) => (
            <input
              {...control}
              {...autofocus}
              name="rate"
              inputMode="decimal"
              className="field amount"
              autoComplete="off"
            />
          )}
        </Field>
        <Field label={t.entry.date} errors={fieldMessages(record.error, "effective_date")}>
          {(control) => (
            <input
              {...control}
              type="date"
              name="date"
              className="field"
              defaultValue={todayIso()}
            />
          )}
        </Field>
        <button type="submit" className="button-primary mt-[1.625rem]" disabled={record.isPending}>
          {t.rates.record}
        </button>
      </form>
      <Alert
        message={
          fieldMessages(record.error, "to_currency")[0] ??
          formMessage(record.error, t) ??
          formMessage(remove.error, t)
        }
      />
      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
          {t.rates.recorded}
        </h3>
        {rates.length === 0 && <p className="py-4 text-muted">{t.rates.empty}</p>}
        <ul className="divide-y divide-line">
          {rates.map((row) => (
            <li key={row.id} className="flex items-center gap-3 py-2.5">
              <span className="min-w-0 flex-1">
                <span className="amount block">
                  {t.rates.row(
                    row.from_currency,
                    Number(row.rate).toLocaleString(language, { maximumFractionDigits: 8 }),
                    row.to_currency,
                  )}
                </span>
                <span className="block text-sm text-muted">
                  {formatDate(row.effective_date, order)}
                </span>
              </span>
              <button
                type="button"
                className="action"
                disabled={remove.isPending}
                onClick={() => remove.mutate(row.id)}
              >
                {t.common.delete}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
