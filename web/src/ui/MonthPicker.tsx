import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, shiftMonth, todayIso } from "../lib/dates";
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from "./icons";

const STEP =
  "grid w-9 place-items-center text-muted transition-colors duration-150 hover:bg-ink/5 hover:text-ink focus-visible:-outline-offset-2 disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-muted";

/**
 * The month that a page shows. One control: a step to each side, and a label
 * that opens the months of a year to go to any of them. With `all`, the
 * months also offer every month at once; the value is then "all".
 */
export function MonthPicker(props: {
  /** "YYYY-MM", or "all". */
  month: string;
  onChange: (month: string) => void;
  /** Offer "All months". */
  all?: boolean;
  /** The side of the control where the months open. */
  align?: "end" | "center";
}) {
  const t = useMessages();
  const language = useLanguage();
  const thisMonth = todayIso().slice(0, 7);
  const every = props.month === "all";
  const shown = every ? thisMonth : props.month;

  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(Number(shown.slice(0, 4)));
  const root = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLButtonElement>(null);
  const grid = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    grid.current?.querySelector<HTMLElement>("[data-start]")?.focus();
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function toggle() {
    setYear(Number(shown.slice(0, 4)));
    setOpen((value) => !value);
  }

  function choose(month: string) {
    props.onChange(month);
    setOpen(false);
    label.current?.focus();
  }

  // The arrow keys move over the months as over a table of four columns.
  function onGridKey(event: KeyboardEvent) {
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -4, ArrowDown: 4 }[event.key];
    if (!offset) return;
    const cells = Array.from(grid.current?.querySelectorAll<HTMLElement>("button") ?? []);
    const next = cells[cells.indexOf(document.activeElement as HTMLElement) + offset];
    if (!next) return;
    event.preventDefault();
    next.focus();
  }

  const text = every ? t.transactions.allMonths : monthLabel(props.month, language);
  // The month that takes the focus when the months open: the chosen one, the
  // current one, or the first of the year.
  const inYear = (month: string) => month.startsWith(`${year}-`);
  const start =
    !every && inYear(props.month) ? props.month : inYear(thisMonth) ? thisMonth : `${year}-01`;
  const place =
    props.align === "center" ? "inset-x-0 justify-center" : "left-0 sm:right-0 sm:left-auto";

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: Escape closes the months from any control inside.
    <div
      ref={root}
      className="relative inline-flex"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        // Inside a window, Escape closes the months and the window stays.
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        label.current?.focus();
      }}
    >
      <div className="inline-flex min-h-10 items-stretch overflow-clip rounded-(--radius-control) border border-control bg-surface">
        <button
          type="button"
          className={STEP}
          aria-label={t.transactions.previousMonth}
          disabled={every}
          onClick={() => props.onChange(shiftMonth(shown, -1))}
        >
          <ChevronLeftIcon />
        </button>
        <button
          ref={label}
          type="button"
          className="inline-flex min-w-44 items-center justify-center gap-1.5 border-line border-x px-3 font-medium transition-colors duration-150 hover:bg-ink/5 focus-visible:-outline-offset-2"
          aria-label={`${t.transactions.period}: ${text}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={toggle}
        >
          <span aria-live="polite">{text}</span>
          <span
            className={`text-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          >
            <ChevronDownIcon />
          </span>
        </button>
        <button
          type="button"
          className={STEP}
          aria-label={t.transactions.nextMonth}
          disabled={every}
          onClick={() => props.onChange(shiftMonth(shown, 1))}
        >
          <ChevronRightIcon />
        </button>
      </div>

      {open && (
        <div className={`absolute top-full z-20 mt-2 flex ${place}`}>
          <div
            role="dialog"
            aria-label={t.transactions.chooseMonth}
            className="popover w-68 shrink-0 p-3"
          >
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
            <div ref={grid} className="mt-2 grid grid-cols-4 gap-1" onKeyDown={onGridKey}>
              {Array.from({ length: 12 }, (_, index) => {
                const month = `${year}-${String(index + 1).padStart(2, "0")}`;
                const chosen = !every && month === props.month;
                return (
                  <button
                    key={month}
                    type="button"
                    data-start={month === start || undefined}
                    aria-label={monthLabel(month, language)}
                    aria-pressed={chosen}
                    className={`rounded-(--radius-control) py-2 text-sm transition-colors duration-150 ${
                      chosen
                        ? "bg-ink font-medium text-sheet"
                        : `hover:bg-ink/7 ${month === thisMonth ? "font-semibold text-accent-ink" : ""}`
                    }`}
                    onClick={() => choose(month)}
                  >
                    {shortMonth(index, language)}
                  </button>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap gap-2 border-line border-t pt-3">
              <button
                type="button"
                className="action flex-1 justify-center"
                aria-pressed={props.month === thisMonth}
                onClick={() => choose(thisMonth)}
              >
                {t.transactions.thisMonth}
              </button>
              {props.all && (
                <button
                  type="button"
                  className="action flex-1 justify-center"
                  aria-pressed={every}
                  onClick={() => choose("all")}
                >
                  {t.transactions.allMonths}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** "Jan", "Fev": the short name of a month, without the period of some languages. */
function shortMonth(index: number, language: string): string {
  const name = new Intl.DateTimeFormat(language, { month: "short" })
    .format(new Date(2026, index, 1))
    .replace(/\.$/, "");
  return name.charAt(0).toUpperCase() + name.slice(1);
}
