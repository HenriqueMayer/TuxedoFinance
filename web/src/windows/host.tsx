import { Link, useNavigate, useRouter, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useMessages } from "../i18n";
import { Boundary } from "../ui/Boundary";
import { Window } from "../ui/Window";
import { CategoriesWindow } from "./categories";
import { AddEntry, EditEntry } from "./entry";
import { DueWindow, HomeBlocksWindow, MonthWindow, WorthWindow } from "./home";
import { InvestmentWindow, NewInvestmentWindow } from "./investment";
import { BudgetWindow, GoalWindow, LimitWindow, NewBudgetWindow, NewGoalWindow } from "./plan";
import { ScheduleWindow } from "./schedule";
import { SettingsWindow } from "./settings";
import {
  AccountWindow,
  CardWindow,
  InvoiceWindow,
  NewAccountWindow,
  NewCardWindow,
  TransferWindow,
} from "./wallet";

/**
 * Windows live in the address as the search parameter `w`, on any page:
 * `/transactions?month=2026-11&w=settings`. So a window has an address, Back
 * closes it, and the page behind keeps its path, filters and scroll position.
 */
export type WindowId =
  | "settings"
  | "categories"
  | "add"
  | "new-account"
  | "new-card"
  | "transfer"
  | "new-investment"
  | "worth"
  | "month"
  | "due"
  | "home-blocks"
  | "limit"
  | "new-budget"
  | "new-goal"
  | `budget:${number}`
  | `goal:${number}`
  | `transaction:${number}`
  | `account:${number}`
  | `card:${number}`
  | `invoice:${number}`
  | `investment:${number}`
  | `schedule:${number}`;

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
  // `wm` is the month of the month window. It changes without closing the window.
  const wm = useRouterState({ select: (state) => (state.location.search as { wm?: string }).wm });
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
        search: (previous) => ({ ...previous, w: undefined, wm: undefined }),
        replace: true,
        resetScroll: false,
      });
    }
  }

  let title: string;
  let content: ReactNode;
  // A window that shows one record is named "kind:id".
  const [kind, idText] = (w ?? "").split(":");
  const id = /^\d+$/.test(idText ?? "") ? Number(idText) : null;
  if (w === "settings") {
    title = t.settings.title;
    content = <SettingsWindow />;
  } else if (w === "categories") {
    title = t.categories.title;
    content = <CategoriesWindow />;
  } else if (w === "add") {
    title = t.entry.add;
    content = <AddEntry onDone={close} />;
  } else if (w === "month") {
    title = t.home.monthTitle;
    content = (
      <MonthWindow
        month={wm}
        onMonth={(month) =>
          navigate({
            to: ".",
            search: (previous) => ({ ...previous, wm: month }),
            replace: true,
            resetScroll: false,
            // Keep the mark that says this window was opened from the page.
            state: (state) => state,
          })
        }
      />
    );
  } else if (w === "due") {
    title = t.home.blocks.due;
    content = <DueWindow />;
  } else if (w === "home-blocks") {
    title = t.home.edit;
    content = <HomeBlocksWindow />;
  } else if (w === "new-account") {
    title = t.wallet.newAccount;
    content = <NewAccountWindow onDone={close} />;
  } else if (w === "new-card") {
    title = t.wallet.newCard;
    content = <NewCardWindow onDone={close} />;
  } else if (w === "transfer") {
    title = t.wallet.transfer;
    content = <TransferWindow onDone={close} />;
  } else if (w === "new-investment") {
    title = t.invest.new;
    content = <NewInvestmentWindow onDone={close} />;
  } else if (w === "worth") {
    title = t.home.blocks.worth;
    content = <WorthWindow />;
  } else if (w === "limit") {
    title = t.plan.limit.title;
    content = <LimitWindow onDone={close} />;
  } else if (w === "new-budget") {
    title = t.plan.budgets.new;
    content = <NewBudgetWindow onDone={close} />;
  } else if (w === "new-goal") {
    title = t.plan.goals.new;
    content = <NewGoalWindow />;
  } else if (kind === "budget" && id !== null) {
    title = t.plan.budgets.budget;
    content = <BudgetWindow id={id} onDone={close} />;
  } else if (kind === "goal" && id !== null) {
    title = t.plan.goals.goal;
    content = <GoalWindow id={id} onDone={close} />;
  } else if (kind === "investment" && id !== null) {
    title = t.invest.investment;
    content = <InvestmentWindow id={id} onDone={close} />;
  } else if (kind === "transaction" && id !== null) {
    title = t.entry.edit;
    content = <EditEntry id={id} onDone={close} />;
  } else if (kind === "account" && id !== null) {
    title = t.wallet.account;
    content = <AccountWindow id={id} onDone={close} />;
  } else if (kind === "card" && id !== null) {
    title = t.wallet.card;
    content = <CardWindow id={id} onDone={close} />;
  } else if (kind === "invoice" && id !== null) {
    title = t.wallet.invoice;
    content = <InvoiceWindow id={id} />;
  } else if (kind === "schedule" && id !== null) {
    title = t.schedule.title;
    content = <ScheduleWindow id={id} />;
  } else {
    return null; // No window, or an id that this version does not know.
  }
  // The key remounts the window when the address names another one.
  return (
    <Window key={w} title={title} origin={origin} onClose={close}>
      <Boundary>{content}</Boundary>
    </Window>
  );
}
