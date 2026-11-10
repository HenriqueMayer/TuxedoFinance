import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import {
  HOME_BLOCKS,
  type HomeBlock,
  homeQuery,
  monthQuery,
  type TrendRow,
  type WorthMonth,
  worthQuery,
} from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, shiftMonth, shortMonthLabel } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { CategoryBars, DueRows } from "../routes/home";
import { sessionQuery, useSavePreferences } from "../session";
import { OpenWindow } from "./host";

/** The analysis of one month. Its month lives in the address, so Back and a link keep it. */
export function MonthWindow(props: {
  month: string | undefined;
  onMonth: (month: string) => void;
}) {
  const t = useMessages();
  const language = useLanguage();
  // Not a suspense query: another month keeps this one on screen while it loads.
  const { data, isPlaceholderData, isError, refetch } = useQuery(monthQuery(props.month));
  if (isError) {
    return (
      <div role="alert" className="grid justify-items-start gap-3">
        <p>{t.common.loadFailed}</p>
        <button type="button" className="button-quiet" onClick={() => refetch()}>
          {t.common.retry}
        </button>
      </div>
    );
  }
  if (!data) return <p className="text-muted">{t.common.loading}</p>;
  const month = data.month.slice(0, 7);

  return (
    <div className={`grid gap-6 ${isPlaceholderData ? "opacity-60" : ""}`}>
      <nav aria-label={t.home.monthTitle} className="flex items-center justify-between gap-2">
        <button
          type="button"
          className="button-quiet px-3"
          aria-label={t.transactions.previousMonth}
          onClick={() => props.onMonth(shiftMonth(month, -1))}
        >
          ‹
        </button>
        <p className="text-lg font-semibold" aria-live="polite">
          {monthLabel(month, language)}
        </p>
        <button
          type="button"
          className="button-quiet px-3"
          aria-label={t.transactions.nextMonth}
          onClick={() => props.onMonth(shiftMonth(month, 1))}
        >
          ›
        </button>
      </nav>

      {data.result.length === 0 && <p className="text-muted">{t.home.noEntries}</p>}
      {data.result.map((result) => (
        <dl key={result.currency} className="flex flex-wrap gap-x-10 gap-y-3">
          <div>
            <dt className="text-sm text-muted">{t.home.blocks.left}</dt>
            <dd
              className={`amount text-2xl font-semibold ${Number(result.left) < 0 ? "text-negative" : ""}`}
            >
              {formatAmount(result.left, result.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted">{t.home.income}</dt>
            <dd className="amount text-2xl font-semibold text-positive">
              {formatAmount(result.income, result.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted">{t.home.expenses}</dt>
            <dd className="amount text-2xl font-semibold">
              {formatAmount(result.expenses, result.currency)}
            </dd>
          </div>
        </dl>
      ))}

      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">{t.home.trend}</h3>
        <Trend rows={data.trend} language={language} />
      </section>

      {data.spending.length > 0 && (
        <section>
          <h3 className="mb-4 border-b border-line pb-2 text-sm font-medium text-muted">
            {t.home.byCategory}
          </h3>
          <CategoryBars rows={data.spending} detailed />
        </section>
      )}
    </div>
  );
}

/**
 * Expenses and income of each month as a table with bars. A table, not a
 * drawn chart: each value is text that a screen reader and a search can read.
 */
function Trend(props: { rows: TrendRow[]; language: string }) {
  const t = useMessages();
  const largest = Math.max(
    ...props.rows.map((row) => Math.max(Number(row.income), Number(row.expenses))),
    1,
  );
  if (props.rows.length === 0) return <p className="py-4 text-muted">{t.home.noEntries}</p>;
  return (
    <table className="mt-2 w-full text-sm">
      <thead className="sr-only">
        <tr>
          <th>{t.home.monthTitle}</th>
          <th>{t.home.income}</th>
          <th>{t.home.expenses}</th>
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row) => (
          <tr key={`${row.month}-${row.currency}`} className="border-b border-line last:border-0">
            <th scope="row" className="w-28 py-2 pr-3 text-left font-normal text-muted">
              {monthLabel(row.month.slice(0, 7), props.language).replace(/ (de )?\d{4}$/, "")}
            </th>
            <td className="py-2">
              <Bar
                amount={row.income}
                largest={largest}
                currency={row.currency}
                tone="bg-positive"
              />
              <Bar amount={row.expenses} largest={largest} currency={row.currency} tone="bg-ink" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Bar(props: { amount: string; largest: number; currency: string; tone: string }) {
  const value = Number(props.amount);
  return (
    <span className="flex items-center gap-2 py-0.5">
      <span
        aria-hidden="true"
        className={`block h-2 rounded-full ${props.tone}`}
        style={{ width: `${value <= 0 ? 0 : Math.max(1, (value / props.largest) * 70)}%` }}
      />
      <span className="amount">{formatAmount(props.amount, props.currency)}</span>
    </span>
  );
}

/** Every invoice that is due, for the Due soon block. */
export function DueWindow() {
  const t = useMessages();
  const { data } = useSuspenseQuery(homeQuery);
  if (data.due.length === 0) return <p className="text-muted">{t.home.nothingDue}</p>;
  return <DueRows rows={data.due} />;
}

/** Show, hide and reorder the Home blocks. Each change is saved at once. */
export function HomeBlocksWindow() {
  const t = useMessages();
  const session = useQuery(sessionQuery);
  const save = useSavePreferences();
  const shown = session.data?.preferences?.home_blocks ?? [];
  // Shown blocks first, in their order; hidden blocks after them.
  const all = [...shown, ...HOME_BLOCKS.filter((block) => !shown.includes(block))];

  function toggle(block: HomeBlock) {
    save.mutate({
      home_blocks: shown.includes(block)
        ? shown.filter((item) => item !== block)
        : [...shown, block],
    });
  }

  function move(block: HomeBlock, offset: -1 | 1) {
    const index = shown.indexOf(block);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= shown.length) return;
    const next = [...shown];
    [next[index], next[target]] = [next[target] as HomeBlock, next[index] as HomeBlock];
    save.mutate({ home_blocks: next });
  }

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted">{t.home.editHelp}</p>
      <ul className="divide-y divide-line border-y border-line">
        {all.map((block) => {
          const index = shown.indexOf(block);
          const name = t.home.blocks[block];
          return (
            <li key={block} className="flex items-center gap-3 py-2.5">
              <label className="flex min-w-0 flex-1 items-center gap-3">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={index >= 0}
                  disabled={save.isPending}
                  onChange={() => toggle(block)}
                />
                <span className="truncate">{name}</span>
              </label>
              <button
                type="button"
                className="button-quiet min-h-9 px-3"
                aria-label={t.home.moveUp(name)}
                disabled={save.isPending || index <= 0}
                onClick={() => move(block, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="button-quiet min-h-9 px-3"
                aria-label={t.home.moveDown(name)}
                disabled={save.isPending || index < 0 || index === shown.length - 1}
                onClick={() => move(block, 1)}
              >
                ↓
              </button>
            </li>
          );
        })}
      </ul>
      {save.isError && (
        <p role="alert" className="text-sm text-negative">
          {t.settings.saveFailed}
        </p>
      )}
    </div>
  );
}

/** What the net worth is made of today, and its last twelve month ends. */
export function WorthWindow() {
  const t = useMessages();
  const language = useLanguage();
  const { data } = useSuspenseQuery(worthQuery);
  const { today } = data;
  const money = (amount: string) => formatAmount(amount, today.currency);
  const parts = [
    { label: t.home.worth.accounts, amount: today.accounts, sign: "" },
    { label: t.home.worth.investments, amount: today.investments, sign: "" },
    { label: t.home.worth.credits, amount: today.card_credits, sign: "" },
    { label: t.home.worth.debt, amount: today.card_debt, sign: "−", help: t.home.worth.debtHelp },
  ].filter((part) => part.label !== t.home.worth.credits || Number(part.amount) !== 0);
  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm text-muted">{t.home.blocks.worth}</p>
        <p
          className={`amount text-3xl font-semibold ${Number(today.net_worth) < 0 ? "text-negative" : ""}`}
        >
          {money(today.net_worth)}
        </p>
      </div>
      <dl className="divide-y divide-line border-y border-line">
        {parts.map((part) => (
          <div key={part.label} className="flex items-baseline justify-between gap-4 py-2.5">
            <dt>
              {part.label}
              {part.help && <span className="block text-sm text-muted">{part.help}</span>}
            </dt>
            <dd className="amount font-semibold">
              {Number(part.amount) !== 0 && part.sign}
              {money(part.amount)}
            </dd>
          </div>
        ))}
      </dl>
      {!today.complete && (
        <p className="text-sm text-muted">
          {t.home.worth.incomplete(today.missing_currencies.join(", "))}{" "}
          <OpenWindow w="rates" className="link">
            {t.rates.add}
          </OpenWindow>
        </p>
      )}
      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
          {t.home.worth.trend}
        </h3>
        <WorthTrend rows={data.months} currency={today.currency} language={language} />
      </section>
    </div>
  );
}

/** The net worth of each month end as a table with bars. Each value is text. */
function WorthTrend(props: { rows: WorthMonth[]; currency: string; language: string }) {
  const t = useMessages();
  const largest = Math.max(...props.rows.map((row) => Number(row.net_worth)), 1);
  return (
    <table className="mt-2 w-full text-sm">
      <thead className="sr-only">
        <tr>
          <th>{t.home.monthTitle}</th>
          <th>{t.home.blocks.worth}</th>
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row) => (
          <tr key={row.month} className="border-b border-line last:border-0">
            <th scope="row" className="w-20 py-2 pr-3 text-left font-normal text-muted">
              {shortMonthLabel(row.month.slice(0, 7), props.language)}
            </th>
            <td className={`py-2 ${Number(row.net_worth) < 0 ? "text-negative" : ""}`}>
              <Bar
                amount={row.net_worth}
                largest={largest}
                currency={props.currency}
                tone="bg-ink"
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
