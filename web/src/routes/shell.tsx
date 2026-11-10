import { Link, Outlet } from "@tanstack/react-router";
import { type ReactNode, useEffect, useRef } from "react";
import { useMessages } from "../i18n";
import { HomeIcon, Mark, PlanIcon, SettingsIcon, TransactionsIcon, WalletIcon } from "../ui/icons";
import { OpenWindow, WindowHost } from "../windows/host";

const ITEM =
  "flex items-center gap-3 rounded-(--radius-control) px-3 py-2.5 text-jacket-muted hover:text-jacket-ink aria-[current=page]:bg-jacket-ink/10 aria-[current=page]:text-jacket-ink max-md:flex-1 max-md:flex-col max-md:gap-1 max-md:px-1 max-md:py-1.5 max-md:text-xs";

function Destination(props: {
  to: "/" | "/transactions" | "/wallet" | "/plan";
  icon: ReactNode;
  label: string;
}) {
  return (
    <li className="max-md:flex max-md:flex-1">
      <Link
        to={props.to}
        className={ITEM} // The open window is in the search; it must not change which destination is current.
        activeOptions={{ exact: props.to === "/", includeSearch: false }}
      >
        {props.icon}
        <span>{props.label}</span>
      </Link>
    </li>
  );
}

/**
 * The frame of every signed-in page: the jacket (navigation) around the shirt
 * (the sheet with the page). A rail on a wide screen, a dock on a phone. Both
 * hold the same four destinations.
 */
export function Shell() {
  const t = useMessages();
  const add = useRef<HTMLLIElement>(null);

  // N opens the Add window from any page, unless the owner is typing or a
  // window is already open.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "n" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable], dialog")) return;
      if (document.querySelector("dialog[open]")) return;
      event.preventDefault();
      add.current?.querySelector<HTMLElement>("a:not([hidden])")?.click();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[14rem_minmax(0,1fr)]">
      {/* On a phone the brand and Settings sit above the sheet; the dock holds the rest. */}
      <header className="flex items-center justify-between bg-jacket px-4 py-2 text-jacket-ink md:hidden">
        <p className="flex items-center gap-2.5 font-semibold">
          <Mark />
          {t.app.name}
        </p>
        <OpenWindow
          w="settings"
          aria-label={t.nav.settings}
          className="grid size-10 place-items-center rounded-(--radius-control) text-jacket-muted"
        >
          <SettingsIcon />
        </OpenWindow>
      </header>
      <nav
        aria-label={t.nav.main}
        className="z-10 bg-jacket text-jacket-ink max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:border-t max-md:border-jacket-ink/15 md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:p-3"
      >
        <p className="flex items-center gap-2.5 px-3 pt-3 pb-6 font-semibold max-md:hidden">
          <Mark />
          {t.app.name}
        </p>
        <ul className="flex gap-1 max-md:items-center max-md:px-2 max-md:pb-[env(safe-area-inset-bottom)] md:flex-col">
          <Destination to="/" icon={<HomeIcon />} label={t.nav.home} />
          <Destination to="/transactions" icon={<TransactionsIcon />} label={t.nav.transactions} />
          {/* The Add action: first on the rail, in the middle of the dock. */}
          <li
            ref={add}
            className="max-md:flex max-md:flex-1 max-md:justify-center md:order-first md:px-1 md:pb-5"
          >
            <OpenWindow
              w="add"
              aria-label={t.entry.addShortcut}
              className="button-accent max-md:size-12 max-md:rounded-full max-md:p-0 md:w-full"
            >
              <span aria-hidden="true" className="text-xl leading-none">
                +
              </span>
              <span className="max-md:sr-only">{t.entry.add}</span>
            </OpenWindow>
          </li>
          <Destination to="/wallet" icon={<WalletIcon />} label={t.nav.wallet} />
          <Destination to="/plan" icon={<PlanIcon />} label={t.nav.plan} />
        </ul>
        <div className="mt-auto max-md:hidden">
          <OpenWindow w="settings" className={ITEM}>
            <SettingsIcon />
            <span>{t.nav.settings}</span>
          </OpenWindow>
        </div>
      </nav>
      <main className="min-h-dvh bg-sheet px-5 py-6 max-md:rounded-t-(--radius-sheet) max-md:pb-24 md:rounded-l-(--radius-sheet) md:px-10 md:py-9">
        <div className="mx-auto max-w-5xl">
          {import.meta.env.MODE === "demo" && (
            <p className="mb-5 rounded-(--radius-control) border border-line bg-surface px-3 py-2 text-sm text-muted">
              {t.demo.banner}
            </p>
          )}
          <Outlet />
        </div>
      </main>
      <WindowHost />
    </div>
  );
}
