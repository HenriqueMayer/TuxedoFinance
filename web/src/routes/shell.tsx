import { Link, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
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
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[14rem_minmax(0,1fr)]">
      <nav
        aria-label={t.nav.main}
        className="z-10 bg-jacket text-jacket-ink max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:border-t max-md:border-jacket-ink/15 md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:p-3"
      >
        <p className="flex items-center gap-2.5 px-3 pt-3 pb-6 font-semibold max-md:hidden">
          <Mark />
          {t.app.name}
        </p>
        <ul className="flex gap-1 max-md:px-2 max-md:pb-[env(safe-area-inset-bottom)] md:flex-col">
          <Destination to="/" icon={<HomeIcon />} label={t.nav.home} />
          <Destination to="/transactions" icon={<TransactionsIcon />} label={t.nav.transactions} />
          <Destination to="/wallet" icon={<WalletIcon />} label={t.nav.wallet} />
          <Destination to="/plan" icon={<PlanIcon />} label={t.nav.plan} />
          <li className="max-md:flex max-md:flex-1 md:hidden">
            <OpenWindow w="settings" className={ITEM}>
              <SettingsIcon />
              <span>{t.nav.settings}</span>
            </OpenWindow>
          </li>
        </ul>
        <div className="mt-auto max-md:hidden">
          <OpenWindow w="settings" className={ITEM}>
            <SettingsIcon />
            <span>{t.nav.settings}</span>
          </OpenWindow>
        </div>
      </nav>
      <main className="min-h-dvh bg-sheet px-5 py-6 max-md:pb-24 md:rounded-l-(--radius-sheet) md:px-10 md:py-9">
        <div className="mx-auto max-w-5xl">
          <Outlet />
        </div>
      </main>
      <WindowHost />
    </div>
  );
}

/** A destination whose content is not built yet. Removed when the last part lands. */
export function Placeholder(props: { title: string }) {
  const t = useMessages();
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">{props.title}</h1>
      <p className="mt-2 text-muted">{t.common.comingSoon}</p>
    </>
  );
}
