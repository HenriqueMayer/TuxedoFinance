import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, todayIso } from "../lib/dates";
import { ChevronLeftIcon, ChevronRightIcon } from "./icons";

export const STEP =
  "grid w-9 place-items-center text-muted transition-colors duration-150 hover:bg-ink/5 hover:text-ink focus-visible:-outline-offset-2 disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-muted";

/**
 * The twelve months of a year, with a step to the year before and after.
 * The chosen month is dark and the current month has the bow-tie color. The
 * arrow keys move over the months as over a table of four columns.
 */
export function Months(props: {
  /** The chosen month ("YYYY-MM"), or null. */
  month: string | null;
  onChoose: (month: string) => void;
  /** The first and the last month that can be chosen. */
  min?: string;
  max?: string;
}) {
  const t = useMessages();
  const language = useLanguage();
  const thisMonth = todayIso().slice(0, 7);
  const [year, setYear] = useState(Number((props.month ?? thisMonth).slice(0, 4)));
  const grid = useRef<HTMLDivElement>(null);

  // The month that takes the focus when the months open: the chosen one, the
  // current one, or the first of the year.
  const inYear = (month: string) => month.startsWith(`${year}-`);
  const start =
    props.month && inYear(props.month) ? props.month : inYear(thisMonth) ? thisMonth : `${year}-01`;
  useEffect(() => {
    grid.current?.querySelector<HTMLElement>("[data-start]")?.focus();
  }, []);

  function onKey(event: KeyboardEvent) {
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -4, ArrowDown: 4 }[event.key];
    if (!offset) return;
    const cells = Array.from(grid.current?.querySelectorAll<HTMLElement>("button") ?? []);
    const next = cells[cells.indexOf(document.activeElement as HTMLElement) + offset];
    if (!next) return;
    event.preventDefault();
    next.focus();
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <button
          type="button"
          className={`${STEP} h-8 rounded-(--radius-control)`}
          aria-label={t.transactions.previousYear}
          onClick={() => setYear(year - 1)}
        >
          <ChevronLeftIcon />
        </button>
        <p className="amount text-sm font-semibold" aria-live="polite">
          {year}
        </p>
        <button
          type="button"
          className={`${STEP} h-8 rounded-(--radius-control)`}
          aria-label={t.transactions.nextYear}
          onClick={() => setYear(year + 1)}
        >
          <ChevronRightIcon />
        </button>
      </div>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: the arrow keys move between the month buttons. */}
      <div ref={grid} className="mt-2 grid grid-cols-4 gap-1" onKeyDown={onKey}>
        {Array.from({ length: 12 }, (_, index) => {
          const month = `${year}-${String(index + 1).padStart(2, "0")}`;
          const chosen = month === props.month;
          return (
            <button
              key={month}
              type="button"
              data-start={month === start || undefined}
              aria-label={monthLabel(month, language)}
              aria-pressed={chosen}
              disabled={
                (props.min !== undefined && month < props.min) ||
                (props.max !== undefined && month > props.max)
              }
              className={`rounded-(--radius-control) py-2 text-sm transition-colors duration-150 disabled:opacity-35 ${
                chosen
                  ? "bg-ink font-medium text-sheet"
                  : `hover:bg-ink/7 ${month === thisMonth ? "font-semibold text-accent-ink" : ""}`
              }`}
              onClick={() => props.onChoose(month)}
            >
              {shortMonth(index, language)}
            </button>
          );
        })}
      </div>
    </>
  );
}

/** "Jan", "Fev": the short name of a month, without the period of some languages. */
function shortMonth(index: number, language: string): string {
  const name = new Intl.DateTimeFormat(language, { month: "short" })
    .format(new Date(2026, index, 1))
    .replace(/\.$/, "");
  return name.charAt(0).toUpperCase() + name.slice(1);
}
