import {
  type ReactNode,
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

type Place = { left: number; width: number; top?: number; bottom?: number; maxHeight: number };

const GAP = 6;
const EDGE = 8;
const PHONE = "(width < 40rem)";

/**
 * A panel that opens from a control: the list of a select, a calendar. On a
 * wide screen it sits under its control, or above it when there is no room
 * below. On a phone it is a sheet at the bottom of the screen.
 *
 * It closes with Escape or with a press outside, and the focus returns to
 * the control. Inside a window, Escape closes the panel and the window stays.
 */
export function Panel(props: {
  /** The control that opened the panel. */
  anchor: RefObject<HTMLElement | null>;
  onClose: () => void;
  /** The name of the panel. On a phone it is the title of the sheet. */
  label: string;
  /** The least width on a wide screen, in pixels. The panel is never narrower than its control. */
  minWidth?: number;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [phone, setPhone] = useState(() => matchMedia(PHONE).matches);
  const [place, setPlace] = useState<Place | null>(null);
  const { anchor, onClose, minWidth = 0 } = props;

  // Where the panel sits. It is measured before the first paint and again
  // when the page scrolls or changes size, so the panel stays with its control.
  useLayoutEffect(() => {
    function measure() {
      const narrow = matchMedia(PHONE).matches;
      setPhone(narrow);
      const box = anchor.current?.getBoundingClientRect();
      if (narrow || !box) return;
      const width = Math.min(Math.max(box.width, minWidth), innerWidth - 2 * EDGE);
      const left = Math.min(Math.max(box.left, EDGE), innerWidth - width - EDGE);
      const below = innerHeight - box.bottom - GAP - EDGE;
      const above = box.top - GAP - EDGE;
      // Below when there is room for a useful list; otherwise the larger side.
      setPlace(
        below >= 260 || below >= above
          ? { left, width, top: box.bottom + GAP, maxHeight: Math.max(below, 160) }
          : { left, width, bottom: innerHeight - box.top + GAP, maxHeight: Math.max(above, 160) },
      );
    }
    measure();
    const onScroll = (event: Event) => {
      // The list of the panel scrolls by itself; that does not move the panel.
      if (!panel.current?.contains(event.target as Node)) measure();
    };
    addEventListener("resize", measure);
    document.addEventListener("scroll", onScroll, true);
    return () => {
      removeEventListener("resize", measure);
      document.removeEventListener("scroll", onScroll, true);
    };
  }, [anchor, minWidth]);

  useEffect(() => {
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !anchor.current?.contains(target)) onClose();
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // The panel takes this Escape: the window around it stays open.
      event.preventDefault();
      event.stopPropagation();
      onClose();
      anchor.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", onEscape, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", onEscape, true);
    };
  }, [anchor, onClose]);

  if (phone) {
    return (
      <>
        <div className="sheet-backdrop" aria-hidden="true" />
        <div ref={panel} role="dialog" aria-label={props.label} className="sheet">
          <div className="grid shrink-0 justify-items-center gap-2 px-5 pt-2.5 pb-3">
            <span aria-hidden="true" className="h-1 w-9 rounded-full bg-line" />
            <p className="text-sm font-semibold">{props.label}</p>
          </div>
          {props.children}
        </div>
      </>
    );
  }
  if (!place) return null;
  return (
    <div
      ref={panel}
      role="dialog"
      aria-label={props.label}
      className="popover fixed z-30 flex flex-col overflow-hidden"
      style={{
        left: place.left,
        width: place.width,
        top: place.top,
        bottom: place.bottom,
        maxHeight: Math.min(place.maxHeight, 384),
        transformOrigin: place.top === undefined ? "bottom" : "top",
      }}
    >
      {props.children}
    </div>
  );
}
