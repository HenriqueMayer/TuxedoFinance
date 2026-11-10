import { Link, useNavigate, useRouter, useRouterState } from "@tanstack/react-router";
import { createContext, type ReactNode, type RefObject, useCallback, useContext } from "react";
import { useMessages } from "../i18n";
import { Boundary } from "../ui/Boundary";
import { Window } from "../ui/Window";
import { AnalysisWindow } from "./analysis";
import { CategoriesWindow } from "./categories";
import { ClosingWindow } from "./closing";
import { AddEntry, EditEntry } from "./entry";
import { DueWindow, HomeBlocksWindow, MonthWindow, WorthWindow } from "./home";
import { ImportStartWindow, ImportWindow } from "./imports";
import { InvestmentWindow, NewInvestmentWindow } from "./investment";
import { NewProgramWindow, ProgramWindow } from "./loyalty";
import { OriginWindow } from "./origin";
import { BudgetWindow, GoalWindow, LimitWindow, NewBudgetWindow, NewGoalWindow } from "./plan";
import { RatesWindow } from "./rates";
import { ScheduleWindow } from "./schedule";
import { SettingsWindow } from "./settings";
import { SheetWindow } from "./sheet";
import { GrowthWindow, SalaryWindow } from "./tools";
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
  | "rates"
  | "closing"
  | "import"
  | `import:${number}`
  | "add"
  | "new-account"
  | "new-card"
  | "transfer"
  | "new-investment"
  | "new-program"
  | `program:${number}`
  | "worth"
  | "analysis"
  | "month"
  | "due"
  | "home-blocks"
  | "limit"
  | "new-budget"
  | "new-goal"
  | "sheet"
  | "salary"
  | "growth"
  | `sheet:${number}`
  | `budget:${number}`
  | `goal:${number}`
  | `transaction:${number}`
  | `account:${number}`
  | `card:${number}`
  | `invoice:${number}`
  | `investment:${number}`
  | `schedule:${number}`
  | `origin:${string}`;

/**
 * A window can have one window above it: the address names the first in `w`
 * and the one above in `w2`. The window below stays open and keeps its
 * state; Back, Escape and the close light act on the window above.
 */
type Level = 1 | 2;

// The level of the window that holds a component: 0 on the page.
const LevelOfWindow = createContext<0 | Level>(0);

// The element that opened the window of each level. The window animates from it.
const origins: Record<Level, HTMLElement | null> = { 1: null, 2: null };

declare module "@tanstack/react-router" {
  interface HistoryState {
    /** True when an in-app action opened the window, so closing can go Back. */
    openedHere?: boolean;
  }
}

/**
 * A link that opens a window. On the page it opens the first window. Inside
 * a window it takes the place of that window, at the same level.
 */
export function OpenWindow(props: {
  w: WindowId;
  className?: string;
  "aria-label"?: string;
  /** For a link inside a menu: "menuitem". */
  role?: string;
  /** The element that the window opens from, when the link itself goes away (a menu item). */
  from?: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const level: Level = useContext(LevelOfWindow) === 2 ? 2 : 1;
  return (
    <Link
      to="."
      search={(previous) =>
        level === 2 ? { ...previous, w2: props.w } : { ...previous, w: props.w, w2: undefined }
      }
      state={{ openedHere: true }}
      resetScroll={false}
      className={props.className}
      aria-label={props["aria-label"]}
      role={props.role}
      onClick={(event) => {
        origins[level] = props.from?.current ?? event.currentTarget;
      }}
    >
      {props.children}
    </Link>
  );
}

/**
 * Open a window above the open window, which stays as it is. `from` is the
 * element that the new window opens from.
 */
export function useOpenAbove() {
  const navigate = useNavigate();
  return useCallback(
    (w: WindowId, from?: HTMLElement | null) => {
      origins[2] = from ?? null;
      navigate({
        to: ".",
        search: (previous) => ({ ...previous, w2: w }),
        state: { openedHere: true },
        resetScroll: false,
      });
    },
    [navigate],
  );
}

/** Renders the windows named by the address, if any. Mounted once, in the shell. */
export function WindowHost() {
  // Read from the location, not from a route: this file is part of the route
  // tree's own type (router → shell → host), so a typed route lookup is circular.
  const w = useRouterState({ select: (state) => (state.location.search as { w?: string }).w });
  const w2 = useRouterState({ select: (state) => (state.location.search as { w2?: string }).w2 });
  return (
    <>
      <Layer level={1} w={w} />
      {/* The window above opens after the one below, so the browser puts it on top. */}
      {w && <Layer level={2} w={w2} />}
    </>
  );
}

/** The window of one level. */
function Layer(props: { level: Level; w: string | undefined }) {
  const t = useMessages();
  const { level, w } = props;
  // `wm` is the month of the month window. It changes without closing the window.
  const wm = useRouterState({ select: (state) => (state.location.search as { wm?: string }).wm });
  // `wp` is the period of the analysis window.
  const wp = useRouterState({ select: (state) => (state.location.search as { wp?: string }).wp });
  const navigate = useNavigate();
  const router = useRouter();
  const setPeriod = useCallback(
    (period: string) =>
      navigate({
        to: ".",
        search: (previous) => ({ ...previous, wp: period }),
        replace: true,
        resetScroll: false,
        state: (state) => state,
      }),
    [navigate],
  );

  function close() {
    origins[level] = null;
    if (router.history.location.state.openedHere) {
      // The window was opened from this page: Back returns to it with no extra entry.
      router.history.back();
    } else {
      // The window came from a link or a reload: there is no page entry to go back to.
      navigate({
        to: ".",
        search: (previous) =>
          level === 2
            ? { ...previous, w2: undefined }
            : { ...previous, w: undefined, wm: undefined, wp: undefined, w2: undefined },
        replace: true,
        resetScroll: false,
      });
    }
  }

  let title: string;
  let content: ReactNode;
  let wide = false; // A window with a wide table opens at full size.
  // A window that shows one record is named "kind:id".
  const [kind, idText] = (w ?? "").split(":");
  const id = /^\d+$/.test(idText ?? "") ? Number(idText) : null;
  if (w === "settings") {
    title = t.settings.title;
    content = <SettingsWindow />;
  } else if (w === "categories") {
    title = t.categories.title;
    content = <CategoriesWindow />;
  } else if (w === "rates") {
    title = t.rates.title;
    content = <RatesWindow />;
  } else if (w === "closing") {
    title = t.closing.title;
    content = <ClosingWindow />;
  } else if (w === "import") {
    title = t.imports.title;
    content = <ImportStartWindow />;
  } else if (kind === "import" && id !== null) {
    title = t.imports.title;
    content = <ImportWindow id={id} onDone={close} />;
    wide = true;
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
  } else if (kind === "origin") {
    title = t.analysis.originTitle;
    content = <OriginWindow id={w ?? ""} />;
  } else if (w === "analysis") {
    title = t.analysis.title;
    content = <AnalysisWindow period={wp} onPeriod={setPeriod} />;
    wide = true;
  } else if (w === "limit") {
    title = t.plan.limit.title;
    content = <LimitWindow onDone={close} />;
  } else if (w === "new-budget") {
    title = t.plan.budgets.new;
    content = <NewBudgetWindow onDone={close} />;
  } else if (w === "new-goal") {
    title = t.plan.goals.new;
    content = <NewGoalWindow />;
  } else if (w === "sheet" || (kind === "sheet" && id !== null)) {
    title = t.plan.sheet.title;
    content = <SheetWindow id={id ?? undefined} onDone={close} />;
    wide = true;
  } else if (w === "salary") {
    title = t.plan.tools.salary;
    content = <SalaryWindow />;
  } else if (w === "growth") {
    title = t.plan.tools.growth;
    content = <GrowthWindow />;
  } else if (kind === "budget" && id !== null) {
    title = t.plan.budgets.budget;
    content = <BudgetWindow id={id} onDone={close} />;
  } else if (kind === "goal" && id !== null) {
    title = t.plan.goals.goal;
    content = <GoalWindow id={id} onDone={close} />;
  } else if (w === "new-program") {
    title = t.loyalty.new;
    content = <NewProgramWindow />;
  } else if (kind === "program" && id !== null) {
    title = t.loyalty.program;
    content = <ProgramWindow id={id} onDone={close} />;
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
    <Window key={w} title={title} origin={origins[level]} onClose={close} wide={wide}>
      <LevelOfWindow value={level}>
        <Boundary>{content}</Boundary>
      </LevelOfWindow>
    </Window>
  );
}
