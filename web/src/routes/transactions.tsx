import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { type Transaction, transactionsQuery } from "../data/ledger";
import { useLanguage, useMessages } from "../i18n";
import { dayLabel, isMonth, monthLabel, shiftMonth, todayIso } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { Segmented } from "../ui/Segmented";
import { instrumentLabel } from "../windows/entry";
import { OpenWindow } from "../windows/host";

/** The filters of the list. They live in the address, so they survive Back and a reload. */
export type TransactionSearch = {
  /** "YYYY-MM", or "all" for every month. Absent means the current month. */
  month?: string;
  q?: string;
  type?: "EXPENSE" | "INCOME";
  page?: number;
};

export function validateTransactionSearch(search: Record<string, unknown>): TransactionSearch {
  return {
    month: search.month === "all" || isMonth(search.month) ? search.month : undefined,
    q: typeof search.q === "string" && search.q ? search.q : undefined,
    type: search.type === "EXPENSE" || search.type === "INCOME" ? search.type : undefined,
    page: Number(search.page) > 1 ? Math.floor(Number(search.page)) : undefined,
  };
}

export function TransactionsPage(props: {
  search: TransactionSearch;
  /** Change filters in the address without a history entry and without moving the page. */
  onChange: (changes: TransactionSearch) => void;
}) {
  const t = useMessages();
  const language = useLanguage();
  const { search, onChange } = props;
  const thisMonth = todayIso().slice(0, 7);
  const month = search.month ?? thisMonth;
  const everyMonth = month === "all";

  const { data, isPending, isError, refetch, isPlaceholderData } = useQuery(
    transactionsQuery({
      month: everyMonth ? undefined : month,
      q: search.q,
      type: search.type,
      page: search.page,
    }),
  );

  // The search box answers at once; the address follows after a short pause.
  const [text, setText] = useState(search.q ?? "");
  useEffect(() => setText(search.q ?? ""), [search.q]);
  useEffect(() => {
    if (text === (search.q ?? "")) return;
    const timer = setTimeout(() => onChange({ q: text || undefined, page: undefined }), 250);
    return () => clearTimeout(timer);
  }, [text, search.q, onChange]);

  const filtered = Boolean(search.q || search.type);
  const currency = data?.items[0]?.currency ?? "BRL";

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{t.nav.transactions}</h1>
          <OpenWindow w="import" className="link text-sm font-medium">
            {t.imports.start}
          </OpenWindow>
        </div>
        <nav aria-label={t.entry.date} className="flex flex-wrap items-center gap-1">
          {!everyMonth && (
            <>
              <button
                type="button"
                className="button-quiet px-3"
                aria-label={t.transactions.previousMonth}
                onClick={() => onChange({ month: shiftMonth(month, -1), page: undefined })}
              >
                ‹
              </button>
              <p className="min-w-36 text-center font-medium" aria-live="polite">
                {monthLabel(month, language)}
              </p>
              <button
                type="button"
                className="button-quiet px-3"
                aria-label={t.transactions.nextMonth}
                onClick={() => onChange({ month: shiftMonth(month, 1), page: undefined })}
              >
                ›
              </button>
            </>
          )}
          <button
            type="button"
            className="button-quiet sm:ml-2"
            aria-pressed={everyMonth}
            onClick={() => onChange({ month: everyMonth ? undefined : "all", page: undefined })}
          >
            {everyMonth ? t.transactions.thisMonth : t.transactions.allMonths}
          </button>
        </nav>
      </div>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <label className="grid min-w-56 flex-1 gap-1.5 text-sm font-medium">
          {t.transactions.search}
          <input
            type="search"
            className="field font-normal"
            placeholder={t.transactions.searchPlaceholder}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <Segmented
          label={t.entry.type}
          value={search.type ?? ""}
          onChange={(value) => onChange({ type: value || undefined, page: undefined })}
          options={[
            { value: "", label: t.common.all },
            { value: "EXPENSE", label: t.transactions.expenses },
            { value: "INCOME", label: t.transactions.income },
          ]}
        />
      </div>

      {data && (
        <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3" aria-live="polite">
          <Total label={t.transactions.income} amount={data.income} currency={currency} positive />
          <Total label={t.transactions.expenses} amount={data.expense} currency={currency} />
          <div className="ml-auto self-end text-sm text-muted">
            {t.transactions.count(data.count)}
          </div>
        </dl>
      )}

      <section className={`mt-4 ${isPlaceholderData ? "opacity-60" : ""}`} aria-busy={isPending}>
        {isPending && <p className="py-10 text-muted">{t.common.loading}</p>}
        {isError && (
          <div role="alert" className="grid justify-items-start gap-3 py-10">
            <p>{t.common.loadFailed}</p>
            <button type="button" className="button-quiet" onClick={() => refetch()}>
              {t.common.retry}
            </button>
          </div>
        )}
        {data && data.count === 0 && (
          <div className="grid justify-items-start gap-3 py-10">
            {filtered ? (
              <>
                <p className="text-muted">{t.transactions.noMatch}</p>
                <button
                  type="button"
                  className="button-quiet"
                  onClick={() => onChange({ q: undefined, type: undefined, page: undefined })}
                >
                  {t.common.clear}
                </button>
              </>
            ) : (
              <>
                <p className="text-lg font-medium">{t.transactions.empty}</p>
                <p className="text-muted">{t.transactions.emptyHelp}</p>
                <OpenWindow w="add" className="button-accent">
                  {t.entry.add}
                </OpenWindow>
              </>
            )}
          </div>
        )}
        {data && data.count > 0 && <Rows items={data.items} />}
      </section>

      {data && data.pages > 1 && (
        <nav
          className="mt-6 flex items-center justify-between gap-4"
          aria-label={t.common.page(data.page, data.pages)}
        >
          <button
            type="button"
            className="button-quiet"
            disabled={data.page <= 1}
            onClick={() => onChange({ page: data.page - 1 })}
          >
            {t.common.previous}
          </button>
          <p className="text-sm text-muted">{t.common.page(data.page, data.pages)}</p>
          <button
            type="button"
            className="button-quiet"
            disabled={data.page >= data.pages}
            onClick={() => onChange({ page: data.page + 1 })}
          >
            {t.common.next}
          </button>
        </nav>
      )}
    </>
  );
}

function Total(props: { label: string; amount: string; currency: string; positive?: boolean }) {
  return (
    <div>
      <dt className="text-sm text-muted">{props.label}</dt>
      <dd className={`amount text-2xl font-semibold ${props.positive ? "text-positive" : ""}`}>
        {formatAmount(props.amount, props.currency)}
      </dd>
    </div>
  );
}

/** Rows grouped by day. Each row opens its entry in a window. */
function Rows(props: { items: Transaction[] }) {
  const language = useLanguage();
  const days: { date: string; items: Transaction[] }[] = [];
  for (const item of props.items) {
    const last = days.at(-1);
    if (last && last.date === item.date) last.items.push(item);
    else days.push({ date: item.date, items: [item] });
  }
  return days.map((day) => (
    <section key={day.date} className="mt-6 first:mt-2">
      <h2 className="border-b border-line pb-2 text-sm font-medium text-muted">
        {dayLabel(day.date, language)}
      </h2>
      <ul className="divide-y divide-line">
        {day.items.map((item) => (
          <Row key={item.id} item={item} />
        ))}
      </ul>
    </section>
  ));
}

function Row(props: { item: Transaction }) {
  const t = useMessages();
  const { item } = props;
  const income = item.transaction_type === "INCOME";
  const shown = item.month_amount ?? item.amount;
  const partial = item.month_amount != null && item.month_amount !== item.amount;
  return (
    <li>
      <OpenWindow
        w={`transaction:${item.id}`}
        className="-mx-2 flex items-center gap-4 rounded-(--radius-control) px-2 py-3 hover:bg-surface"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{item.title}</span>
          <span className="block truncate text-sm text-muted">
            {item.category.name} · {instrumentLabel(item.instrument)}
            {item.installments > 1 && ` · ${t.transactions.installment(item.installments)}`}
            {item.is_fixed && ` · ${t.transactions.recurring}`}
          </span>
        </span>
        <span className="text-right">
          <span className={`amount block font-semibold ${income ? "text-positive" : ""}`}>
            {income ? "+" : "−"}
            {formatAmount(shown, item.currency)}
          </span>
          {partial && (
            <span className="amount block text-sm text-muted">
              {t.transactions.ofTotal(formatAmount(item.amount, item.currency))}
            </span>
          )}
        </span>
      </OpenWindow>
    </li>
  );
}
