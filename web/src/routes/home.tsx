import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  type CategorySpending,
  type DueRow,
  type Home,
  type HomeBlock,
  homeQuery,
} from "../data/reports";
import { useMessages } from "../i18n";
import { formatDate } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { sessionQuery, useDateOrder } from "../session";
import { OpenWindow } from "../windows/host";
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

function Block(props: { block: HomeBlock; home: Home }) {
  if (props.block === "left") return <LeftBlock home={props.home} />;
  if (props.block === "spending") return <SpendingBlock rows={props.home.spending} />;
  return <DueBlock rows={props.home.due} />;
}

function Title(props: { children: ReactNode }) {
  return <span className="block text-sm font-medium text-muted">{props.children}</span>;
}

/** The answer of the month: what is left after the expenses. The whole block opens the month. */
function LeftBlock(props: { home: Home }) {
  const t = useMessages();
  const results = props.home.result;
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
