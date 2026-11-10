import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { type Analysis, analysisQuery } from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, monthOf, shiftMonth, shortMonthLabel } from "../lib/dates";
import { formatAmount, formatPercent } from "../lib/money";
import {
  monthsBetween,
  oldestStart,
  PRESETS,
  type Preset,
  presetOf,
  presetPeriod,
} from "../lib/period";
import { BarChart, CHART, LineChart, type Run, type Series } from "../ui/charts";
import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from "../ui/icons";
import { RangeSlider } from "../ui/RangeSlider";
import { Segmented } from "../ui/Segmented";
import { OpenWindow, useOpenAbove } from "./host";
import { originId, Positions } from "./origin";

type Flow = Analysis["flows"][number];

/** What the sections share: the data, the origin window and the period change. */
type Tools = {
  data: Analysis;
  /** Open, above this window, what a month is made of. */
  open: (id: `origin:${string}`) => void;
  /** Make a run of months the period of the window. */
  zoom: (start: string, end: string) => void;
};

/** False when the period before starts before the records: no change is shown. */
const Comparable = createContext(true);

const HEADING = "border-b border-line pb-2 font-medium";
const SHOWN_CATEGORIES = 8;
/**
 * The analysis of a period of months: income and expenses, categories, net
 * worth and investments, each against the period before. The period lives in
 * the address ("2026-06_2026-11"), so Back and a link keep it.
 *
 * In each chart, a click on a month opens a window with what its values are
 * made of, and a drag over months gives the figures of those months.
 */
export function AnalysisWindow(props: {
  period: string | undefined;
  onPeriod: (period: string) => void;
}) {
  const t = useMessages();
  const language = useLanguage();
  const [start, end] = props.period?.split("_") ?? [];
  // Not a suspense query: another period keeps this one on screen while it loads.
  const { data, isPlaceholderData, isError, refetch } = useQuery(analysisQuery(start, end));

  // The handles of the slider move at once; the address follows after a short pause.
  const [draft, setDraft] = useState<[string, string] | null>(null);
  const { onPeriod } = props;
  useEffect(() => {
    if (!draft) return;
    const timer = setTimeout(() => onPeriod(draft.join("_")), 120);
    return () => clearTimeout(timer);
  }, [draft, onPeriod]);
  const shownStart = data ? monthOf(data.start) : undefined;
  const shownEnd = data ? monthOf(data.end) : undefined;
  useEffect(() => {
    setDraft((current) =>
      current && current[0] === shownStart && current[1] === shownEnd ? null : current,
    );
  }, [shownStart, shownEnd]);

  const openAbove = useOpenAbove();

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

  const first = monthOf(data.first);
  const last = monthOf(data.last);
  const [from, to] = draft ?? [monthOf(data.start), monthOf(data.end)];
  // The track of the slider does not depend on the period on screen, so it
  // keeps its length while a handle moves: the records, and twelve months at least.
  const oldest = oldestStart(first, last);
  const [trackStart = oldest] = [oldest, shiftMonth(last, -11)].sort();
  const track = monthsBetween(trackStart, last);
  // Where the first handle rests for each preset, named under the track.
  const preset = presetOf(from, to, first, last);
  const marks = PRESETS.map((name) => ({
    position: track.indexOf(presetPeriod(name, first, last)[0]),
    label: t.analysis.presetsShort[name],
    on: name === preset,
  })).filter(
    (mark, index, all) =>
      mark.position >= 0 && all.findIndex((other) => other.position === mark.position) === index,
  );
  const choose = (next: [string, string]) => {
    setDraft(null);
    onPeriod(next.join("_"));
  };
  const count = monthsBetween(from, to).length;
  const short = (month: string) => shortMonthLabel(month, language);
  const tools: Tools = {
    data,
    // The window opens from the chart that has the focus after the click.
    open: (id) => openAbove(id, document.activeElement as HTMLElement | null),
    zoom: (a, b) => choose([a, b]),
  };

  return (
    <div className="grid grid-cols-1 gap-8">
      <section aria-label={t.analysis.period} className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          <Segmented
            inline
            label={t.analysis.period}
            hideLabel
            value={preset}
            onChange={(preset) => preset && choose(presetPeriod(preset as Preset, first, last))}
            options={PRESETS.map((preset) => ({
              value: preset,
              label: t.analysis.presets[preset],
              short: t.analysis.presetsShort[preset],
            }))}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="action px-2"
              aria-label={t.analysis.back}
              title={t.analysis.back}
              disabled={from <= (track[0] ?? from)}
              onClick={() => choose([shiftMonth(from, -1), shiftMonth(to, -1)])}
            >
              <ChevronLeftIcon />
            </button>
            <p className="min-w-44 text-center text-sm" aria-live="polite">
              <span className="font-medium">
                {short(from)} – {short(to)}
              </span>{" "}
              <span className="text-muted">· {t.analysis.months(count)}</span>
            </p>
            <button
              type="button"
              className="action px-2"
              aria-label={t.analysis.forward}
              title={t.analysis.forward}
              disabled={to >= last}
              onClick={() => choose([shiftMonth(from, 1), shiftMonth(to, 1)])}
            >
              <ChevronRightIcon />
            </button>
          </div>
        </div>
        {track.length > 1 && (
          <RangeSlider
            count={track.length}
            start={Math.max(track.indexOf(from), 0)}
            end={Math.max(track.indexOf(to), 0)}
            startLabel={t.analysis.firstMonth}
            endLabel={t.analysis.lastMonth}
            text={(position) => monthLabel(track[position] ?? last, language)}
            marks={marks}
            name={(position) => short(track[position] ?? last)}
            onChange={(a, b) => setDraft([track[a] ?? from, track[b] ?? to])}
          />
        )}
        <p className="text-sm text-muted">
          {data.comparable
            ? t.analysis.compared(
                short(monthOf(data.previous_start)),
                short(shiftMonth(monthOf(data.start), -1)),
              )
            : t.analysis.notComparable}{" "}
          {t.analysis.hint}
        </p>
      </section>

      <Comparable value={data.comparable}>
        {/* A slow answer dims the old figures; a quick one does not flicker. */}
        <div
          className={`grid grid-cols-1 gap-10 transition-opacity duration-200 ${
            isPlaceholderData ? "opacity-55 delay-200" : ""
          }`}
        >
          <Flows {...tools} />
          <Worth {...tools} />
          <Investments {...tools} />
        </div>
      </Comparable>
    </div>
  );
}

/**
 * The run of months that the owner selected in one chart, and the analysis
 * of that run from the server. `stock` is for values at month ends: the
 * change from the first month end to the last one is the analysis of the
 * months after the first.
 */
function useRun(data: Analysis, stock = false) {
  const t = useMessages();
  const language = useLanguage();
  const [run, setRun] = useState<Run | null>(null);
  // Another period has other months: the selection ends.
  const period = `${data.start}_${data.end}`;
  const [seen, setSeen] = useState(period);
  if (seen !== period) {
    setSeen(period);
    setRun(null);
  }
  const months = data.months.map(monthOf);
  const first = run ? months[run[0]] : undefined;
  const last = run ? months[run[1]] : undefined;
  const from = stock && first ? shiftMonth(first, 1) : first;
  const part = useQuery({
    ...analysisQuery(from, last),
    enabled: Boolean(from && last),
    placeholderData: undefined,
  });
  const count = run ? run[1] - run[0] + 1 : 0;
  const title =
    first && last
      ? `${shortMonthLabel(first, language)} – ${shortMonthLabel(last, language)} · ${t.analysis.months(count)}`
      : "";
  return {
    run,
    setRun,
    first,
    last,
    title,
    loading: t.common.loading,
    part: run ? part.data : undefined,
  };
}

/** One figure of a selected run. Without a text yet, its figure is still loading. */
type RunRow = { name: string; text: string | undefined; color?: string; tone?: string };

/**
 * What a chart needs for a selected run: the run itself, its figures under
 * the marks, and the same figures for the label under the pointer.
 */
function runProps(selection: ReturnType<typeof useRun>, tools: Tools, rows: RunRow[]) {
  return {
    selected: selection.run,
    onSelect: selection.setRun,
    selection: selection.run
      ? {
          title: selection.title,
          rows: rows.map((row) => ({ ...row, text: row.text ?? selection.loading })),
        }
      : undefined,
    summary: (
      <RunSummary
        tools={tools}
        first={selection.first}
        last={selection.last}
        onClear={() => selection.setRun(null)}
      >
        {rows.map((row) => (
          <RunValue key={row.name} label={row.name} value={row.text} tone={row.tone} />
        ))}
      </RunSummary>
    ),
  };
}

/** The line above a chart for a selected run: its months, its figures and what to do with it. */
function RunSummary(props: {
  tools: Tools;
  first: string | undefined;
  last: string | undefined;
  onClear: () => void;
  children: ReactNode;
}) {
  const t = useMessages();
  const language = useLanguage();
  const { first, last } = props;
  if (!first || !last) return null;
  return (
    <>
      <span className="font-medium text-ink">
        {shortMonthLabel(first, language)} – {shortMonthLabel(last, language)}
      </span>
      {props.children}
      <span className="flex items-center gap-1.5">
        <button type="button" className="action" onClick={() => props.tools.zoom(first, last)}>
          {t.analysis.usePeriod}
        </button>
        <button
          type="button"
          className="action px-2"
          aria-label={t.analysis.clearSelection}
          title={t.analysis.clearSelection}
          onClick={props.onClear}
        >
          <CloseIcon />
        </button>
      </span>
    </>
  );
}

/** One figure of a selected run. Without a value yet, it says that it loads. */
function RunValue(props: { label: string; value: string | undefined; tone?: string }) {
  const t = useMessages();
  return (
    <span>
      {props.label}{" "}
      <span className={`amount font-medium ${props.tone ?? "text-ink"}`}>
        {props.value ?? t.common.loading}
      </span>
    </span>
  );
}

/** Income, expenses and categories. Amounts of two currencies are not added: the owner chooses one. */
function Flows(tools: Tools) {
  const t = useMessages();
  const language = useLanguage();
  const { data } = tools;
  const [currency, setCurrency] = useState("");
  const selection = useRun(data);
  const flow = data.flows.find((row) => row.currency === currency) ?? data.flows[0];
  if (!flow) {
    return (
      <section>
        <h3 className={HEADING}>{t.analysis.flows}</h3>
        <p className="mt-4 text-muted">{t.analysis.noFlows}</p>
      </section>
    );
  }
  const money = (amount: string) => formatAmount(amount, flow.currency);
  const months = data.months.map(monthOf);
  const labels = months.map((month) => shortMonthLabel(month, language));
  const partial = data.end === data.last ? data.months.length - 1 : undefined;
  const series: Series[] = [
    {
      name: t.home.income,
      color: CHART.positive,
      values: flow.months.map((row) => Number(row.income)),
      texts: flow.months.map((row) => money(row.income)),
    },
    {
      name: t.home.expenses,
      color: CHART.ink,
      values: flow.months.map((row) => Number(row.expenses)),
      texts: flow.months.map((row) => money(row.expenses)),
    },
  ];
  // A run without entries in this currency has no row: its figures are zero.
  const loaded = selection.part !== undefined;
  const part = selection.part?.flows.find((row) => row.currency === flow.currency);
  const figure = (amount: string | undefined) => (loaded ? money(amount ?? "0") : undefined);

  return (
    <>
      <section className="grid gap-4">
        <div className={`flex flex-wrap items-end justify-between gap-3 ${HEADING}`}>
          <h3>{t.analysis.flows}</h3>
          {data.flows.length > 1 && (
            <Segmented
              inline
              hideLabel
              label={t.settings.currency}
              value={flow.currency}
              onChange={setCurrency}
              options={data.flows.map((row) => ({ value: row.currency, label: row.currency }))}
            />
          )}
        </div>
        <dl className="flex flex-wrap gap-x-10 gap-y-4">
          <Stat label={t.home.income} value={money(flow.income)} tone="text-positive">
            <Change
              amount={flow.income_change}
              percent={flow.income_change_percent}
              currency={flow.currency}
              good="up"
            />
          </Stat>
          <Stat label={t.home.expenses} value={money(flow.expenses)}>
            <Change
              amount={flow.expenses_change}
              percent={flow.expenses_change_percent}
              currency={flow.currency}
              good="down"
            />
          </Stat>
          <Stat
            label={t.analysis.result}
            value={money(flow.result)}
            tone={Number(flow.result) < 0 ? "text-negative" : ""}
          >
            <Change amount={flow.result_change} currency={flow.currency} good="up" />
          </Stat>
          <Stat label={t.analysis.averageExpenses} value={money(flow.average_expenses)} quiet />
        </dl>
        <BarChart
          title={t.analysis.flows}
          labels={labels}
          series={series}
          partial={partial}
          partialNote={t.analysis.partial}
          axisText={axisText(language)}
          onPick={(index) => tools.open(originId("flows", months[index] ?? "", flow.currency))}
          {...runProps(selection, tools, [
            {
              name: t.home.income,
              text: figure(part?.income),
              color: CHART.positive,
              tone: "text-positive",
            },
            { name: t.home.expenses, text: figure(part?.expenses), color: CHART.ink },
            { name: t.analysis.result, text: figure(part?.result) },
          ])}
        />
      </section>
      <Categories tools={tools} flow={flow} labels={labels} partial={partial} />
    </>
  );
}

/** The categories of the period, largest first, and one of them month by month. */
function Categories(props: {
  tools: Tools;
  flow: Flow;
  labels: string[];
  partial: number | undefined;
}) {
  const t = useMessages();
  const language = useLanguage();
  const { flow, tools } = props;
  const [chosen, setChosen] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const selection = useRun(tools.data);
  const money = (amount: string) => formatAmount(amount, flow.currency);
  const category = flow.categories.find((row) => row.category_id === chosen) ?? flow.categories[0];
  if (!category) return null;
  const rows = all ? flow.categories : flow.categories.slice(0, SHOWN_CATEGORIES);
  const months = tools.data.months.map(monthOf);
  const part = selection.part?.flows
    .find((row) => row.currency === flow.currency)
    ?.categories.find((row) => row.category_id === category.category_id);

  return (
    <section className="grid gap-4">
      <h3 className={HEADING}>{t.analysis.categories}</h3>
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-2">
        <div>
          <ul className="grid gap-1">
            {rows.map((row) => (
              <li key={row.category_id ?? "none"}>
                <button
                  type="button"
                  aria-pressed={row === category}
                  onClick={() => setChosen(row.category_id)}
                  className={`grid w-full gap-1.5 rounded-(--radius-control) px-2.5 py-2 text-left transition-colors duration-150 hover:bg-ink/5 ${
                    row === category ? "bg-ink/5" : ""
                  }`}
                >
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="truncate font-medium">{row.name}</span>
                    <span className="amount font-semibold">{money(row.amount)}</span>
                  </span>
                  <span className="block h-1.5 rounded-full bg-line">
                    <span
                      className="chart-mark block h-full rounded-full bg-ink"
                      style={{ width: `${Math.min(Number(row.share ?? 0), 100)}%` }}
                    />
                  </span>
                  <span className="flex items-baseline justify-between gap-3 text-sm text-muted">
                    <span>{row.share === null ? "" : formatPercent(row.share, language)}</span>
                    <Change amount={row.change} currency={flow.currency} good="down" />
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {flow.categories.length > SHOWN_CATEGORIES && (
            <button type="button" className="action mt-3" onClick={() => setAll(!all)}>
              {all ? t.analysis.fewer : t.analysis.allCategories(flow.categories.length)}
            </button>
          )}
        </div>
        <div className="grid content-start gap-3">
          <p>
            <span className="font-medium">{category.name}</span>{" "}
            <span className="text-sm text-muted">
              · {t.analysis.averagePerMonth(money(category.average))}
            </span>
          </p>
          <BarChart
            title={t.analysis.categoryByMonth(category.name)}
            labels={props.labels}
            partial={props.partial}
            partialNote={t.analysis.partial}
            height={200}
            axisText={axisText(language)}
            series={[
              {
                name: category.name,
                color: CHART.ink,
                values: category.months.map(Number),
                texts: category.months.map(money),
              },
            ]}
            onPick={(index) =>
              tools.open(
                originId("category", months[index] ?? "", flow.currency, category.category_id),
              )
            }
            {...runProps(selection, tools, [
              {
                name: category.name,
                text: selection.part ? money(part?.amount ?? "0") : undefined,
                color: CHART.ink,
              },
            ])}
          />
        </div>
      </div>
    </section>
  );
}

/** The net worth at each month end and what it is made of. */
function Worth(tools: Tools) {
  const t = useMessages();
  const language = useLanguage();
  const { worth } = tools.data;
  const selection = useRun(tools.data, true);
  const money = (amount: string) => formatAmount(amount, worth.currency);
  const last = worth.months.at(-1);
  if (!last) return null;
  const months = tools.data.months.map(monthOf);
  const line = (
    name: string,
    color: string,
    read: (row: (typeof worth.months)[number]) => string,
    extra: Partial<Series> = {},
  ): Series => ({
    name,
    color,
    values: worth.months.map((row) => Number(read(row))),
    texts: worth.months.map((row) => money(read(row))),
    ...extra,
  });
  const series = [
    line(t.home.blocks.worth, CHART.ink, (row) => row.net_worth, { strong: true }),
    line(t.home.worth.accounts, CHART.positive, (row) => row.accounts),
    line(t.home.worth.investments, CHART.accent, (row) => row.investments),
    line(t.home.worth.debt, CHART.negative, (row) => row.card_debt, { dashed: true }),
  ];
  const part = selection.part?.worth;
  return (
    <section className="grid gap-4">
      <h3 className={HEADING}>{t.home.blocks.worth}</h3>
      <dl className="flex flex-wrap gap-x-10 gap-y-4">
        <Stat
          label={t.analysis.worthAtEnd}
          value={money(last.net_worth)}
          tone={Number(last.net_worth) < 0 ? "text-negative" : ""}
        >
          <Change
            amount={worth.change}
            percent={worth.change_percent}
            currency={worth.currency}
            good="up"
          />
        </Stat>
        <Stat label={t.home.worth.accounts} value={money(last.accounts)} quiet />
        <Stat label={t.home.worth.investments} value={money(last.investments)} quiet />
        <Stat label={t.home.worth.debt} value={money(last.card_debt)} quiet />
      </dl>
      {!worth.complete && (
        <p className="text-sm text-muted">
          {t.home.worth.incomplete(worth.missing_currencies.join(", "))}{" "}
          <OpenWindow w="rates" className="action">
            {t.rates.add}
          </OpenWindow>
        </p>
      )}
      <LineChart
        title={t.home.blocks.worth}
        labels={months.map((month) => shortMonthLabel(month, language))}
        series={series}
        axisText={axisText(language)}
        onPick={(index) => tools.open(originId("worth", months[index] ?? ""))}
        {...runProps(selection, tools, [
          {
            name: t.analysis.changeOf(t.home.blocks.worth),
            text: part ? signed(part.change, worth.currency) : undefined,
          },
        ])}
      />
    </section>
  );
}

/** What the investments are worth against what they cost, and the positions at the end. */
function Investments(tools: Tools) {
  const t = useMessages();
  const language = useLanguage();
  const { worth, positions } = tools.data;
  const selection = useRun(tools.data, true);
  const money = (amount: string) => formatAmount(amount, worth.currency);
  const last = worth.months.at(-1);
  const held = worth.months.some((row) => Number(row.investments) !== 0);
  if (!last || (!held && positions.length === 0)) {
    return (
      <section>
        <h3 className={HEADING}>{t.home.worth.investments}</h3>
        <p className="mt-4 text-muted">{t.analysis.noInvestments}</p>
      </section>
    );
  }
  const months = tools.data.months.map(monthOf);
  const series: Series[] = [
    {
      name: t.analysis.value,
      color: CHART.ink,
      strong: true,
      values: worth.months.map((row) => Number(row.investments)),
      texts: worth.months.map((row) => money(row.investments)),
    },
    {
      name: t.analysis.cost,
      color: CHART.accent,
      dashed: true,
      values: worth.months.map((row) => Number(row.investments_cost)),
      texts: worth.months.map((row) => money(row.investments_cost)),
    },
  ];
  const part = selection.part?.worth;
  return (
    <section className="grid gap-4">
      <h3 className={HEADING}>{t.home.worth.investments}</h3>
      <dl className="flex flex-wrap gap-x-10 gap-y-4">
        <Stat label={t.analysis.valueAtEnd} value={money(last.investments)}>
          <Change amount={worth.investments_change} currency={worth.currency} good="up" />
        </Stat>
        <Stat label={t.analysis.cost} value={money(last.investments_cost)} quiet />
        <Stat
          label={t.analysis.gain}
          value={money(last.investments_gain)}
          tone={Number(last.investments_gain) < 0 ? "text-negative" : ""}
          quiet
        />
      </dl>
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-2">
        <LineChart
          title={t.home.worth.investments}
          labels={months.map((month) => shortMonthLabel(month, language))}
          series={series}
          height={200}
          axisText={axisText(language)}
          onPick={(index) => tools.open(originId("investments", months[index] ?? ""))}
          {...runProps(selection, tools, [
            {
              name: t.analysis.changeOf(t.analysis.value),
              text: part ? signed(part.investments_change, worth.currency) : undefined,
            },
          ])}
        />
        {positions.length > 0 && (
          <div className="grid content-start gap-3">
            <p className="text-sm text-muted">{t.analysis.positionsAtEnd}</p>
            <Positions rows={positions} currency={worth.currency} />
          </div>
        )}
      </div>
    </section>
  );
}

/** One figure of a section: its name, its value and, below, its change. */
function Stat(props: {
  label: string;
  value: string;
  tone?: string;
  /** A supporting figure: smaller than the main ones. */
  quiet?: boolean;
  children?: ReactNode;
}) {
  return (
    <div>
      <dt className="text-sm text-muted">{props.label}</dt>
      <dd
        className={`amount font-semibold ${props.quiet ? "text-lg" : "text-2xl"} ${props.tone ?? ""}`}
      >
        {props.value}
      </dd>
      {props.children && <dd className="text-sm">{props.children}</dd>}
    </div>
  );
}

/**
 * A change against the period before, with its sign. The server calculates
 * it. The color says whether the direction is good; the sign says the same
 * without color.
 */
function Change(props: {
  amount: string;
  percent?: string | null;
  currency: string;
  good: "up" | "down";
}) {
  const language = useLanguage();
  const t = useMessages();
  if (!useContext(Comparable)) return null;
  const value = Number(props.amount);
  if (value === 0) return <span className="text-muted">{t.analysis.noChange}</span>;
  const tone = value > 0 === (props.good === "up") ? "text-positive" : "text-negative";
  return (
    <span className={`amount ${tone}`}>
      {signed(props.amount, props.currency)}
      {props.percent != null &&
        ` · ${Number(props.percent) > 0 ? "+" : ""}${formatPercent(props.percent, language)}`}
    </span>
  );
}

/** An amount with its sign written: "+R$ 100,00". */
function signed(amount: string, currency: string): string {
  return `${Number(amount) > 0 ? "+" : ""}${formatAmount(amount, currency)}`;
}

/** A short text for a value of an axis: "2 mil", "1,5 mi". */
function axisText(language: string): (value: number) => string {
  const format = new Intl.NumberFormat(language, { notation: "compact", maximumFractionDigits: 1 });
  return (value) => format.format(value);
}
