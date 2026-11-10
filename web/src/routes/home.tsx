import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  type CategorySpending,
  type DueRow,
  type Home,
  type HomeBlock,
  homeQuery,
} from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { formatDate } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { sessionQuery, useDateOrder } from "../session";
import { Meter } from "../ui/Meter";
import { OpenWindow } from "../windows/host";
import { goalStatus } from "./plan";
import { StatusLabel } from "./wallet";

const BLOCK = "rounded-(--radius-window) border border-line bg-surface p-5";

/** Home answers the owner's questions with blocks. The owner chooses the blocks and their order. */
export function HomePage() {
  const t = useMessages();
  const session = useQuery(sessionQuery);
  const home = useQuery(homeQuery);
  const blocks = session.data?.preferences?.home_blocks ?? [];

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t.nav.home}</h1>
        <OpenWindow w="home-blocks" className="button-quiet">
          {t.home.edit}
        </OpenWindow>
      </div>
      {home.isPending && <p className="py-10 text-muted">{t.common.loading}</p>}
      {home.isError && (
        <div role="alert" className="grid justify-items-start gap-3 py-10">
          <p>{t.common.loadFailed}</p>
          <button type="button" className="button-quiet" onClick={() => home.refetch()}>
            {t.common.retry}
          </button>
        </div>
      )}
      {home.data && <CaughtUp days={home.data.days_since_last_entry} />}
      {home.data && blocks.length === 0 && <p className="py-10 text-muted">{t.home.noBlocks}</p>}
      {home.data && (
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {blocks.map((block) => (
            <Block key={block} block={block} home={home.data} />
          ))}
        </div>
      )}
    </>
  );
}

/**
 * One line about the habit of recording. Up to date on the day of an entry or
 * the day after; from the second day without one, it asks for the missing days.
 */
function CaughtUp(props: { days: number | null }) {
  const t = useMessages();
  const behind = props.days === null || props.days >= 2;
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <span className={behind ? "" : "text-muted"}>
        {props.days === null
          ? t.home.start
          : props.days === 0
            ? t.home.upToDate
            : t.home.lastEntry(props.days)}
      </span>
      {behind && (
        <OpenWindow w="add" className="link font-medium">
          {props.days === null ? t.entry.add : t.home.catchUp}
        </OpenWindow>
      )}
    </p>
  );
}

function Block(props: { block: HomeBlock; home: Home }) {
  if (props.block === "left") return <LeftBlock home={props.home} />;
  if (props.block === "spending") return <SpendingBlock rows={props.home.spending} />;
  if (props.block === "worth") return <WorthBlock worth={props.home.worth} />;
  if (props.block === "goals") return <GoalsBlock goals={props.home.goals} />;
  return <DueBlock rows={props.home.due} />;
}

function Title(props: { children: ReactNode }) {
  return <span className="block text-sm font-medium text-muted">{props.children}</span>;
}

/**
 * The answer of the month. With a limit, it is what is left of the limit;
 * without one, the income minus the expenses. The whole block opens the month.
 */
function LeftBlock(props: { home: Home }) {
  const t = useMessages();
  const results = props.home.result;
  const { limit } = props.home;
  if (limit) {
    const money = (amount: string) => formatAmount(amount, limit.currency);
    const over = Number(limit.left) < 0;
    return (
      <OpenWindow
        w="month"
        className={`${BLOCK} block transition-shadow hover:shadow-md lg:col-span-2`}
      >
        <Title>{over ? t.home.limit.over : t.home.blocks.left}</Title>
        <span
          className={`amount mt-2 block text-4xl font-semibold tracking-tight ${over ? "text-negative" : ""}`}
        >
          {money(limit.left.replace("-", ""))}
        </span>
        <span className="mt-3 block max-w-xl">
          <Meter value={limit.expenses} total={limit.amount} />
        </span>
        <span className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
          <span className="text-muted">{t.home.limit.of(money(limit.amount))}</span>
          {limit.per_day !== null && (
            <span className="text-muted">{t.home.limit.perDay(money(limit.per_day))}</span>
          )}
          <span>
            <span className="text-muted">{t.home.expenses} </span>
            <span className="amount font-medium">{money(limit.expenses)}</span>
          </span>
          <span>
            <span className="text-muted">{t.home.income} </span>
            <span className="amount font-medium text-positive">{money(limit.income)}</span>
          </span>
        </span>
      </OpenWindow>
    );
  }
  return (
    <OpenWindow
      w="month"
      className={`${BLOCK} block transition-shadow hover:shadow-md lg:col-span-2`}
    >
      <Title>{t.home.blocks.left}</Title>
      {results.length === 0 && <span className="mt-3 block text-muted">{t.home.noEntries}</span>}
      {results.map((result) => (
        <span key={result.currency} className="mt-2 block">
          <span
            className={`amount block text-4xl font-semibold tracking-tight ${Number(result.left) < 0 ? "text-negative" : ""}`}
          >
            {formatAmount(result.left, result.currency)}
          </span>
          <span className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
            <span>
              <span className="text-muted">{t.home.income} </span>
              <span className="amount font-medium text-positive">
                {formatAmount(result.income, result.currency)}
              </span>
            </span>
            <span>
              <span className="text-muted">{t.home.expenses} </span>
              <span className="amount font-medium">
                {formatAmount(result.expenses, result.currency)}
              </span>
            </span>
            <span>
              <span className="text-muted">{t.home.lastMonth} </span>
              <span className="amount font-medium">
                {formatAmount(result.previous_expenses, result.currency)}
              </span>
            </span>
          </span>
        </span>
      ))}
    </OpenWindow>
  );
}

/** Bars of the largest categories. A bar length compares amounts; the amount beside it is the value. */
export function CategoryBars(props: {
  rows: CategorySpending[];
  limit?: number;
  detailed?: boolean;
}) {
  const shown = props.limit ? props.rows.slice(0, props.limit) : props.rows;
  const largest = Math.max(...props.rows.map((row) => Number(row.amount)), 1);
  return (
    <span className="grid gap-3">
      {shown.map((row) => (
        <span key={`${row.currency}-${row.category_id}`} className="block">
          <span className="flex items-baseline justify-between gap-3">
            <span className="truncate">{row.name}</span>
            <span className="amount font-medium">{formatAmount(row.amount, row.currency)}</span>
          </span>
          <span className="mt-1.5 block h-2 rounded-full bg-line" aria-hidden="true">
            <span
              className="block h-full rounded-full bg-ink"
              style={{ width: `${Math.max(2, (Number(row.amount) / largest) * 100)}%` }}
            />
          </span>
          {props.detailed &&
            row.children.map((child) => (
              <span
                key={child.category_id}
                className="mt-1.5 flex items-baseline justify-between gap-3 pl-4 text-sm text-muted"
              >
                <span className="truncate">{child.name}</span>
                <span className="amount">{formatAmount(child.amount, row.currency)}</span>
              </span>
            ))}
        </span>
      ))}
    </span>
  );
}

function SpendingBlock(props: { rows: CategorySpending[] }) {
  const t = useMessages();
  const limit = 5;
  return (
    <OpenWindow w="month" className={`${BLOCK} block transition-shadow hover:shadow-md`}>
      <Title>{t.home.blocks.spending}</Title>
      <span className="mt-4 block">
        {props.rows.length === 0 ? (
          <span className="text-muted">{t.home.noSpending}</span>
        ) : (
          <CategoryBars rows={props.rows} limit={limit} />
        )}
      </span>
      {props.rows.length > limit && (
        <span className="mt-3 block text-sm text-muted">
          {t.home.more(props.rows.length - limit)}
        </span>
      )}
    </OpenWindow>
  );
}

/** One line for each invoice that is due. Each line opens its invoice. */
export function DueRows(props: { rows: DueRow[] }) {
  const t = useMessages();
  const order = useDateOrder();
  return (
    <ul className="divide-y divide-line">
      {props.rows.map((row) => (
        <li key={`${row.kind}-${row.invoice_id ?? row.transaction_id}-${row.month}`}>
          <OpenWindow
            // An invoice opens its window; a month of a repeating expense opens its schedule.
            w={
              row.kind === "invoice"
                ? `invoice:${row.invoice_id ?? 0}`
                : `schedule:${row.transaction_id ?? 0}`
            }
            className="-mx-2 flex items-center gap-3 rounded-(--radius-control) px-2 py-2.5 hover:bg-sheet"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{row.title}</span>
              <span className="block text-sm">
                <span className="text-muted">
                  {t.wallet.due(formatDate(row.due_date, order))} ·{" "}
                </span>
                <StatusLabel invoice={row} t={t} />
              </span>
            </span>
            <span className="amount font-semibold">{formatAmount(row.amount, row.currency)}</span>
          </OpenWindow>
        </li>
      ))}
    </ul>
  );
}

function DueBlock(props: { rows: DueRow[] }) {
  const t = useMessages();
  const limit = 4;
  return (
    <section className={BLOCK}>
      <h2 className="flex items-center justify-between gap-3">
        <Title>{t.home.blocks.due}</Title>
        {props.rows.length > limit && (
          <OpenWindow w="due" className="link text-sm">
            {t.home.seeAll}
          </OpenWindow>
        )}
      </h2>
      <div className="mt-2">
        {props.rows.length === 0 ? (
          <p className="mt-2 text-muted">{t.home.nothingDue}</p>
        ) : (
          <DueRows rows={props.rows.slice(0, limit)} />
        )}
      </div>
    </section>
  );
}

/** The net worth of today and how it moved since the end of the month before. */
function WorthBlock(props: { worth: Home["worth"] }) {
  const t = useMessages();
  const { worth } = props;
  // The server gives the change; here it only loses its sign for the sentence.
  const change = Number(worth.change);
  const amount = formatAmount(worth.change.replace("-", ""), worth.currency);
  return (
    <OpenWindow w="worth" className={`${BLOCK} block transition-shadow hover:shadow-md`}>
      <Title>{t.home.blocks.worth}</Title>
      <span
        className={`amount mt-2 block text-3xl font-semibold tracking-tight ${Number(worth.net_worth) < 0 ? "text-negative" : ""}`}
      >
        {formatAmount(worth.net_worth, worth.currency)}
      </span>
      <span className="mt-2 block text-sm text-muted">
        {change === 0
          ? t.home.worth.same
          : change > 0
            ? t.home.worth.more(amount)
            : t.home.worth.less(amount)}
      </span>
      {!worth.complete && (
        <span className="mt-2 block text-sm text-muted">{t.home.worth.incompleteShort}</span>
      )}
    </OpenWindow>
  );
}

/** The active goals and how far each one is. A goal opens its window. */
function GoalsBlock(props: { goals: Home["goals"] }) {
  const t = useMessages();
  const language = useLanguage();
  const limit = 4;
  return (
    <section className={BLOCK}>
      <h2>
        <Title>{t.home.blocks.goals}</Title>
      </h2>
      {props.goals.length === 0 && (
        <p className="mt-2">
          <span className="text-muted">{t.home.goals.none} </span>
          <OpenWindow w="new-goal" className="link font-medium">
            {t.home.goals.add}
          </OpenWindow>
        </p>
      )}
      <ul className="mt-2 divide-y divide-line">
        {props.goals.slice(0, limit).map((goal) => (
          <li key={goal.id}>
            <OpenWindow
              w={`goal:${goal.id}`}
              className="-mx-2 block rounded-(--radius-control) px-2 py-2.5 hover:bg-sheet"
            >
              <span className="flex items-baseline justify-between gap-3">
                <span className="truncate font-medium">{goal.name}</span>
                <span className="amount font-semibold">
                  {formatAmount(goal.saved, goal.currency)}
                </span>
              </span>
              <span className="mt-1.5 block">
                <Meter value={goal.saved} total={goal.target_amount} />
              </span>
              <span className="mt-1 block text-sm text-muted">
                {goal.percent}% · {goalStatus(goal, t, language)}
              </span>
            </OpenWindow>
          </li>
        ))}
      </ul>
      {props.goals.length > limit && (
        <p className="mt-2 text-sm text-muted">{t.home.more(props.goals.length - limit)}</p>
      )}
    </section>
  );
}
