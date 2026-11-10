import { Link, useNavigate, useRouter, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useMessages } from "../i18n";
import { Window } from "../ui/Window";
import { SettingsWindow } from "./settings";

/**
 * Windows live in the address as the search parameter `w`, on any page:
 * `/transactions?month=2026-11&w=settings`. So a window has an address, Back
 * closes it, and the page behind keeps its path, filters and scroll position.
 */
export type WindowId = "settings";

// The element that opened the current window. The window animates from it.
let origin: HTMLElement | null = null;

declare module "@tanstack/react-router" {
  interface HistoryState {
    /** True when an in-app action opened the window, so closing can go Back. */
    openedHere?: boolean;
  }
}

/** A link that opens a window above the current page. */
export function OpenWindow(props: {
  w: WindowId;
  className?: string;
  "aria-label"?: string;
  children: ReactNode;
}) {
  return (
    <Link
      to="."
      search={(previous) => ({ ...previous, w: props.w })}
      state={{ openedHere: true }}
      resetScroll={false}
      className={props.className}
      aria-label={props["aria-label"]}
      onClick={(event) => {
        origin = event.currentTarget;
      }}
    >
      {props.children}
    </Link>
  );
}

/** Renders the window named by the address, if any. Mounted once, in the shell. */
export function WindowHost() {
  const t = useMessages();
  // Read from the location, not from a route: this file is part of the route
  // tree's own type (router → shell → host), so a typed route lookup is circular.
  const w = useRouterState({ select: (state) => (state.location.search as { w?: string }).w });
  const navigate = useNavigate();
  const router = useRouter();

  function close() {
    origin = null;
    if (router.history.location.state.openedHere) {
      // The window was opened from this page: Back returns to it with no extra entry.
      router.history.back();
    } else {
      // The window came from a link or a reload: there is no page entry to go back to.
      navigate({
        to: ".",
        search: (previous) => ({ ...previous, w: undefined }),
        replace: true,
        resetScroll: false,
      });
    }
  }

  if (w === "settings") {
    return (
      <Window key={w} title={t.settings.title} origin={origin} onClose={close}>
        <SettingsWindow />
      </Window>
    );
  }
  return null;
}
