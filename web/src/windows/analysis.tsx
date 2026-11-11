import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import { type Analysis, analysisQuery } from "../data/reports";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, monthOf, shiftMonth, shortMonthLabel } from "../lib/dates";
import { formatAmount, formatPercent } from "../lib/money";
import {
  monthsBetween,
  oldestStart,
  PRESETS,
  type Preset,
  presetMarks,
  presetOf,
  presetPeriod,
} from "../lib/period";
import { BarChart, CHART, LineChart, type Run, type Series, Swatch } from "../ui/charts";
import {
  CardIcon,
  ChartIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  TagIcon,
  TrendIcon,
  WorthIcon,
} from "../ui/icons";
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

/** The areas of the analysis. */
type AreaId = "flows" | "categories" | "cards" | "worth" | "investments";
const SHOWN_CATEGORIES = 8;
/**
 * The analysis of a period of months: income and expenses, categories, cards,
 * net worth and investments, each against the period before. The period lives in
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

  // The preset that the owner pressed: it names a period that two presets give.
  const [pressed, setPressed] = useState<Preset | "">("");

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
  const preset = presetOf(from, to, first, last, pressed);
  const marks = presetMarks(track, first, last, preset).map((mark) => ({
    position: mark.position,
    label: t.analysis.presetsShort[mark.preset],
    on: mark.on,
  }));
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
    <div className="grid grid-cols-1 gap-5">
      <section aria-label={t.analysis.period} className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          <Segmented
            inline
            label={t.analysis.period}
            hideLabel
            value={preset}
            onChange={(preset) => {
              if (!preset) return;
              setPressed(preset);
              choose(presetPeriod(preset, first, last));
            }}
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

      <AreaBar
        areas={[
          { id: "flows", title: t.analysis.flows, icon: <ChartIcon /> },
          { id: "categories", title: t.analysis.categories, icon: <TagIcon /> },
          { id: "cards", title: t.analysis.cards, icon: <CardIcon /> },
          { id: "worth", title: t.home.blocks.worth, icon: <WorthIcon /> },
          { id: "investments", title: t.home.worth.investments, icon: <TrendIcon /> },
        ]}
        period={`${short(from)} – ${short(to)}`}
      />

      <Comparable value={data.comparable}>
        {/* A slow answer dims the old figures; a quick one does not flicker. */}
        <div
          className={`grid grid-cols-1 gap-6 transition-opacity duration-200 ${
            isPlaceholderData ? "opacity-55 delay-200" : ""
          }`}
        >
          <Flows {...tools} />
          <Cards {...tools} />
          <Worth {...tools} />
          <Investments {...tools} />
        </div>
      </Comparable>
    </div>
  );
}

/**
 * One area of the analysis: a block with its name and its mark in a band at
 * the top, so that the owner sees where one area ends and the next begins.
 */
function Area(props: {
  id: AreaId;
  title: string;
  icon: ReactNode;
  /** A control of the whole area, at the end of its band. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={`area-${props.id}`} data-area={props.id} aria-label={props.title} className="area">
      <header className="area-head">
        <span aria-hidden="true" className="area-mark">
          {props.icon}
        </span>
        <h3 className="font-semibold">{props.title}</h3>
        {props.aside && <span className="ml-auto">{props.aside}</span>}
      </header>
      <div className="grid gap-4 p-4 sm:p-5">{props.children}</div>
    </section>
  );
}

/**
 * The areas of the analysis in one bar that stays at the top of the window.
 * A press goes to an area; the bar marks the area that is at the top.
 */
function AreaBar(props: {
  areas: { id: AreaId; title: string; icon: ReactNode }[];
  /** The period on screen, as a reminder while the controls are out of view. */
  period: string;
}) {
  const t = useMessages();
  const bar = useRef<HTMLElement>(null);
  const [current, setCurrent] = useState<AreaId>("flows");
  // The area that a press asked for, until the owner scrolls: an area near
  // the end of the window cannot reach the top, and it is still the current one.
  const pressed = useRef<AreaId | null>(null);
  // True while the scroll of a press runs.
  const moving = useRef(false);
  const settle = useRef(0);

  // The current area is the last one that starts above the line under the bar.
  useEffect(() => {
    const nav = bar.current;
    const root = nav?.closest<HTMLElement>(".overflow-y-auto");
    if (!nav || !root) return;
    let frame = 0;
    const read = () => {
      if (pressed.current) return setCurrent(pressed.current);
      const areas = [...root.querySelectorAll<HTMLElement>("[data-area]")];
      const line = nav.getBoundingClientRect().bottom + 16;
      const atEnd =
        root.scrollTop > 0 && root.scrollTop + root.clientHeight >= root.scrollHeight - 2;
      const above = areas.filter((area) => area.getBoundingClientRect().top <= line);
      const area = atEnd ? areas.at(-1) : (above.at(-1) ?? areas[0]);
      if (area) setCurrent(area.dataset.area as AreaId);
    };
    const onScroll = () => {
      // A scroll that no press started is of the owner: the position decides again.
      if (!moving.current) pressed.current = null;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    const onEnd = () => {
      moving.current = false;
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    root.addEventListener("scrollend", onEnd);
    // The areas change their height with the data and with the width.
    const sizes = new ResizeObserver(onScroll);
    for (const area of root.querySelectorAll("[data-area]")) sizes.observe(area);
    read();
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settle.current);
      sizes.disconnect();
      root.removeEventListener("scroll", onScroll);
      root.removeEventListener("scrollend", onEnd);
    };
  }, []);

  // On a narrow window the bar scrolls sideways: the current name stays in view.
  useEffect(() => {
    const nav = bar.current;
    const tab = nav?.querySelector<HTMLElement>(`[data-tab="${current}"]`);
    if (!nav || !tab) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    nav.scrollTo({
      left: tab.offsetLeft - (nav.clientWidth - tab.offsetWidth) / 2,
      behavior: still ? "auto" : "smooth",
    });
  }, [current]);

  /**
   * Bring an area under the bar. Only the content of the window scrolls:
   * `scrollIntoView` also scrolls the window itself when the area cannot
   * reach the top, and that hides the title and this bar.
   */
  function go(id: AreaId) {
    const nav = bar.current;
    const root = nav?.closest<HTMLElement>(".overflow-y-auto");
    const area = root?.querySelector<HTMLElement>(`[data-area="${id}"]`);
    if (!nav || !root || !area) return;
    pressed.current = id;
    setCurrent(id);
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const top =
      root.scrollTop +
      area.getBoundingClientRect().top -
      root.getBoundingClientRect().top -
      nav.offsetHeight -
      10;
    const limit = root.scrollHeight - root.clientHeight;
    const target = Math.round(Math.min(Math.max(top, 0), limit));
    // The scroll of a press ends with `scrollend`. A browser without that
    // event gets a pause, and a press that needs no scroll has no end.
    clearTimeout(settle.current);
    moving.current = Math.abs(target - root.scrollTop) > 1;
    if (moving.current && !("onscrollend" in (root as object))) {
      settle.current = window.setTimeout(() => {
        moving.current = false;
      }, 1200);
    }
    root.scrollTo({ top: target, behavior: still ? "auto" : "smooth" });
  }

  return (
    <nav ref={bar} aria-label={t.analysis.areas} className="area-bar">
      {props.areas.map((area) => (
        <button
          key={area.id}
          type="button"
          className="area-tab"
          data-tab={area.id}
          aria-current={area.id === current ? "true" : undefined}
          onClick={() => go(area.id)}
        >
          {area.icon}
          {area.title}
        </button>
      ))}
      <span className="ml-auto pl-3 text-sm whitespace-nowrap text-muted max-sm:hidden">
        {props.period}
      </span>
    </nav>
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
      <Area id="flows" title={t.analysis.flows} icon={<ChartIcon />}>
        <p className="text-muted">{t.analysis.noFlows}</p>
      </Area>
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
      <Area
        id="flows"
        title={t.analysis.flows}
        icon={<ChartIcon />}
        aside={
          data.flows.length > 1 && (
            <Segmented
              inline
              hideLabel
              label={t.settings.currency}
              value={flow.currency}
              onChange={setCurrency}
              options={data.flows.map((row) => ({ value: row.currency, label: row.currency }))}
            />
          )
        }
      >
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
      </Area>
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
    <Area id="categories" title={t.analysis.categories} icon={<TagIcon />}>
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
    </Area>
  );
}

/** The cards that take a color of their own in a chart. With more cards, the chart has their total. */
const CARD_COLORS = [CHART.ink, CHART.accent, CHART.quiet];

/**
 * The credit cards: the statements of the period, what the cards owe today
 * and the statements after the current month. The owner reads every card
 * together, one series for each, or presses one card to read it alone.
 */
function Cards(tools: Tools) {
  const t = useMessages();
  const language = useLanguage();
  const { data } = tools;
  const [currency, setCurrency] = useState("");
  const [chosen, setChosen] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const selection = useRun(data);
  const row = data.cards.find((item) => item.currency === currency) ?? data.cards[0];
  if (!row) {
    return (
      <Area id="cards" title={t.analysis.cards} icon={<CardIcon />}>
        <p className="text-muted">{t.analysis.noCards}</p>
      </Area>
    );
  }
  const money = (amount: string) => formatAmount(amount, row.currency);
  // One card alone needs no choice. A chosen card that left the period gives its place to all.
  const card = row.cards.length === 1 ? row.cards[0] : row.cards.find((item) => item.id === chosen);
  const scope = card ?? row;
  const name = card?.name ?? t.analysis.allCards;
  const months = data.months.map(monthOf);
  const partial = data.end === data.last ? data.months.length - 1 : undefined;
  // Every card together: one series for each card while each one can take a color.
  const compared = !card && row.cards.length <= CARD_COLORS.length;
  const series = (read: (source: typeof scope) => string[]): Series[] =>
    compared
      ? row.cards.map((item, index) => ({
          name: item.name,
          color: CARD_COLORS[index] ?? CHART.ink,
          values: read(item).map(Number),
          texts: read(item).map(money),
        }))
      : [
          {
            name,
            color: CHART.ink,
            values: read(scope).map(Number),
            texts: read(scope).map(money),
          },
        ];
  // The figures of a selected run. A run without a statement has no row: its figures are zero.
  const loaded = selection.part !== undefined;
  const part = selection.part?.cards.find((item) => item.currency === row.currency);
  const figure = (id: number | null) => {
    if (!loaded) return undefined;
    const found = id === null ? part : part?.cards.find((item) => item.id === id);
    return money(found?.total ?? "0");
  };
  const runRows: RunRow[] = compared
    ? [
        ...row.cards.map((item, index) => ({
          name: item.name,
          text: figure(item.id),
          color: CARD_COLORS[index],
        })),
        { name: t.analysis.allCards, text: figure(null) },
      ]
    : [{ name, text: figure(card?.id ?? null), color: CHART.ink }];
  const categories = all ? scope.categories : scope.categories.slice(0, SHOWN_CATEGORIES);
  const choice =
    "grid w-full gap-1.5 rounded-(--radius-control) px-2.5 py-2 text-left transition-colors duration-150 hover:bg-ink/5";

  return (
    <Area
      id="cards"
      title={t.analysis.cards}
      icon={<CardIcon />}
      aside={
        data.cards.length > 1 && (
          <Segmented
            inline
            hideLabel
            label={t.settings.currency}
            value={row.currency}
            onChange={setCurrency}
            options={data.cards.map((item) => ({ value: item.currency, label: item.currency }))}
          />
        )
      }
    >
      <div className="grid gap-2">
        <p className="font-medium">{name}</p>
        <dl className="flex flex-wrap gap-x-10 gap-y-4">
          <Stat label={t.analysis.cardsTotal} value={money(scope.total)}>
            <Change
              amount={scope.change}
              percent={scope.change_percent}
              currency={row.currency}
              good="down"
            />
          </Stat>
          <Stat label={t.analysis.cardsAverage} value={money(scope.average)} quiet />
          <Stat label={t.analysis.cardsOwed} value={money(scope.owed)} quiet />
          <Stat label={t.analysis.cardsUpcoming} value={money(scope.upcoming_total)} quiet />
        </dl>
      </div>
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-2">
        <ul className="grid content-start gap-1">
          {row.cards.length > 1 && (
            <li>
              <button
                type="button"
                aria-pressed={!card}
                onClick={() => setChosen(null)}
                className={`${choice} ${card ? "" : "bg-ink/5"}`}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate font-medium">{t.analysis.allCards}</span>
                  <span className="amount font-semibold">{money(row.total)}</span>
                </span>
                <span className="text-sm text-muted">{t.analysis.cardOwes(money(row.owed))}</span>
              </button>
            </li>
          )}
          {row.cards.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={item === card}
                onClick={() => setChosen(item.id)}
                className={`${choice} ${item === card ? "bg-ink/5" : ""}`}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2 font-medium">
                    {row.cards.length <= CARD_COLORS.length && (
                      <Swatch color={CARD_COLORS[index] ?? CHART.ink} />
                    )}
                    <span className="truncate">{item.name}</span>
                  </span>
                  <span className="amount font-semibold">{money(item.total)}</span>
                </span>
                <span className="block h-1.5 rounded-full bg-line">
                  <span
                    className="chart-mark block h-full rounded-full bg-ink"
                    style={{ width: `${Math.min(Number(item.share ?? 0), 100)}%` }}
                  />
                </span>
                <span className="flex items-baseline justify-between gap-3 text-sm text-muted">
                  <span>
                    {item.share === null ? "" : `${formatPercent(item.share, language)} · `}
                    {t.analysis.cardOwes(money(item.owed))}
                  </span>
                  <Change amount={item.change} currency={row.currency} good="down" />
                </span>
              </button>
            </li>
          ))}
        </ul>
        <BarChart
          title={t.analysis.statementsByMonth(name)}
          labels={months.map((month) => shortMonthLabel(month, language))}
          series={series((source) => source.months)}
          partial={partial}
          partialNote={t.analysis.partial}
          height={220}
          axisText={axisText(language)}
          onPick={(index) =>
            tools.open(originId("cards", months[index] ?? "", row.currency, card?.id ?? null))
          }
          {...runProps(selection, tools, runRows)}
        />
      </div>
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 border-t border-line pt-4 lg:grid-cols-2">
        <div className="grid content-start gap-3">
          <p className="font-medium">{t.analysis.cardCategories(name)}</p>
          {scope.categories.length === 0 && <p className="text-muted">{t.analysis.noEntries}</p>}
          <ul className="grid gap-3">
            {categories.map((part) => (
              <li key={part.category_id ?? "none"} className="grid gap-1.5">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate">{part.name}</span>
                  <span className="amount font-semibold">{money(part.amount)}</span>
                </span>
                <span className="block h-1.5 rounded-full bg-line">
                  <span
                    className="chart-mark block h-full rounded-full bg-ink"
                    style={{ width: `${Math.min(Number(part.share ?? 0), 100)}%` }}
                  />
                </span>
                {part.share !== null && (
                  <span className="text-sm text-muted">{formatPercent(part.share, language)}</span>
                )}
              </li>
            ))}
          </ul>
          {scope.categories.length > SHOWN_CATEGORIES && (
            <button type="button" className="action w-fit" onClick={() => setAll(!all)}>
              {all ? t.analysis.fewer : t.analysis.allCategories(scope.categories.length)}
            </button>
          )}
        </div>
        <div className="grid content-start gap-3">
          <div>
            <p className="font-medium">{t.analysis.cardsUpcoming}</p>
            <p className="text-sm text-muted">
              {t.analysis.cardsUpcomingHelp(shortMonthLabel(monthOf(data.last), language))}
            </p>
          </div>
          {row.upcoming_months.length === 0 ? (
            <p className="text-muted">{t.analysis.noUpcoming}</p>
          ) : (
            <BarChart
              title={t.analysis.laterStatementsOf(name)}
              labels={row.upcoming_months.map((month) => shortMonthLabel(monthOf(month), language))}
              series={series((source) => source.upcoming)}
              height={200}
              axisText={axisText(language)}
            />
          )}
        </div>
      </div>
    </Area>
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
    <Area id="worth" title={t.home.blocks.worth} icon={<WorthIcon />}>
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
    </Area>
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
      <Area id="investments" title={t.home.worth.investments} icon={<TrendIcon />}>
        <p className="text-muted">{t.analysis.noInvestments}</p>
      </Area>
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
    <Area id="investments" title={t.home.worth.investments} icon={<TrendIcon />}>
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
    </Area>
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
