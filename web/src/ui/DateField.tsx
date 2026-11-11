import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, monthLabel, shiftMonth, todayIso } from "../lib/dates";
import { useDateOrder } from "../session";
import { CalendarIcon, ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from "./icons";
import { Months, STEP } from "./Months";
import { Panel } from "./Panel";

type Control = {
  id?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  disabled?: boolean;
  className?: string;
  /** The name of the value in a form. */
  name?: string;
};

/** The calendar date of an ISO text, at noon so that no time zone moves the day. */
function at(iso: string): Date {
  const [year = 1970, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

/** The date that is `days` days from an ISO date. */
function shiftDay(iso: string, days: number): string {
  const date = at(iso);
  date.setDate(date.getDate() + days);
  return todayIso(date);
}

/**
 * A date. The control shows it in the owner's date order; its panel is a
 * calendar of one month. The name of the month opens the months of the year.
 *
 * Keys in the calendar: the arrows move one day or one week, Page Up and
 * Page Down one month, Enter chooses, Escape closes. It works with a value
 * and `onChange`, or inside a form with `name`.
 */
export function DateField(
  props: Control & {
    value?: string;
    defaultValue?: string;
    onChange?: (date: string) => void;
    /** The first and the last date that can be chosen ("YYYY-MM-DD"). */
    min?: string;
    max?: string;
    /** Words for "no date". With them the date can be empty. */
    empty?: string;
  },
) {
  const t = useMessages();
  const order = useDateOrder();
  const trigger = useRef<HTMLButtonElement>(null);
  const [own, setOwn] = useState(props.defaultValue ?? "");
  const value = props.value ?? own;
  const [open, setOpen] = useState(false);

  function choose(next: string) {
    setOwn(next);
    props.onChange?.(next);
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <>
      {props.name && <input type="hidden" name={props.name} value={value} />}
      <button
        ref={trigger}
        type="button"
        id={props.id}
        aria-label={props["aria-label"]}
        aria-invalid={props["aria-invalid"]}
        aria-describedby={props["aria-describedby"]}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={props.disabled}
        data-empty={value ? undefined : ""}
        className={`select-control date-control field ${props.className ?? ""}`}
        onClick={() => setOpen(!open)}
      >
        <span className="shrink-0 text-muted">
          <CalendarIcon />
        </span>
        <span className="amount min-w-0 flex-1 truncate">
          {value ? formatDate(value, order) : (props.empty ?? t.dates.choose)}
        </span>
      </button>
      {open && (
        <Panel
          anchor={trigger}
          onClose={() => setOpen(false)}
          label={props["aria-label"] ?? t.dates.choose}
          minWidth={296}
        >
          <Calendar
            value={value}
            min={props.min}
            max={props.max}
            empty={props.empty}
            onChoose={choose}
          />
        </Panel>
      )}
    </>
  );
}

/** One month of days, or the months of a year when the owner asks for them. */
function Calendar(props: {
  value: string;
  min?: string;
  max?: string;
  empty?: string;
  onChoose: (date: string) => void;
}) {
  const t = useMessages();
  const language = useLanguage();
  const today = todayIso();
  const allowed = (date: string) =>
    (props.min === undefined || date >= props.min) &&
    (props.max === undefined || date <= props.max);
  // The day that the arrow keys start from: the chosen one, or today.
  const [focused, setFocused] = useState(props.value || today);
  const [months, setMonths] = useState(false);
  const grid = useRef<HTMLDivElement>(null);
  // True when the day button must take the focus: on opening and after a key.
  const moved = useRef(true);
  const view = focused.slice(0, 7);

  // The focus goes to the calendar when it opens and follows the arrow keys.
  // A press on a step of the month leaves the focus on that step.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the day and the view say when to look for the button.
  useEffect(() => {
    if (!months && moved.current) {
      grid.current?.querySelector<HTMLElement>("[data-focused]")?.focus();
    }
    moved.current = false;
  }, [focused, months]);

  function go(next: string) {
    moved.current = true;
    setFocused(next);
  }

  function onKey(event: KeyboardEvent) {
    const days = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (days) {
      event.preventDefault();
      go(shiftDay(focused, days));
    } else if (event.key === "PageUp" || event.key === "PageDown") {
      event.preventDefault();
      const month = shiftMonth(view, event.key === "PageUp" ? -1 : 1);
      // The same day in the other month, or its last day.
      const last = new Date(Number(month.slice(0, 4)), Number(month.slice(5)), 0).getDate();
      go(`${month}-${String(Math.min(Number(focused.slice(8)), last)).padStart(2, "0")}`);
    }
  }

  const first = at(`${view}-01`);
  const length = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const days = Array.from(
    { length },
    (_, index) => `${view}-${String(index + 1).padStart(2, "0")}`,
  );
  // Sunday starts the week in both languages of the interface.
  const names = Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(language, { weekday: "narrow" }).format(new Date(2026, 1, 1 + index)),
  );
  const full = new Intl.DateTimeFormat(language, { dateStyle: "full" });

  return (
    <div className="p-3">
      {months ? (
        <Months
          month={view}
          min={props.min?.slice(0, 7)}
          max={props.max?.slice(0, 7)}
          onChoose={(month) => {
            setMonths(false);
            go(`${month}-01`);
          }}
        />
      ) : (
        <>
          <div className="flex items-center justify-between">
            <button
              type="button"
              className={`${STEP} h-8 rounded-(--radius-control)`}
              aria-label={t.transactions.previousMonth}
              onClick={() => setFocused(`${shiftMonth(view, -1)}-01`)}
            >
              <ChevronLeftIcon />
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-(--radius-control) px-2 py-1 text-sm font-semibold transition-colors duration-150 hover:bg-ink/5"
              aria-label={`${t.transactions.chooseMonth}: ${monthLabel(view, language)}`}
              onClick={() => setMonths(true)}
            >
              <span aria-live="polite">{monthLabel(view, language)}</span>
              <span className="text-muted">
                <ChevronDownIcon />
              </span>
            </button>
            <button
              type="button"
              className={`${STEP} h-8 rounded-(--radius-control)`}
              aria-label={t.transactions.nextMonth}
              onClick={() => setFocused(`${shiftMonth(view, 1)}-01`)}
            >
              <ChevronRightIcon />
            </button>
          </div>
          <div aria-hidden="true" className="mt-2 grid grid-cols-7 text-center text-muted text-xs">
            {names.map((name, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: the seven days of a week, in order.
              <span key={index} className="py-1">
                {name}
              </span>
            ))}
          </div>
          {/* biome-ignore lint/a11y/noStaticElementInteractions: the arrow keys move between the day buttons. */}
          <div ref={grid} className="grid grid-cols-7 gap-y-0.5" onKeyDown={onKey}>
            {days.map((date, index) => {
              const chosen = date === props.value;
              return (
                <button
                  key={date}
                  type="button"
                  style={index === 0 ? { gridColumnStart: first.getDay() + 1 } : undefined}
                  tabIndex={date === focused ? 0 : -1}
                  data-focused={date === focused ? "" : undefined}
                  aria-label={full.format(at(date))}
                  aria-pressed={chosen}
                  disabled={!allowed(date)}
                  className={`day ${chosen ? "day-chosen" : date === today ? "day-today" : ""}`}
                  onClick={() => props.onChoose(date)}
                >
                  {index + 1}
                </button>
              );
            })}
          </div>
        </>
      )}
      <div className="mt-3 flex flex-wrap gap-2 border-line border-t pt-3">
        <button
          type="button"
          className="action flex-1 justify-center"
          disabled={!allowed(today)}
          onClick={() => props.onChoose(today)}
        >
          {t.dates.today}
        </button>
        {props.empty !== undefined && (
          <button
            type="button"
            className="action flex-1 justify-center"
            onClick={() => props.onChoose("")}
          >
            {props.empty}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * A month. The control shows its name; its panel has the months of a year.
 * With `empty`, the month can be left out: the words say what that means,
 * for example "No end".
 */
export function MonthField(
  props: Control & {
    /** "YYYY-MM", or "" for no month. */
    value?: string;
    defaultValue?: string;
    onChange?: (month: string) => void;
    min?: string;
    max?: string;
    empty?: string;
  },
) {
  const t = useMessages();
  const language = useLanguage();
  const trigger = useRef<HTMLButtonElement>(null);
  const [own, setOwn] = useState(props.defaultValue ?? "");
  const value = props.value ?? own;
  const [open, setOpen] = useState(false);

  function choose(next: string) {
    setOwn(next);
    props.onChange?.(next);
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <>
      {props.name && <input type="hidden" name={props.name} value={value} />}
      <button
        ref={trigger}
        type="button"
        id={props.id}
        aria-label={props["aria-label"]}
        aria-invalid={props["aria-invalid"]}
        aria-describedby={props["aria-describedby"]}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={props.disabled}
        data-empty={value ? undefined : ""}
        className={`select-control date-control field ${props.className ?? ""}`}
        onClick={() => setOpen(!open)}
      >
        <span className="shrink-0 text-muted">
          <CalendarIcon />
        </span>
        <span className="min-w-0 flex-1 truncate">
          {value ? monthLabel(value, language) : (props.empty ?? t.transactions.chooseMonth)}
        </span>
      </button>
      {open && (
        <Panel
          anchor={trigger}
          onClose={() => setOpen(false)}
          label={props["aria-label"] ?? t.transactions.chooseMonth}
          minWidth={272}
        >
          <div className="p-3">
            <Months month={value || null} min={props.min} max={props.max} onChoose={choose} />
            {props.empty !== undefined && (
              <div className="mt-3 border-line border-t pt-3">
                <button
                  type="button"
                  className="action w-full justify-center"
                  aria-pressed={value === ""}
                  onClick={() => choose("")}
                >
                  {props.empty}
                </button>
              </div>
            )}
          </div>
        </Panel>
      )}
    </>
  );
}
