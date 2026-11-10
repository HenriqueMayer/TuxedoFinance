import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import { useMessages } from "../i18n";

/**
 * The window: the one way an object opens. It is a native modal dialog, so the
 * browser supplies the focus trap, Escape and the inert page behind it.
 *
 * Opening animates from `origin` (the clicked element) to the final frame.
 * Closing animates back, then calls `onClose`. A reduced-motion preference
 * replaces both with a short fade. The page behind is never unmounted.
 */
export function Window(props: {
  title: string;
  /** The element that opened the window. Without it the window fades in. */
  origin: HTMLElement | null;
  onClose: () => void;
  children: ReactNode;
}) {
  const t = useMessages();
  const titleId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const [full, setFull] = useState(false);
  const closing = useRef(false);
  const { origin, onClose } = props;

  // Open once. showModal() moves focus inside and makes the page inert.
  // A layout effect, so its cleanup runs while the dialog is still in the
  // document: close() can then return focus to the element that opened it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the origin is read at open time only.
  useLayoutEffect(() => {
    const element = dialog.current;
    if (!element) return;
    element.showModal();
    // showModal() focuses the first control, which is the close light. A form
    // marks the control where typing starts.
    element.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    travel(element, origin, "in");
    return () => element.close();
  }, []);

  async function close() {
    const element = dialog.current;
    if (!element || closing.current) return; // A second press during the exit does nothing.
    closing.current = true;
    await travel(element, origin, "out");
    element.close(); // Focus returns to the opener before the address changes.
    onClose();
  }

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: the click closes on the backdrop; Escape is the keyboard equivalent and arrives as onCancel.
    <dialog
      ref={dialog}
      className="window"
      data-size={full ? "full" : "fit"}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault(); // Escape closes through the same exit as the button.
        close();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) close(); // A click on the backdrop.
      }}
    >
      <header className="relative flex h-11 shrink-0 items-center border-b border-line px-3">
        <div className="flex items-center">
          <TrafficLight label={t.window.close} color="#ec6a5e" onClick={close} />
          <span className="grid size-6 place-items-center" aria-hidden="true">
            <span className="size-3 rounded-full bg-line" />
          </span>
          <TrafficLight
            label={full ? t.window.restore : t.window.expand}
            color="#61c554"
            onClick={() => setFull(!full)}
            pressed={full}
            className="max-sm:hidden"
          />
        </div>
        <h2
          id={titleId}
          className="pointer-events-none absolute inset-x-24 truncate text-center text-sm font-semibold"
        >
          {props.title}
        </h2>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5">{props.children}</div>
    </dialog>
  );
}

/** A window control. The colored dot is 12px; the pointer target is 24px. */
function TrafficLight(props: {
  label: string;
  color: string;
  onClick: () => void;
  pressed?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={props.label}
      aria-pressed={props.pressed}
      title={props.label}
      onClick={props.onClick}
      className={`grid size-6 place-items-center rounded-full ${props.className ?? ""}`}
    >
      <span
        className="size-3 rounded-full ring-1 ring-black/15 ring-inset"
        style={{ background: props.color }}
      />
    </button>
  );
}

/** Animate the window from or to its origin. Resolves when the motion ends. */
function travel(element: HTMLElement, origin: HTMLElement | null, direction: "in" | "out") {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const from = origin?.isConnected ? origin.getBoundingClientRect() : null;
  const to = element.getBoundingClientRect();

  let away: Keyframe;
  if (reduced || !from || from.width === 0) {
    // No travel: a fade, with a slight scale only when motion is allowed.
    away = { opacity: 0, transform: reduced ? "none" : "scale(0.97)" };
  } else {
    const dx = from.left + from.width / 2 - (to.left + to.width / 2);
    const dy = from.top + from.height / 2 - (to.top + to.height / 2);
    const scale = `${from.width / to.width}, ${from.height / to.height}`;
    away = { opacity: 0, transform: `translate(${dx}px, ${dy}px) scale(${scale})` };
  }
  const home: Keyframe = { opacity: 1, transform: "none" };

  const animation = element.animate(direction === "in" ? [away, home] : [home, away], {
    duration: reduced ? 120 : direction === "in" ? 260 : 180,
    easing: direction === "in" ? "cubic-bezier(0.2, 0.8, 0.2, 1)" : "cubic-bezier(0.4, 0, 1, 1)",
    fill: direction === "out" ? "forwards" : "none",
  });
  // A cancelled animation rejects; the window still closes or stays open correctly.
  return animation.finished.catch(() => undefined);
}

/**
 * Attributes for the control where typing starts in a window. The window
 * focuses a marked control when it opens. The ref covers content that arrives
 * later, for example after its data has loaded.
 */
export const autofocus = {
  "data-autofocus": true,
  ref: (element: HTMLElement | null) => element?.focus(),
};
