import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMessages } from "../i18n";
import { CheckIcon, ChevronDownIcon, SearchIcon } from "./icons";
import { Panel } from "./Panel";

export type Choice = {
  value: string;
  label: string;
  /** A second line under the label, for example the bank of an account. */
  hint?: string;
  /** The heading that the choice is listed under. */
  group?: string;
};

// A short list is read at a glance. A longer one gets a search box.
const SEARCH_FROM = 8;

/** Lower case without accents, so "saude" finds "Saúde". */
function plain(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/**
 * One choice from a list of the owner's records or of fixed values. The
 * control shows the choice; its panel lists the choices under their headings
 * and, for a long list, filters them as the owner types.
 *
 * Keys: Enter, Space or an arrow opens the list; a letter opens it and
 * starts the search. In the list, the arrows move, Enter chooses and Escape
 * closes. It works with a value and `onChange`, or inside a form with `name`.
 */
export function Select(props: {
  id?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  options: Choice[];
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  /** The text of the control while no choice is made. The owner cannot return to it. */
  placeholder?: string;
  /** Words for "no choice". With them the list starts with that choice, and its value is "". */
  empty?: string;
  /** The name of the value in a form. */
  name?: string;
  disabled?: boolean;
  /** A small control, for a row of a table or of a list of settings. */
  compact?: boolean;
  /** A short mark before the choice, inside the control: the symbol of a currency. */
  lead?: ReactNode;
  className?: string;
}) {
  const t = useMessages();
  const list = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [own, setOwn] = useState(props.defaultValue ?? "");
  const asked = props.value ?? own;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const options = useMemo(
    () =>
      props.empty === undefined
        ? props.options
        : [{ value: "", label: props.empty }, ...props.options],
    [props.options, props.empty],
  );
  // A select without words for "no choice" always has a choice: the first one
  // stands for a value that the list does not have.
  const value =
    options.some((option) => option.value === asked) || props.placeholder !== undefined
      ? asked
      : (options[0]?.value ?? "");
  const searchable = props.options.length >= SEARCH_FROM;
  const found = useMemo(() => {
    const words = plain(query).split(/\s+/).filter(Boolean);
    if (words.length === 0) return options;
    return options.filter((option) => {
      const text = plain(`${option.label} ${option.hint ?? ""} ${option.group ?? ""}`);
      return option.value !== "" && words.every((word) => text.includes(word));
    });
  }, [options, query]);
  const chosen = options.find((option) => option.value === value);

  function show(text = "") {
    if (props.disabled) return;
    setQuery(text);
    setActive(
      text
        ? 0
        : Math.max(
            options.findIndex((option) => option.value === value),
            0,
          ),
    );
    setOpen(true);
  }

  function choose(next: string) {
    setOwn(next);
    props.onChange?.(next);
    setOpen(false);
    trigger.current?.focus();
  }

  function onTriggerKey(event: KeyboardEvent) {
    if (open) return;
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      show();
    } else if (searchable && event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      show(event.key);
    }
  }

  function onListKey(event: KeyboardEvent) {
    const last = found.length - 1;
    const move = { ArrowDown: active + 1, ArrowUp: active - 1, Home: 0, End: last }[event.key];
    if (move !== undefined) {
      event.preventDefault();
      setActive(Math.min(Math.max(move, 0), Math.max(last, 0)));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = found[active];
      if (option) choose(option.value);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <>
      {props.name && <input type="hidden" name={props.name} value={value} />}
      <button
        ref={trigger}
        type="button"
        role="combobox"
        id={props.id}
        aria-label={props["aria-label"]}
        aria-invalid={props["aria-invalid"]}
        aria-describedby={props["aria-describedby"]}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? list : undefined}
        disabled={props.disabled}
        className={`select-control ${props.compact ? "select-compact" : "field"} ${props.className ?? ""}`}
        data-empty={chosen && chosen.value !== "" ? undefined : ""}
        data-value={value}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onTriggerKey}
      >
        {props.lead !== undefined && (
          <span aria-hidden="true" className="select-lead amount">
            {props.lead}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">
          {chosen?.label ?? props.placeholder ?? ""}
          {/* The second line of the choice follows its name, where there is room for it. */}
          {chosen?.hint && !props.compact && <span className="text-muted"> · {chosen.hint}</span>}
        </span>
        <span
          className={`shrink-0 text-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        >
          <ChevronDownIcon />
        </span>
      </button>
      {open && (
        <Panel
          anchor={trigger}
          onClose={() => setOpen(false)}
          label={props["aria-label"] ?? chosen?.label ?? props.placeholder ?? t.common.choose}
          minWidth={searchable ? 280 : 200}
        >
          <Options
            id={list}
            found={found}
            value={value}
            active={active}
            query={searchable ? query : null}
            onQuery={(text) => {
              setQuery(text);
              setActive(0);
            }}
            onActive={setActive}
            onChoose={choose}
            onKey={onListKey}
          />
        </Panel>
      )}
    </>
  );
}

/** The search box and the list of a select. The focus stays on the box or on the list. */
function Options(props: {
  id: string;
  found: Choice[];
  value: string;
  active: number;
  /** The text of the search, or null for a list without a search box. */
  query: string | null;
  onQuery: (text: string) => void;
  onActive: (index: number) => void;
  onChoose: (value: string) => void;
  onKey: (event: KeyboardEvent) => void;
}) {
  const t = useMessages();
  const box = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const current = `${props.id}-${props.active}`;

  // The focus goes to the search box, or to the list when there is none. On a
  // phone the list takes it, so the keyboard does not cover the sheet at once.
  const searchable = props.query !== null;
  useEffect(() => {
    const narrow = matchMedia("(width < 40rem)").matches;
    (searchable && !narrow ? box.current : list.current)?.focus();
  }, [searchable]);

  // The option that the arrows reach stays in view.
  useEffect(() => {
    document.getElementById(current)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  let heading: string | undefined;
  return (
    <>
      {props.query !== null && (
        <label className="flex shrink-0 items-center gap-2 border-line border-b px-3 text-muted">
          <SearchIcon />
          <input
            ref={box}
            type="search"
            aria-label={t.common.search}
            aria-controls={props.id}
            aria-activedescendant={current}
            autoComplete="off"
            placeholder={t.common.search}
            className="select-search min-w-0 flex-1 bg-transparent py-2.5 text-ink placeholder:text-muted"
            value={props.query}
            onChange={(event) => props.onQuery(event.target.value)}
            onKeyDown={props.onKey}
          />
        </label>
      )}
      {/* biome-ignore lint/a11y/useFocusableInteractive: the list takes the focus by script when it has no search box. */}
      <div
        ref={list}
        id={props.id}
        role="listbox"
        tabIndex={-1}
        aria-activedescendant={current}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1 outline-none"
        onKeyDown={(event) => {
          // A letter typed on the list goes to the search box.
          if (searchable && event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
            box.current?.focus();
            return;
          }
          props.onKey(event);
        }}
      >
        {props.found.length === 0 && (
          <p className="px-2.5 py-3 text-sm text-muted">{t.common.nothingFound}</p>
        )}
        {props.found.map((option, index) => {
          const titled = option.group !== heading;
          heading = option.group;
          const chosen = option.value === props.value;
          return (
            <div key={option.value}>
              {titled && option.group && (
                <p className="px-2.5 pt-2.5 pb-1 text-muted text-xs font-medium">{option.group}</p>
              )}
              {/* biome-ignore lint/a11y/useKeyWithClickEvents: the keys are handled on the search box or on the list. */}
              <div
                id={`${props.id}-${index}`}
                role="option"
                tabIndex={-1}
                aria-selected={chosen}
                data-value={option.value}
                data-active={index === props.active ? "" : undefined}
                className="select-option"
                onPointerMove={() => index !== props.active && props.onActive(index)}
                onClick={() => props.onChoose(option.value)}
              >
                <span className="min-w-0 flex-1">
                  <span className={`block truncate ${option.value === "" ? "text-muted" : ""}`}>
                    {option.label}
                  </span>
                  {option.hint && (
                    <span className="block truncate text-muted text-xs">{option.hint}</span>
                  )}
                </span>
                {chosen && (
                  <span className="shrink-0 text-accent-ink">
                    <CheckIcon />
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
