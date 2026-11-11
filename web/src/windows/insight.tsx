import { useSuspenseQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  accountItemQuery,
  cardItemQuery,
  type ItemShare,
  investmentItemQuery,
} from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { monthOf, shortMonthLabel } from "../lib/dates";
import { formatAmount, formatPercent } from "../lib/money";
import { BarChart, CHART, LineChart, type Series } from "../ui/charts";
import { ChartIcon } from "../ui/icons";
import { Meter } from "../ui/Meter";
import { useOpenAbove } from "./host";

type Kind = "investment" | "account" | "card";

const GROUP = "border-b border-line pb-2 text-sm font-medium text-muted";

/**
 * The button of an item of the Wallet that opens its analysis. The analysis
 * opens above the window of the item, which stays as it is.
 */
export function AnalyzeButton(props: { kind: Kind; id: number }) {
  const t = useMessages();
  const open = useOpenAbove();
  return (
    <button
      type="button"
      className="action shrink-0"
      onClick={(event) => open(`insight:${props.kind}:${props.id}`, event.currentTarget)}
    >
      <ChartIcon />
      {t.insight.open}
    </button>
  );
}

/**
 * The analysis of one item of the Wallet over twelve months: the item month
 * by month, what moved, and the item beside every item of its kind. The id
 * is "insight:kind:number".
 */
export function InsightWindow(props: { id: string }) {
  const [, kind, text = ""] = props.id.split(":");
  const id = Number(text);
  if (!Number.isInteger(id)) return null;
  if (kind === "investment") return <InvestmentInsight id={id} />;
  if (kind === "account") return <AccountInsight id={id} />;
  if (kind === "card") return <CardInsight id={id} />;
  return null;
}

/** A short text for a value of an axis: "2 mil". */
function useAxisText(): (value: number) => string {
  const language = useLanguage();
  const format = new Intl.NumberFormat(language, { notation: "compact", maximumFractionDigits: 1 });
  return (value) => format.format(value);
}

function useMonthLabels(months: { month: string }[]): string[] {
  const language = useLanguage();
  return months.map((row) => shortMonthLabel(monthOf(row.month), language));
}

/** The name of the item, what the analysis covers, and its main figures. */
function Head(props: { name: string; detail: string; children: ReactNode }) {
  const t = useMessages();
  return (
    <div className="grid gap-4">
      <div>
        <p className="text-lg font-semibold">{props.name}</p>
        <p className="text-sm text-muted">
          {props.detail} · {t.insight.period}
        </p>
      </div>
      <dl className="flex flex-wrap gap-x-10 gap-y-4">{props.children}</dl>
    </div>
  );
}

function Figure(props: { label: string; value: string; tone?: string; main?: boolean }) {
  return (
    <div>
      <dt className="text-sm text-muted">{props.label}</dt>
      <dd
        className={`amount font-semibold ${props.main ? "text-2xl" : "text-lg"} ${props.tone ?? ""}`}
      >
        {props.value}
      </dd>
    </div>
  );
}

function Part(props: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <h3 className={GROUP}>{props.title}</h3>
      {props.children}
    </section>
  );
}

/**
 * The item beside every item of its kind: its value of the total, one bar
 * that compares the two, and the list of the items with the part of each.
 */
function Comparison(props: {
  title: string;
  /** For example "of R$ 12.250,37 invested". */
  of: (total: string) => string;
  share: ItemShare;
  currency: string;
}) {
  const t = useMessages();
  const language = useLanguage();
  const { share } = props;
  const money = (amount: string) => formatAmount(amount, props.currency);
  return (
    <Part title={props.title}>
      <div className="grid gap-2">
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="amount text-2xl font-semibold">{money(share.value)}</span>
          <span className="text-muted">{props.of(money(share.total))}</span>
          {share.percent !== null && (
            <span className="amount ml-auto rounded-full bg-ink px-2.5 py-0.5 text-sm font-semibold text-sheet">
              {formatPercent(share.percent, language)}
            </span>
          )}
        </p>
        <Meter value={share.value} total={share.total} />
      </div>
      {share.items.length > 1 && (
        <ul className="divide-y divide-line">
          {share.items.map((item) => (
            <li
              key={item.id}
              aria-current={item.current ? "true" : undefined}
              className="flex items-center gap-3 py-2"
            >
              <span
                aria-hidden="true"
                className={`size-2.5 shrink-0 rounded-full ${item.current ? "bg-ink" : "bg-line"}`}
              />
              <span className="min-w-0 flex-1">
                <span className={`block truncate ${item.current ? "font-semibold" : ""}`}>
                  {item.name}
                  {item.current && (
                    <span className="ml-2 text-xs font-medium text-accent-ink">
                      {t.insight.thisOne}
                    </span>
                  )}
                </span>
                <span className="block truncate text-sm text-muted">{item.detail}</span>
              </span>
              <span className="text-right">
                <span className={`amount block ${item.current ? "font-semibold" : ""}`}>
                  {money(item.value)}
                </span>
                {item.share !== null && (
                  <span className="amount block text-sm text-muted">
                    {formatPercent(item.share, language)}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Part>
  );
}

function InvestmentInsight(props: { id: number }) {
  const t = useMessages();
  const { data } = useSuspenseQuery(investmentItemQuery(props.id));
  const axisText = useAxisText();
  const labels = useMonthLabels(data.months);
  const money = (amount: string) => formatAmount(amount, data.currency);
  const bars = (
    name: string,
    color: string,
    read: (row: (typeof data.months)[number]) => string,
  ): Series => ({
    name,
    color,
    values: data.months.map((row) => Number(read(row))),
    texts: data.months.map((row) => money(read(row))),
  });
  return (
    <div className="grid grid-cols-1 gap-7">
      <Head name={data.name} detail={data.institution_name}>
        <Figure label={t.insight.valueToday} value={money(data.value)} main />
        <Figure label={t.insight.yields} value={money(data.yields)} tone="text-positive" />
        <Figure label={t.insight.deposits} value={money(data.deposits)} />
        <Figure label={t.insight.withdrawals} value={money(data.withdrawals)} />
        {data.gain !== null && (
          <Figure
            label={t.insight.gain}
            value={money(data.gain)}
            tone={Number(data.gain) < 0 ? "text-negative" : "text-positive"}
          />
        )}
      </Head>
      <Part title={t.insight.valueByMonth}>
        <LineChart
          title={t.insight.valueByMonth}
          labels={labels}
          height={190}
          axisText={axisText}
          series={[{ ...bars(t.insight.value, CHART.ink, (row) => row.value), strong: true }]}
        />
      </Part>
      <Part title={t.insight.moved}>
        <BarChart
          title={t.insight.moved}
          labels={labels}
          height={180}
          axisText={axisText}
          series={[
            bars(t.insight.deposits, CHART.ink, (row) => row.deposits),
            bars(t.insight.withdrawals, CHART.quiet, (row) => row.withdrawals),
            bars(t.insight.yields, CHART.positive, (row) => row.yields),
          ]}
        />
      </Part>
      <Comparison
        title={t.insight.amongInvestments}
        of={t.insight.ofInvested}
        share={data.share}
        currency={data.base_currency}
      />
    </div>
  );
}

function AccountInsight(props: { id: number }) {
  const t = useMessages();
  const { data } = useSuspenseQuery(accountItemQuery(props.id));
  const axisText = useAxisText();
  const labels = useMonthLabels(data.months);
  const money = (amount: string) => formatAmount(amount, data.currency);
  const change = Number(data.change);
  return (
    <div className="grid grid-cols-1 gap-7">
      <Head name={data.name} detail={data.bank_name}>
        <Figure
          label={t.insight.balanceToday}
          value={money(data.balance)}
          tone={Number(data.balance) < 0 ? "text-negative" : ""}
          main
        />
        <Figure
          label={t.insight.change}
          value={`${change > 0 ? "+" : ""}${money(data.change)}`}
          tone={change > 0 ? "text-positive" : change < 0 ? "text-negative" : ""}
        />
        <Figure label={t.insight.inflow} value={money(data.inflow)} tone="text-positive" />
        <Figure label={t.insight.outflow} value={money(data.outflow)} />
      </Head>
      <Part title={t.insight.balanceByMonth}>
        <LineChart
          title={t.insight.balanceByMonth}
          labels={labels}
          height={190}
          axisText={axisText}
          series={[
            {
              name: t.insight.balance,
              color: CHART.ink,
              strong: true,
              values: data.months.map((row) => Number(row.balance)),
              texts: data.months.map((row) => money(row.balance)),
            },
          ]}
        />
      </Part>
      <Part title={t.insight.inAndOut}>
        <BarChart
          title={t.insight.inAndOut}
          labels={labels}
          height={180}
          axisText={axisText}
          partial={data.months.length - 1}
          partialNote={t.analysis.partial}
          series={[
            {
              name: t.insight.inflow,
              color: CHART.positive,
              values: data.months.map((row) => Number(row.inflow)),
              texts: data.months.map((row) => money(row.inflow)),
            },
            {
              name: t.insight.outflow,
              color: CHART.ink,
              values: data.months.map((row) => Number(row.outflow)),
              texts: data.months.map((row) => money(row.outflow)),
            },
          ]}
        />
      </Part>
      <Comparison
        title={t.insight.amongAccounts}
        of={t.insight.ofAccounts}
        share={data.share}
        currency={data.base_currency}
      />
    </div>
  );
}

function CardInsight(props: { id: number }) {
  const t = useMessages();
  const language = useLanguage();
  const { data } = useSuspenseQuery(cardItemQuery(props.id));
  const axisText = useAxisText();
  const labels = useMonthLabels(data.months);
  const money = (amount: string) => formatAmount(amount, data.currency);
  return (
    <div className="grid grid-cols-1 gap-7">
      <Head name={data.name} detail={data.account_name}>
        <Figure label={t.insight.owed} value={money(data.owed)} main />
        <Figure label={t.insight.statements} value={money(data.total)} />
        <Figure label={t.insight.average} value={money(data.average)} />
      </Head>
      <Part title={t.insight.statementByMonth}>
        <BarChart
          title={t.insight.statementByMonth}
          labels={labels}
          height={190}
          axisText={axisText}
          partial={data.months.length - 1}
          partialNote={t.analysis.partial}
          series={[
            {
              name: t.insight.statement,
              color: CHART.ink,
              values: data.months.map((row) => Number(row.amount)),
              texts: data.months.map((row) => money(row.amount)),
            },
          ]}
        />
      </Part>
      {data.categories.length > 0 && (
        <Part title={t.insight.categories}>
          <ul className="grid gap-3">
            {data.categories.map((row) => (
              <li key={row.category_id ?? "none"} className="grid gap-1.5">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate font-medium">{row.name}</span>
                  <span className="amount font-semibold">{money(row.amount)}</span>
                </span>
                <Meter value={row.amount} total={data.total} />
                {row.share !== null && (
                  <span className="amount text-sm text-muted">
                    {formatPercent(row.share, language)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Part>
      )}
      <Comparison
        title={t.insight.amongCards}
        of={t.insight.ofCards}
        share={data.share}
        currency={data.base_currency}
      />
    </div>
  );
}
