import { useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { type Analysis, type Origin, originQuery } from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, isMonth, monthLabel, monthOf, shortMonthLabel, todayIso } from "../lib/dates";
import { formatAmount, formatPercent } from "../lib/money";
import { useDateOrder } from "../session";
import { CHART, ShareBar, Swatch } from "../ui/charts";
import { ChevronRightIcon } from "../ui/icons";
import { OpenWindow } from "./host";

const ROW =
  "-mx-2 flex items-center gap-3 rounded-(--radius-control) px-2 py-2 transition-colors duration-150 hover:bg-ink/5";
const GROUP = "border-b border-line pb-2 text-sm font-medium text-muted";
const SHOWN_ENTRIES = 10;
// The parts of a composition that take a color. The others share one gray.
const PART_COLORS = [CHART.ink, CHART.accent, CHART.positive];

/** The name of an origin window: what a click on a month of the analysis opens. */
export function originId(
  section: "flows" | "category" | "worth" | "investments",
  month: string,
  currency = "",
  category: number | null = null,
): `origin:${string}` {
  return `origin:${section}:${month}:${currency}:${category ?? ""}`;
}

/**
 * What the values of one month of the analysis are made of. It opens above
 * the analysis window, which keeps its period and its place.
 *
 * The id is "origin:section:month:currency:category". The section says which
 * chart the owner clicked: the entries of the month, the entries of one
 * category, the parts of the net worth, or the investment operations.
 */
export function OriginWindow(props: { id: string }) {
  const t = useMessages();
  const language = useLanguage();
  const [, section, text = "", currency = "", categoryText = ""] = props.id.split(":");
  const month = isMonth(text) ? text : todayIso().slice(0, 7);
  const { data } = useSuspenseQuery(originQuery(month));
  const category = /^\d+$/.test(categoryText) ? Number(categoryText) : null;
  const entries = data.entries.filter((row) => !currency || row.currency === currency);
  const expenses = entries.filter((row) => row.flow === "EXPENSE");
  // The name of the category comes from its entries; a category has entries when its bar has a height.
  const name = expenses.find((row) => row.category_id === category)?.category_name;

  return (
    <div className="grid grid-cols-1 gap-6">
      <div>
        <p className="text-lg font-semibold">
          {section === "category" && name ? `${name} · ` : ""}
          {monthLabel(monthOf(data.month), language)}
        </p>
        <p className="text-sm text-muted">{t.analysis.originHelp[sectionKey(section)]}</p>
      </div>
      {section === "category" ? (
        <EntryList
          rows={expenses.filter((row) => row.category_id === category)}
          month={month}
          type="EXPENSE"
        />
      ) : section === "worth" ? (
        <WorthOrigin worth={data.worth} />
      ) : section === "investments" ? (
        <OperationOrigin found={data} />
      ) : (
        <>
          <section>
            <h3 className={GROUP}>{t.home.income}</h3>
            <EntryList
              rows={entries.filter((row) => row.flow === "INCOME")}
              month={month}
              type="INCOME"
            />
          </section>
          <section>
            <h3 className={GROUP}>{t.home.expenses}</h3>
            <EntryList rows={expenses} month={month} type="EXPENSE" />
          </section>
        </>
      )}
    </div>
  );
}

function sectionKey(section: string | undefined): "flows" | "category" | "worth" | "investments" {
  return section === "category" || section === "worth" || section === "investments"
    ? section
    : "flows";
}

/** Entries from the largest amount. Each one opens its window; the whole list is in Transactions. */
function EntryList(props: { rows: Origin["entries"]; month: string; type: "INCOME" | "EXPENSE" }) {
  const t = useMessages();
  const order = useDateOrder();
  const [all, setAll] = useState(false);
  if (props.rows.length === 0) return <p className="py-3 text-muted">{t.analysis.noEntries}</p>;
  const rows = all ? props.rows : props.rows.slice(0, SHOWN_ENTRIES);
  return (
    <>
      <ul className="divide-y divide-line">
        {rows.map((row) => (
          <li key={`${row.transaction_id}-${row.category_id}`}>
            <OpenWindow w={`transaction:${row.transaction_id}`} className={ROW}>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{row.title}</span>
                <span className="block truncate text-sm text-muted">
                  {row.category_name} · {formatDate(row.date, order)}
                  {row.installment_number !== null &&
                    row.installment_count !== null &&
                    ` · ${t.analysis.installment(row.installment_number, row.installment_count)}`}
                  {row.split && ` · ${t.analysis.split}`}
                </span>
              </span>
              <span
                className={`amount font-semibold ${row.flow === "INCOME" ? "text-positive" : ""}`}
              >
                {formatAmount(row.amount, row.currency)}
              </span>
            </OpenWindow>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        {props.rows.length > SHOWN_ENTRIES && (
          <button type="button" className="action" onClick={() => setAll(!all)}>
            {all ? t.analysis.fewer : t.analysis.allEntries(props.rows.length)}
          </button>
        )}
        <Link
          to="/transactions"
          search={{ month: props.month, type: props.type }}
          className="action"
        >
          {t.analysis.inTransactions}
          <ChevronRightIcon />
        </Link>
      </div>
    </>
  );
}

/** The accounts, the investments and the card statements of a month end. */
function WorthOrigin(props: { worth: Origin["worth"] }) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { worth } = props;
  const money = (amount: string | null) =>
    amount === null ? t.analysis.noRate : formatAmount(amount, worth.currency);
  const empty = <p className="py-3 text-muted">{t.analysis.nothing}</p>;
  return (
    <>
      <p className="-mt-3 text-sm text-muted">{t.analysis.asOf(formatDate(worth.as_of, order))}</p>
      <section>
        <h3 className={GROUP}>{t.home.worth.accounts}</h3>
        {worth.accounts.length === 0 && empty}
        <ul className="divide-y divide-line">
          {worth.accounts.map((row) => (
            <li key={row.id}>
              <OpenWindow w={`account:${row.id}`} className={ROW}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{row.name}</span>
                  <span className="block truncate text-sm text-muted">{row.bank_name}</span>
                </span>
                <span className="amount font-semibold">{money(row.amount)}</span>
              </OpenWindow>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className={GROUP}>{t.home.worth.investments}</h3>
        {worth.positions.length === 0 && empty}
        <ul className="divide-y divide-line">
          {worth.positions.map((row) => (
            <li key={row.id}>
              <OpenWindow w={`investment:${row.id}`} className={ROW}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{row.name}</span>
                  <span className="block truncate text-sm text-muted">{row.institution_name}</span>
                </span>
                <span className="amount font-semibold">{money(row.value)}</span>
              </OpenWindow>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className={GROUP}>{t.home.worth.debt}</h3>
        {worth.cards.length === 0 && empty}
        <ul className="divide-y divide-line">
          {worth.cards.map((row) => (
            <li key={`${row.card_id}-${row.month}`} className="flex items-center gap-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{row.card_name}</span>
                <span className="block truncate text-sm text-muted">
                  {t.analysis.statementOf(shortMonthLabel(monthOf(row.month), language))}
                </span>
              </span>
              <span className="amount font-semibold">{money(row.amount)}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

/** The operations of a month and the positions at its end. */
function OperationOrigin(props: { found: Origin }) {
  const t = useMessages();
  const order = useDateOrder();
  const { operations, worth } = props.found;
  return (
    <>
      <section>
        <h3 className={GROUP}>{t.analysis.operations}</h3>
        {operations.length === 0 && <p className="py-3 text-muted">{t.analysis.noOperations}</p>}
        <ul className="divide-y divide-line">
          {operations.map((row) => (
            <li key={`${row.kind}-${row.id ?? row.position_id}`}>
              <OpenWindow w={`investment:${row.position_id}`} className={ROW}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {t.analysis.kinds[row.kind]} · {row.name}
                  </span>
                  <span className="block truncate text-sm text-muted">
                    {row.institution_name} · {formatDate(row.date, order)}
                  </span>
                </span>
                <span
                  className={`amount font-semibold ${row.kind === "YIELD" ? "text-positive" : ""}`}
                >
                  {formatAmount(row.value, row.currency)}
                </span>
              </OpenWindow>
            </li>
          ))}
        </ul>
      </section>
      <section className="grid gap-3">
        <h3 className={GROUP}>{t.analysis.positionsOn(formatDate(worth.as_of, order))}</h3>
        {worth.positions.length === 0 ? (
          <p className="text-muted">{t.analysis.nothing}</p>
        ) : (
          <Positions rows={worth.positions} currency={worth.currency} />
        )}
      </section>
    </>
  );
}

/** Positions as one bar of parts and a list: each with its value and its part of the total. */
export function Positions(props: { rows: Analysis["positions"]; currency: string }) {
  const language = useLanguage();
  const parts = props.rows.map((row, index) => ({
    ...row,
    color: PART_COLORS[index] ?? CHART.quiet,
  }));
  return (
    <>
      <ShareBar
        parts={parts.map((part) => ({
          name: `${part.id}`,
          color: part.color,
          percent: Number(part.share ?? 0),
        }))}
      />
      <ul className="divide-y divide-line">
        {parts.map((part) => (
          <li key={part.id}>
            <OpenWindow w={`investment:${part.id}`} className={ROW}>
              <Swatch color={part.color} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{part.name}</span>
                <span className="block truncate text-sm text-muted">{part.institution_name}</span>
              </span>
              <span className="text-right">
                <span className="amount block font-semibold">
                  {formatAmount(part.value, props.currency)}
                </span>
                {part.share !== null && (
                  <span className="amount block text-sm text-muted">
                    {formatPercent(part.share, language)}
                  </span>
                )}
              </span>
            </OpenWindow>
          </li>
        ))}
      </ul>
    </>
  );
}
