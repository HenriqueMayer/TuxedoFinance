import { type KeyboardEvent, useEffect, useRef, useState } from "react";

type Pair = { start: number; end: number };

/**
 * A range of positions on one track, with a handle at each end. It is two
 * native range inputs on the same track.
 *
 * A handle follows the pointer between two positions and comes to rest on
 * the nearest one when the pointer lets go. Each position has a dot on the
 * track, and the dot where a moving handle will rest is lit. `onChange` is called when the
 * nearest position changes, so the owner sees the range change while the
 * handle moves. The arrow keys, Home and End move one whole position.
 */
export function RangeSlider(props: {
  /** The number of positions: 0 to `count - 1`. */
  count: number;
  start: number;
  end: number;
  onChange: (start: number, end: number) => void;
  startLabel: string;
  endLabel: string;
  /** The text of a position for a screen reader, for example "June 2026". */
  text: (position: number) => string;
  /** Named positions under the track, for example where "3 months" starts. */
  marks?: { position: number; label: string; on: boolean }[];
  /** A short name of a position, shown where a moving handle will rest: "Jun/26". */
  name?: (position: number) => string;
}) {
  const max = Math.max(props.count - 1, 1);
  // The place of the handles while they move: between two positions.
  const [live, setLive] = useState<Pair | null>(null);
  const frame = useRef(0);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  const shown = live ?? { start: props.start, end: props.end };
  const at = (position: number) => `calc(9px + (100% - 18px) * ${position / max})`;

  function move(handle: keyof Pair, value: number) {
    cancelAnimationFrame(frame.current);
    const next =
      handle === "start"
        ? { start: Math.min(value, shown.end), end: shown.end }
        : { start: shown.start, end: Math.max(value, shown.start) };
    setLive(next);
    const [start, end] = [Math.round(next.start), Math.round(next.end)];
    if (start !== props.start || end !== props.end) props.onChange(start, end);
  }

  /** Bring the handles to the nearest positions in a short motion. */
  function settle() {
    if (!live) return;
    const from = live;
    const to = { start: Math.round(from.start), end: Math.round(from.end) };
    const began = performance.now();
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = (now: number) => {
      const part = still ? 1 : Math.min((now - began) / 140, 1);
      const eased = 1 - (1 - part) ** 3;
      if (part >= 1) {
        setLive(null);
        return;
      }
      setLive({
        start: from.start + (to.start - from.start) * eased,
        end: from.end + (to.end - from.end) * eased,
      });
      frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  }

  function onKey(handle: keyof Pair, event: KeyboardEvent) {
    const current = handle === "start" ? props.start : props.end;
    const target = {
      ArrowLeft: current - 1,
      ArrowDown: current - 1,
      ArrowRight: current + 1,
      ArrowUp: current + 1,
      PageDown: current - 3,
      PageUp: current + 3,
      Home: 0,
      End: max,
    }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    const value = Math.min(Math.max(target, 0), max);
    if (handle === "start") props.onChange(Math.min(value, props.end), props.end);
    else props.onChange(props.start, Math.max(value, props.start));
  }

  const input = (handle: keyof Pair, label: string, front: boolean) => (
    <input
      type="range"
      min={0}
      max={max}
      step="any"
      value={shown[handle]}
      aria-label={label}
      aria-valuenow={props[handle]}
      aria-valuetext={props.text(props[handle])}
      style={{ zIndex: front ? 2 : 1 }}
      onChange={(event) => move(handle, Number(event.target.value))}
      onPointerUp={settle}
      onPointerCancel={settle}
      onBlur={settle}
      onKeyDown={(event) => onKey(handle, event)}
    />
  );

  // A name at an end of the track stays inside the track.
  const edge = (position: number) =>
    position === 0 ? "start" : position === max ? "end" : undefined;
  // The positions where the moving handles come to rest.
  const targets = live ? [Math.round(live.start), Math.round(live.end)] : [];
  const stops = Array.from({ length: max + 1 }, (_, position) => position);

  return (
    <div className={props.marks?.length ? "range range-marked" : "range"}>
      <span className="range-track" />
      <span
        className="range-chosen"
        style={{ left: at(shown.start), right: `calc(100% - ${at(shown.end)})` }}
      />
      {/* One dot for each position: where a handle can stop. The nearest one lights up. */}
      {stops.map((position) => (
        <span
          key={position}
          className="range-stop"
          style={{ left: at(position) }}
          data-in={position > shown.start && position < shown.end ? "" : undefined}
          data-near={targets.includes(position) ? "" : undefined}
        />
      ))}
      {/* While a handle moves, the names under the track are the months where the handles rest. */}
      {live && props.name
        ? [...new Set(targets)].map((position) => (
            <span
              key={position}
              aria-hidden="true"
              className="range-mark"
              style={{ left: at(position) }}
              data-on=""
              data-edge={edge(position)}
            >
              {props.name?.(position)}
            </span>
          ))
        : props.marks?.map((mark) => (
            <span
              key={mark.position}
              aria-hidden="true"
              className="range-mark"
              style={{ left: at(mark.position) }}
              data-on={mark.on ? "" : undefined}
              data-edge={edge(mark.position)}
            >
              {mark.label}
            </span>
          ))}
      {/* With both handles at the end of the track, the first one stays on top. */}
      {input("start", props.startLabel, shown.start > max / 2)}
      {input("end", props.endLabel, shown.start <= max / 2)}
    </div>
  );
}
