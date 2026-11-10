import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  type Closing,
  type ClosingAccount,
  closingQuery,
  useCloseMonth,
  useClosingAdjust,
  useClosingBalance,
  useClosingUnadjust,
  useReopenMonth,
} from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, monthLabel, monthOf, shiftMonth, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, formatAmount, parseAmount, sameAmount } from "../lib/money";
import { CategoryBars, DueRows } from "../routes/home";
import { useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { Alert, parseBalance, values } from "./wallet";

/**
 * The closing of a month. It opens on the month that waits for it and stays
 * on a month until the owner moves to another one.
 */
export function ClosingWindow() {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { data: first } = useSuspenseQuery(closingQuery());
  // After the closing, the server would name the next month. The window keeps its month.
  const [month, setMonth] = useState(() => monthOf(first.month));
  // Another month replaces the content in place when it arrives.
  const review = useQuery({ ...closingQuery(month), placeholderData: keepPreviousData });
  const data = review.data ?? first;
  const shown = monthOf(data.month);
  const name = monthLabel(shown, language);
  const money = (amount: string) => formatAmount(amount, data.currency);
  const check = data.accounts[0]?.date;

  return (
    <div className="grid grid-cols-1 gap-8">
      <div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-lg font-medium">{name}</p>
          <div className="flex gap-1">
            <button
              type="button"
              className="button-quiet min-h-9 px-3"
              aria-label={t.closing.previousMonth}
              onClick={() => setMonth(shiftMonth(month, -1))}
            >
              ‹
            </button>
            <button
              type="button"
              className="button-quiet min-h-9 px-3"
              aria-label={t.closing.nextMonth}
              disabled={month >= todayIso().slice(0, 7)}
              onClick={() => setMonth(shiftMonth(month, 1))}
            >
              ›
            </button>
          </div>
        </div>
        <p className="mt-1 max-w-prose text-sm text-muted">
          {data.is_closed && data.closed_on
            ? `${t.closing.closedOn(formatDate(data.closed_on, order))}${data.changed_since ? ` ${t.closing.changed}` : ""}`
            : t.closing.intro}
        </p>
      </div>

      <section className="grid gap-3">
        <h3 className="font-medium">{t.closing.balances}</h3>
        {check ? (
          <p className="max-w-prose text-sm text-muted">
            {t.closing.balancesHelp(formatDate(check, order))}
          </p>
        ) : (
          <p className="text-sm text-muted">{t.closing.noAccounts}</p>
        )}
        <ul className="divide-y divide-line border-y border-line">
          {data.accounts.map((account) => (
            <li key={account.account_id} className="py-3">
              <AccountCheck
                // The key shows the saved balance when the server answers.
                key={`${data.month}-${account.statement}-${account.adjusted}`}
                month={data.month}
                account={account}
              />
            </li>
          ))}
        </ul>
        {data.open_items.length > 0 && (
          <div className="mt-2">
            <h4 className="text-sm font-medium text-muted">{t.closing.openItems}</h4>
            <DueRows rows={data.open_items} />
          </div>
        )}
      </section>

      <section className="grid gap-3">
        <h3 className="font-medium">{t.closing.result}</h3>
        <div>
          <p className="text-sm text-muted">{t.closing.leftOver}</p>
          <p
            className={`amount text-3xl font-semibold ${Number(data.result.result) < 0 ? "text-negative" : ""}`}
          >
            {money(data.result.result)}
          </p>
        </div>
        <dl className="flex flex-wrap gap-x-10 gap-y-2 text-sm">
          <div>
            <dt className="text-muted">{t.closing.income}</dt>
            <dd className="amount font-semibold text-positive">{money(data.result.income)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t.closing.expenses}</dt>
            <dd className="amount font-semibold">{money(data.result.expenses)}</dd>
          </div>
        </dl>
        {data.result.limit !== null && data.result.left !== null && (
          <p className="text-sm">
            {Number(data.result.left) < 0
              ? t.closing.overLimit(
                  money(data.result.left.replace("-", "")),
                  money(data.result.limit),
                )
              : t.closing.withinLimit(money(data.result.left), money(data.result.limit))}
          </p>
        )}
        <p className="text-sm">
          {t.closing.worth(money(data.worth.net_worth))}
          {Number(data.worth.change) !== 0 && (
            <span className="text-muted">
              {" · "}
              {Number(data.worth.change) > 0
                ? t.closing.worthMore(money(data.worth.change))
                : t.closing.worthLess(money(data.worth.change.replace("-", "")))}
            </span>
          )}
        </p>
        {data.spending.length > 0 && (
          <div className="mt-2 max-w-xl">
            <h4 className="mb-3 text-sm font-medium text-muted">{t.closing.spending}</h4>
            <CategoryBars rows={data.spending} />
          </div>
        )}
      </section>

      <CloseForm key={data.month} data={data} name={name} />
    </div>
  );
}

/** One account: the recorded balance, the balance of the bank, and their difference. */
function AccountCheck(props: { month: string; account: ClosingAccount }) {
  const t = useMessages();
  const { account, month } = props;
  const save = useClosingBalance();
  const adjust = useClosingAdjust();
  const unadjust = useClosingUnadjust();
  const [invalid, setInvalid] = useState(false);
  const money = (amount: string) => formatAmount(amount, account.currency);
  const busy = save.isPending || adjust.isPending || unadjust.isPending;

  function typed(text: string) {
    const empty = text.trim() === "";
    const balance = empty ? null : parseBalance(text, account.currency);
    setInvalid(!empty && balance === null);
    if (!empty && balance === null) return;
    if (
      balance === account.statement ||
      (balance !== null && sameAmount(balance, account.statement))
    ) {
      return; // Nothing was typed.
    }
    save.mutate({ month, account_id: account.account_id, balance });
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{account.name}</p>
          <p className="amount text-sm text-muted">{t.closing.inApp(money(account.tracked))}</p>
        </div>
        <input
          aria-label={t.closing.atBank(account.name)}
          aria-invalid={invalid}
          placeholder={t.closing.bankBalance}
          inputMode="decimal"
          autoComplete="off"
          className="field amount w-56"
          disabled={busy}
          defaultValue={
            account.statement === null ? "" : editableAmount(account.statement, account.currency)
          }
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
          onBlur={(event) => typed(event.currentTarget.value)}
        />
      </div>
      {invalid && <p className="text-sm text-negative">{t.closing.balanceInvalid}</p>}
      {account.adjusted && (
        <p className="text-sm">
          <span className="text-muted">{t.closing.adjusted} </span>
          <button
            type="button"
            className="link"
            disabled={busy}
            onClick={() => unadjust.mutate({ month, account_id: account.account_id })}
          >
            {t.closing.removeAdjustment}
          </button>
        </p>
      )}
      {!account.adjusted && account.difference !== null && Number(account.difference) === 0 && (
        <p className="text-sm text-muted">{t.closing.matches}</p>
      )}
      {!account.adjusted && account.difference !== null && Number(account.difference) !== 0 && (
        <p className="text-sm">
          {t.closing.difference(money(account.difference))}{" "}
          <span className="text-muted">{t.closing.differenceHelp} </span>
          <button
            type="button"
            className="link"
            disabled={busy}
            onClick={() =>
              adjust.mutate({
                month,
                account_id: account.account_id,
                difference: account.difference ?? "0",
              })
            }
          >
            {t.closing.adjust}
          </button>
        </p>
      )}
      <Alert
        message={
          fieldMessages(adjust.error, "difference")[0] ??
          formMessage(save.error, t) ??
          formMessage(adjust.error, t) ??
          formMessage(unadjust.error, t)
        }
      />
    </div>
  );
}

/** The limit from the next month, and the closing itself. */
function CloseForm(props: { data: Closing; name: string }) {
  const t = useMessages();
  const language = useLanguage();
  const { data } = props;
  const close = useCloseMonth();
  const reopen = useReopenMonth();
  const [invalid, setInvalid] = useState(false);
  const next = data.next_limit;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = (values(event).limit ?? "").trim();
    const limit = typed === "" ? null : parseAmount(typed, data.currency);
    setInvalid(typed !== "" && limit === null);
    if (typed !== "" && limit === null) return;
    // The same limit again is not a change.
    const changed = limit !== null && !sameAmount(limit, next.amount);
    close.mutate({ month: data.month, next_limit: changed ? limit : null });
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <h3 className="font-medium">{t.closing.next(monthLabel(monthOf(next.month), language))}</h3>
      <Field
        label={`${t.plan.limit.amount} (${data.currency})`}
        errors={invalid ? [t.plan.limit.invalid] : fieldMessages(close.error, "next_limit")}
        help={next.amount === null ? t.closing.nextNone : t.closing.nextHelp}
        className="max-w-sm"
      >
        {(control) => (
          <input
            {...control}
            // The key shows the saved limit after the closing.
            key={next.amount ?? ""}
            name="limit"
            inputMode="decimal"
            className="field amount"
            autoComplete="off"
            defaultValue={next.amount === null ? "" : editableAmount(next.amount, data.currency)}
          />
        )}
      </Field>
      <Alert message={formMessage(close.error, t) ?? formMessage(reopen.error, t)} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        {data.is_closed ? (
          <button
            type="button"
            className="button-quiet"
            disabled={reopen.isPending}
            onClick={() => reopen.mutate({ month: data.month })}
          >
            {t.closing.reopen}
          </button>
        ) : (
          <span />
        )}
        <button type="submit" className="button-primary" disabled={close.isPending}>
          {data.is_closed ? t.closing.closeAgain : t.closing.close(props.name)}
        </button>
      </div>
    </form>
  );
}
