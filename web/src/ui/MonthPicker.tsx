import { useEffect, useRef, useState } from "react";
import { useLanguage, useMessages } from "../i18n";
import { monthLabel, shiftMonth, todayIso } from "../lib/dates";
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from "./icons";
import { Months, STEP } from "./Months";

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
  /** The last month that can be shown ("YYYY-MM"). */
  max?: string;
  /** The side of the control where the months open. */
  align?: "start" | "end" | "center";
}) {
  const t = useMessages();
  const language = useLanguage();
  const thisMonth = todayIso().slice(0, 7);
  const every = props.month === "all";
  const shown = every ? thisMonth : props.month;

  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function choose(month: string) {
    props.onChange(month);
    setOpen(false);
    label.current?.focus();
  }

  const text = every ? t.transactions.allMonths : monthLabel(props.month, language);
  const place = {
    start: "left-0",
    center: "inset-x-0 justify-center",
    end: "left-0 sm:right-0 sm:left-auto",
  }[props.align ?? "end"];
  const last = props.max !== undefined && shown >= props.max;

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
          onClick={() => setOpen((value) => !value)}
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
          disabled={every || last}
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
            <Months month={every ? null : props.month} max={props.max} onChoose={choose} />

            <div className="mt-3 flex flex-wrap gap-2 border-line border-t pt-3">
              <button
                type="button"
                className="action flex-1 justify-center"
                aria-pressed={props.month === thisMonth}
                disabled={props.max !== undefined && thisMonth > props.max}
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
