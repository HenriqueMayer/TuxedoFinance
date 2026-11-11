import {
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from "react";
import { MoreIcon } from "./icons";

/**
 * A button that opens a short list of the less frequent actions of a page.
 * The items have `role="menuitem"`. The arrow keys move between them, Escape
 * closes the list, and the focus returns to the button.
 */
export function Menu(props: {
  /** The name of the button, for example "More actions". */
  label: string;
  /** The items. They receive the button, so that a window can open from it. */
  children: (trigger: RefObject<HTMLButtonElement | null>) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  const items = () =>
    Array.from(panel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent) {
    const list = items();
    const at = list.indexOf(document.activeElement as HTMLElement);
    let next: HTMLElement | undefined;
    if (event.key === "ArrowDown") next = list[(at + 1) % list.length];
    else if (event.key === "ArrowUp") next = list[(at - 1 + list.length) % list.length];
    else if (event.key === "Home") next = list[0];
    else if (event.key === "End") next = list.at(-1);
    else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    } else if (event.key === "Tab") {
      setOpen(false);
      return;
    } else return;
    event.preventDefault();
    next?.focus();
  }

  return (
    <div ref={root} className="relative inline-flex">
      <button
        ref={trigger}
        type="button"
        className="button-quiet w-10 bg-surface px-0"
        aria-label={props.label}
        title={props.label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <MoreIcon />
      </button>
      {open && (
        // The click of an item reaches the list, and the list closes.
        // biome-ignore lint/a11y/useKeyWithClickEvents: the items are links and buttons; they answer the keyboard themselves.
        <div
          ref={panel}
          role="menu"
          aria-label={props.label}
          className="popover absolute top-full right-0 z-20 mt-2 grid min-w-52 gap-0.5 p-1"
          onKeyDown={onKeyDown}
          onClick={close}
        >
          {props.children(trigger)}
        </div>
      )}
    </div>
  );
}
