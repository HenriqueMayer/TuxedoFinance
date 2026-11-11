import {
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

/**
 * Charts drawn for this product, in SVG, with the colors of the visual
 * language. A chart only draws: every number arrives calculated, and the
 * text of each value arrives formatted.
 *
 * Above the marks, one line names the series. Under the pointer or with the
 * arrow keys, a label with the values of one month floats above the plot,
 * so it never covers the marks. A click (or Enter) picks a month. A drag (or
 * Shift with an arrow key) selects a run of months; its figures show under
 * the marks, and Escape or a press outside the chart ends the selection.
 * Each chart has a table with the same values for a screen reader.
 */

/** The colors that a series can take. Four at most in one chart. */
export const CHART = {
  ink: "var(--color-ink)",
  accent: "var(--color-accent-ink)",
  positive: "var(--color-positive)",
  negative: "var(--color-negative)",
  quiet: "var(--color-control)",
} as const;

export type Series = {
  name: string;
  color: string;
  values: number[];
  /** The text of each value, for the line above the marks and for the table. */
  texts: string[];
  /** A line with dashes: a second mark besides the color. */
  dashed?: boolean;
  /** The main line of the chart. */
  strong?: boolean;
};

/** A run of months: the first and the last index. */
export type Run = [number, number];

type Shared = {
  title: string;
  labels: string[];
  series: Series[];
  /** A short text for a value of the axis, for example "2 mil". */
  axisText: (value: number) => string;
  height?: number;
  /** The owner chose a month, with a click or with Enter. */
  onPick?: (index: number) => void;
  /** The owner selected a run of months, or cleared the selection (null). */
  onSelect?: (run: Run | null) => void;
  selected?: Run | null;
  /** The figures of the selected run, shown under the marks. */
  summary?: ReactNode;
  /** The same figures for the label, when the pointer is on the selected run. */
  selection?: Reading;
};

/** What the floating label says: a name, and one row for each figure. */
export type Reading = {
  title: string;
  rows: { name: string; text: string; color?: string; dashed?: boolean; tone?: string }[];
};

/** Round values for an axis that covers `low` to `high`: 0, 2 000, 4 000… */
export function axisSteps(low: number, high: number, count = 4): number[] {
  const top = high > low ? high : low + 1;
  const raw = (top - low) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step =
    [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((size) => size >= raw) ?? raw;
  const first = Math.floor(low / step) * step;
  const last = Math.ceil(top / step) * step;
  const steps: number[] = [];
  for (let index = 0; first + index * step <= last + step / 1e6; index += 1) {
    steps.push(Number((first + index * step).toPrecision(12)));
  }
  return steps;
}

const LEFT = 48;
const TOP = 10;
const BOTTOM = 24;

type Frame = {
  /** The horizontal center of a month. */
  x: (index: number) => number;
  /** The vertical position of a value. */
  y: (value: number) => number;
  /** The width that one month has. */
  band: number;
  zero: number;
};

/** The axes, the line above the marks, the pointer and the keys that the charts share. */
function Plot(
  props: Shared & {
    low: number;
    high: number;
    /** A note of the legend, for example "Month in progress". */
    note?: string;
    children: (frame: Frame, active: number | null) => ReactNode;
  },
) {
  const root = useRef<HTMLDivElement>(null);
  const plot = useRef<HTMLDivElement>(null);
  // The name of the tint of a selected run, for the SVG.
  const tint = `tint-${useId().replace(/[^a-z0-9]/gi, "")}`;
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);
  // A drag in progress, and the month where the pointer went down.
  const [drag, setDrag] = useState<Run | null>(null);
  const down = useRef<number | null>(null);
  // The month where a selection with Shift and the arrow keys started.
  const anchor = useRef<number | null>(null);
  useEffect(() => {
    const element = plot.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A selected run ends with Escape, wherever the focus is, and with a press
  // outside the chart. Escape then does not close the window.
  const { selected, onSelect } = props;
  useEffect(() => {
    if (!selected || !onSelect) return;
    const outside = (event: globalThis.PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) onSelect(null);
    };
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      onSelect(null);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", onEscape, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", onEscape, true);
    };
  }, [selected, onSelect]);

  const height = props.height ?? 220;
  const count = props.labels.length;
  const steps = axisSteps(props.low, props.high);
  const [bottom = 0] = steps;
  const top = steps.at(-1) ?? 1;
  const inner = Math.max(width - LEFT - 8, 1);
  const band = inner / Math.max(count, 1);
  const frame: Frame = {
    band,
    x: (index) => LEFT + band * (index + 0.5),
    y: (value) => TOP + (height - TOP - BOTTOM) * (1 - (value - bottom) / (top - bottom)),
    zero: 0,
  };
  frame.zero = frame.y(Math.min(Math.max(0, bottom), top));
  // A label needs about 52 px: with many months, only some are written.
  const every = Math.max(1, Math.ceil((count * 52) / inner));

  /** The month under the pointer. During a drag, the nearest month. */
  function monthAt(event: PointerEvent<HTMLDivElement>, nearest: boolean): number | null {
    const box = event.currentTarget.getBoundingClientRect();
    const index = Math.floor((event.clientX - box.left - LEFT) / band);
    if (nearest) return Math.min(Math.max(index, 0), count - 1);
    return index >= 0 && index < count ? index : null;
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const index = monthAt(event, false);
    if (index === null) return;
    down.current = index;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const from = down.current;
    const index = monthAt(event, from !== null);
    setActive(index);
    if (from === null || index === null || !props.onSelect) return;
    if (drag || index !== from) setDrag([Math.min(from, index), Math.max(from, index)]);
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const from = down.current;
    down.current = null;
    if (drag) {
      // A drag that returns to its first month selects nothing.
      props.onSelect?.(drag[0] === drag[1] ? null : drag);
      setDrag(null);
    } else if (from !== null && monthAt(event, false) === from) {
      // With a selected run, a click ends the selection. Without one, it picks the month.
      if (props.selected) props.onSelect?.(null);
      else props.onPick?.(from);
    }
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape" && (props.selected || active !== null)) {
      event.stopPropagation();
      event.preventDefault();
      props.onSelect?.(null);
      setActive(null);
      anchor.current = null;
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && active !== null) {
      event.preventDefault();
      props.onPick?.(active);
      return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const from = active ?? (event.key === "ArrowLeft" ? count : -1);
    const next = Math.min(count - 1, Math.max(0, from + (event.key === "ArrowLeft" ? -1 : 1)));
    setActive(next);
    if (event.shiftKey && props.onSelect) {
      anchor.current ??= active ?? next;
      const start = anchor.current;
      props.onSelect(start === next ? null : [Math.min(start, next), Math.max(start, next)]);
    } else {
      anchor.current = null;
    }
  }

  const run = drag ?? props.selected ?? null;
  const plotHeight = height - TOP - BOTTOM;
  const runLeft = run ? frame.x(run[0]) - band / 2 : 0;
  const runWidth = run ? band * (run[1] - run[0] + 1) : 0;
  const onRun = active !== null && run !== null && active >= run[0] && active <= run[1];

  // The floating label: the months of a drag, the figures of the selected run
  // when the pointer is on it, or the values of the month under the pointer.
  let label: (Reading & { x: number }) | null = null;
  if (drag) {
    label = {
      x: runLeft + runWidth / 2,
      title: `${props.labels[drag[0]]} – ${props.labels[drag[1]]}`,
      rows: [],
    };
  } else if (onRun && props.selection) {
    label = { x: runLeft + runWidth / 2, ...props.selection };
  } else if (active !== null) {
    label = {
      x: frame.x(active),
      title: props.labels[active] ?? "",
      rows: props.series.map((series) => ({
        name: series.name,
        color: series.color,
        dashed: series.dashed,
        text: series.texts[active] ?? "",
      })),
    };
  }
  // The label follows its month or its run and stays inside the width of the chart.
  const side = !label
    ? ""
    : label.x < 130
      ? "left-0"
      : label.x > width - 130
        ? "right-0"
        : "-translate-x-1/2";

  return (
    // biome-ignore lint/a11y/useSemanticElements: a figure with a table inside; the SVG is its picture.
    <div ref={root} role="group" aria-label={props.title} className="grid gap-2">
      <table className="sr-only">
        <caption>{props.title}</caption>
        <thead>
          <tr>
            <td />
            {props.series.map((series) => (
              <th key={series.name} scope="col">
                {series.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.labels.map((label, index) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              {props.series.map((series) => (
                <td key={series.name}>{series.texts[index]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex min-h-6 flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted">
        {props.series.map((series) => (
          <span key={series.name} className="flex items-center gap-2">
            <Swatch color={series.color} dashed={series.dashed} />
            {series.name}
          </span>
        ))}
        {props.note && (
          <span className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block size-2.5 rounded-[3px] border border-ink border-dashed opacity-60"
            />
            {props.note}
          </span>
        )}
      </div>

      {/* biome-ignore lint/a11y/noStaticElementInteractions: the keys read the chart month by month; the table carries the values. */}
      <div
        ref={plot}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: the arrow keys, Enter and Shift work on the chart.
        tabIndex={0}
        className={`relative rounded-(--radius-control) ${
          drag ? "cursor-ew-resize" : props.onPick ? "cursor-pointer" : ""
        }`}
        // A horizontal drag selects months; a vertical one still scrolls the window.
        style={{ touchAction: "pan-y" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          down.current = null;
          setDrag(null);
        }}
        onPointerLeave={() => down.current === null && setActive(null)}
        onKeyDown={onKey}
        onBlur={() => setActive(null)}
      >
        {width > 0 && (
          <svg width={width} height={height} aria-hidden="true" className="block select-none">
            {steps.map((value) => (
              <g key={value}>
                <line
                  x1={LEFT}
                  x2={width - 8}
                  y1={frame.y(value)}
                  y2={frame.y(value)}
                  stroke="var(--color-line)"
                  strokeWidth={value === 0 ? 1.5 : 1}
                />
                <text
                  x={LEFT - 8}
                  y={frame.y(value) + 4}
                  textAnchor="end"
                  fontSize="12"
                  fill="var(--color-muted)"
                  className="amount"
                >
                  {props.axisText(value)}
                </text>
              </g>
            ))}
            <defs>
              <linearGradient id={tint} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" style={{ stopColor: "var(--color-accent)", stopOpacity: 0.3 }} />
                <stop offset="1" style={{ stopColor: "var(--color-accent)", stopOpacity: 0.05 }} />
              </linearGradient>
            </defs>
            {/* The selected run: a soft band behind the marks. */}
            {run && (
              <rect
                className="chart-run"
                x={runLeft}
                y={TOP - 6}
                width={runWidth}
                height={plotHeight + 6}
                rx="12"
                fill={`url(#${tint})`}
              />
            )}
            {active !== null && !run && (
              <rect
                x={frame.x(active) - band / 2}
                y={TOP - 6}
                width={band}
                height={plotHeight + 6}
                rx="10"
                fill="var(--color-ink)"
                opacity="0.06"
              />
            )}
            {props.children(frame, active !== null && !drag && !onRun ? active : null)}
            {run && (
              <>
                {/* The months outside the run step back; the run keeps its full color. */}
                <rect
                  className="chart-run"
                  x={LEFT}
                  y={TOP - 6}
                  width={Math.max(runLeft - LEFT, 0)}
                  height={plotHeight + 5}
                  fill="var(--color-surface)"
                  opacity="0.62"
                />
                <rect
                  className="chart-run"
                  x={runLeft + runWidth}
                  y={TOP - 6}
                  width={Math.max(width - 8 - runLeft - runWidth, 0)}
                  height={plotHeight + 5}
                  fill="var(--color-surface)"
                  opacity="0.62"
                />
                {/* A short grip at each end, as on a handle that can be moved. */}
                {[runLeft, runLeft + runWidth].map((x, index) => (
                  <rect
                    // biome-ignore lint/suspicious/noArrayIndexKey: the two ends of one run.
                    key={index}
                    className="chart-run"
                    x={x - 2}
                    y={TOP + plotHeight / 2 - 16}
                    width="4"
                    height="32"
                    rx="2"
                    fill="var(--color-accent)"
                  />
                ))}
              </>
            )}
            {props.labels.map((label, index) => {
              const inside = run !== null && index >= run[0] && index <= run[1];
              return (count - 1 - index) % every === 0 ? (
                <text
                  key={label}
                  x={frame.x(index)}
                  y={height - 6}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight={inside ? 600 : 400}
                  fill={inside ? "var(--color-ink)" : "var(--color-muted)"}
                >
                  {label}
                </text>
              ) : null;
            })}
          </svg>
        )}
        {/* The label floats above the plot, never over the marks. */}
        {label && (
          <div
            data-reading
            aria-hidden="true"
            className={`popover pointer-events-none absolute bottom-full z-10 mb-0.5 px-3 py-2 text-sm ${side}`}
            style={side === "-translate-x-1/2" ? { left: label.x } : undefined}
          >
            <p className="whitespace-nowrap font-medium">{label.title}</p>
            {label.rows.map((row) => (
              <p key={row.name} className="mt-0.5 flex items-center gap-2 whitespace-nowrap">
                {row.color && <Swatch color={row.color} dashed={row.dashed} />}
                <span className="text-muted">{row.name}</span>
                <span className={`amount ml-auto pl-3 font-medium ${row.tone ?? ""}`}>
                  {row.text}
                </span>
              </p>
            ))}
          </div>
        )}
      </div>

      {/* The figures of a selected run, under the marks: the chart keeps its place. */}
      {run && !drag && props.summary && (
        <div
          data-run
          className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted"
          aria-live="polite"
        >
          {props.summary}
        </div>
      )}
    </div>
  );
}

/** The mark of a series in a legend: a square, or a short dashed line. */
export function Swatch(props: { color: string; dashed?: boolean }) {
  return props.dashed ? (
    <span
      aria-hidden="true"
      className="inline-block w-3.5 shrink-0 border-t-2 border-dashed"
      style={{ borderColor: props.color }}
    />
  ) : (
    <span
      aria-hidden="true"
      className="inline-block size-2.5 shrink-0 rounded-[3px]"
      style={{ background: props.color }}
    />
  );
}

/**
 * Amounts of each month as bars, one bar for each series. The bars start at
 * zero. The bars of a month that is not over are lighter, with a dashed edge.
 */
export function BarChart(
  props: Shared & {
    /** The index of a month that is not over, and the words of the legend for it. */
    partial?: number;
    partialNote?: string;
  },
) {
  const values = props.series.flatMap((series) => series.values);
  return (
    <Plot
      {...props}
      low={Math.min(0, ...values)}
      high={Math.max(1, ...values)}
      note={props.partial === undefined ? undefined : props.partialNote}
    >
      {(frame) => {
        const group = Math.min(frame.band * 0.72, 56);
        const bar = Math.max(group / props.series.length - 2, 1);
        return props.series.map((series, position) =>
          series.values.map((value, index) => {
            const y = frame.y(value);
            const open = index === props.partial;
            return (
              <rect
                // biome-ignore lint/suspicious/noArrayIndexKey: a bar is the value of a fixed position.
                key={`${series.name}-${index}`}
                x={frame.x(index) - group / 2 + position * (bar + 2) + 1}
                y={Math.min(y, frame.zero)}
                width={bar}
                height={Math.max(Math.abs(frame.zero - y), value === 0 ? 0 : 1)}
                rx={Math.min(2, bar / 2)}
                fill={series.color}
                fillOpacity={open ? 0.4 : 1}
                stroke={open ? series.color : "none"}
                strokeDasharray={open ? "3 2" : undefined}
                className="chart-mark"
              />
            );
          }),
        );
      }}
    </Plot>
  );
}

/**
 * Values at each month end as lines. The axis covers the values of the
 * series and says its range; it starts at zero when the values are near it.
 */
export function LineChart(props: Shared) {
  const values = props.series.flatMap((series) => series.values);
  const high = Math.max(...values, 1);
  const lowest = Math.min(...values, high);
  // A range that starts far from zero shows the change; near zero, zero is the honest start.
  const low = lowest < 0 || lowest > high * 0.5 ? lowest : 0;
  return (
    <Plot {...props} low={low} high={high}>
      {(frame, active) =>
        props.series.map((series) => {
          const points = series.values.map((value, index) => [frame.x(index), frame.y(value)]);
          const last = points.at(-1);
          const at = active === null ? undefined : points[active];
          return (
            <g key={series.name}>
              <path
                d={points.map((point, index) => `${index ? "L" : "M"}${point.join(",")}`).join(" ")}
                fill="none"
                stroke={series.color}
                strokeWidth={series.strong ? 2.5 : 1.75}
                strokeDasharray={series.dashed ? "5 4" : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
                className="chart-mark"
              />
              {last && (
                <circle
                  cx={last[0]}
                  cy={last[1]}
                  r={series.strong ? 4 : 3}
                  fill={series.color}
                  className="chart-mark"
                />
              )}
              {at && (
                <circle
                  cx={at[0]}
                  cy={at[1]}
                  r="4.5"
                  fill="var(--color-surface)"
                  stroke={series.color}
                  strokeWidth="2"
                />
              )}
            </g>
          );
        })
      }
    </Plot>
  );
}

/** Parts of one total as one bar. Each part has its percentage of the width. */
export function ShareBar(props: { parts: { name: string; color: string; percent: number }[] }) {
  return (
    <div aria-hidden="true" className="flex h-3 gap-0.5 overflow-hidden rounded-full">
      {props.parts.map((part) => (
        <span
          key={part.name}
          className="chart-mark h-full first:rounded-l-full last:rounded-r-full"
          style={{ width: `${part.percent}%`, background: part.color }}
        />
      ))}
    </div>
  );
}
