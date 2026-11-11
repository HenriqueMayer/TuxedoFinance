import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  type ScheduleMonth,
  scheduleQuery,
  useChangeAmountFrom,
  useMonthAction,
  useRemoveAmountChange,
} from "../data/ledger";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, monthLabel } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { formatAmount, parseAmount } from "../lib/money";
import { useDateOrder } from "../session";
import { AmountInput } from "../ui/AmountInput";
import { MonthField } from "../ui/DateField";
import { Field } from "../ui/Field";

/** The months of a repeating entry: confirm, skip or restore a month, and change the amount from a month. */
export function ScheduleWindow(props: { id: number }) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { data } = useSuspenseQuery(scheduleQuery(props.id));
  const act = useMonthAction(props.id);
  const change = useChangeAmountFrom(props.id);
  const remove = useRemoveAmountChange(props.id);
  const [amountInvalid, setAmountInvalid] = useState(false);
  const money = (amount: string) => formatAmount(amount, data.currency);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const typed = Object.fromEntries(new FormData(form)) as Record<string, string>;
    const amount = parseAmount(typed.amount ?? "", data.currency);
    setAmountInvalid(amount === null);
    if (amount === null) return;
    change.mutate({ month: typed.month ?? "", amount }, { onSuccess: () => form.reset() });
  }

  const actionError = formMessage(act.error, t) ?? fieldMessages(act.error, "month")[0];
  return (
    <div className="grid grid-cols-1 gap-6">
      <p className="text-lg font-semibold">{data.title}</p>

      <ul className="divide-y divide-line border-y border-line">
        {data.months.map((month) => (
          <Month
            key={month.month}
            month={month}
            label={monthLabel(month.month.slice(0, 7), language)}
            date={month.cash_date ? formatDate(month.cash_date, order) : ""}
            amount={money(month.amount)}
            pending={act.isPending}
            onAction={(action) => act.mutate({ month: month.month.slice(0, 7), action })}
          />
        ))}
      </ul>
      {actionError && (
        <p role="alert" className="text-sm text-negative">
          {actionError}
        </p>
      )}

      <form
        onSubmit={submit}
        className="grid gap-4 rounded-(--radius-control) bg-sheet p-4"
        noValidate
      >
        <h3 className="font-medium">{t.schedule.changeFrom}</h3>
        <div className="flex flex-wrap items-end gap-4">
          <Field label={t.schedule.from} errors={fieldMessages(change.error, "month")}>
            {(control) => (
              <MonthField
                {...control}
                name="month"
                defaultValue={data.default_change_month.slice(0, 7)}
              />
            )}
          </Field>
          <Field
            label={`${t.schedule.newAmount} (${data.currency})`}
            errors={amountInvalid ? [t.entry.amountInvalid] : fieldMessages(change.error, "amount")}
            className="w-40"
          >
            {(control) => (
              <AmountInput
                currency={data.currency}
                {...control}
                name="amount"
                className="field amount"
              />
            )}
          </Field>
          <button type="submit" className="button-primary" disabled={change.isPending}>
            {t.schedule.apply}
          </button>
        </div>
        {formMessage(change.error, t) && (
          <p role="alert" className="text-sm text-negative">
            {formMessage(change.error, t)}
          </p>
        )}
        {data.amount_changes.length > 0 && (
          <ul className="divide-y divide-line border-t border-line">
            {data.amount_changes.map((row) => (
              <li key={row.month} className="flex items-center gap-3 py-2">
                <span className="flex-1">
                  <span className="amount font-medium">{money(row.amount)}</span>{" "}
                  <span className="text-sm text-muted">
                    {t.schedule.fromMonth(monthLabel(row.month.slice(0, 7), language))}
                  </span>
                </span>
                <button
                  type="button"
                  className="action"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(row.month.slice(0, 7))}
                >
                  {t.schedule.remove}
                </button>
              </li>
            ))}
          </ul>
        )}
      </form>
    </div>
  );
}

function Month(props: {
  month: ScheduleMonth;
  label: string;
  date: string;
  amount: string;
  pending: boolean;
  onAction: (action: "confirm" | "skip" | "restore") => void;
}) {
  const t = useMessages();
  const { month } = props;
  const skipped = month.status === "SKIPPED";
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{props.label}</span>
        <span className="block text-sm">
          <span className="text-muted">{props.date}</span>
          {props.date && " · "}
          <span className={month.awaiting ? "font-medium text-negative" : "text-muted"}>
            {month.awaiting ? t.schedule.awaiting : t.schedule.status[month.status]}
          </span>
        </span>
      </span>
      <span className={`amount font-semibold ${skipped ? "text-muted line-through" : ""}`}>
        {props.amount}
      </span>
      <span className="flex gap-2">
        {month.can_confirm && (
          <button
            type="button"
            className={month.awaiting ? "button-primary min-h-9" : "button-quiet min-h-9"}
            disabled={props.pending}
            aria-label={`${t.schedule.confirm}: ${props.label}`}
            onClick={() => props.onAction("confirm")}
          >
            {t.schedule.confirm}
          </button>
        )}
        {month.can_skip && (
          <button
            type="button"
            className="button-quiet min-h-9"
            disabled={props.pending}
            aria-label={`${t.schedule.skip}: ${props.label}`}
            onClick={() => props.onAction("skip")}
          >
            {t.schedule.skip}
          </button>
        )}
        {month.can_restore && (
          <button
            type="button"
            className="button-quiet min-h-9"
            disabled={props.pending}
            aria-label={`${t.schedule.undo}: ${props.label}`}
            onClick={() => props.onAction("restore")}
          >
            {t.schedule.undo}
          </button>
        )}
      </span>
    </li>
  );
}
