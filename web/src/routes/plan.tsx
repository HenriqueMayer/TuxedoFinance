import { useQuery } from "@tanstack/react-query";
import {
  type Budget,
  type Forecast,
  forecastQuery,
  type Goal,
  goalsQuery,
  type MonthPlan,
  planQuery,
  savedSheetsQuery,
} from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import type { Messages } from "../i18n/en";
import { monthLabel, monthOf, shortMonthLabel } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { CheckIcon, ChevronRightIcon, PlusIcon } from "../ui/icons";
import { Meter } from "../ui/Meter";
import { OpenWindow } from "../windows/host";

const CARD = "block rounded-(--radius-window) border border-line bg-surface p-5 card-open";

/** What the owner intends: the limit of the month, the category budgets and the goals. */
export function PlanPage() {
  const t = useMessages();
  const language = useLanguage();
  const plan = useQuery(planQuery);
  const goals = useQuery(goalsQuery);
  const forecast = useQuery(forecastQuery);

  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t.nav.plan}</h1>
        {plan.data && (
          <p className="flex flex-wrap items-center gap-x-4 gap-y-2 text-muted">
            <OpenWindow w="closing" className="action">
              <CheckIcon />
              {t.closing.open}
            </OpenWindow>
            {monthLabel(monthOf(plan.data.month), language)}
          </p>
        )}
      </div>
      {plan.isPending && <p className="py-10 text-muted">{t.common.loading}</p>}
      {(plan.isError || goals.isError) && (
        <div role="alert" className="grid justify-items-start gap-3 py-10">
          <p>{t.common.loadFailed}</p>
          <button
            type="button"
            className="button-quiet"
            onClick={() => {
              plan.refetch();
              goals.refetch();
            }}
          >
            {t.common.retry}
          </button>
        </div>
      )}
      {plan.data && <MonthLimit plan={plan.data} />}
      {plan.data && <Budgets plan={plan.data} />}
      {goals.data && <Goals goals={goals.data.goals} />}
      {forecast.data && <MonthsAhead forecast={forecast.data} />}
      {plan.data && <Tools />}
    </>
  );
}

/** The limit of the month and what is left of it. The card opens the limit. */
function MonthLimit(props: { plan: MonthPlan }) {
  const t = useMessages();
  const { plan } = props;
  const money = (amount: string) => formatAmount(amount, plan.currency);
  if (plan.limit === null || plan.left === null) {
    return (
      <OpenWindow w="limit" className={`${CARD} mt-6`}>
        <span className="block text-lg font-medium">{t.plan.month.noLimit}</span>
        <span className="mt-1 block max-w-prose text-muted">{t.plan.month.noLimitHelp}</span>
        <span className="mt-4 flex flex-wrap items-baseline justify-between gap-3">
          <span className="action">
            <PlusIcon />
            {t.plan.month.setLimit}
          </span>
          <span className="text-sm">
            <span className="text-muted">{t.plan.month.spent} </span>
            <span className="amount font-medium">{money(plan.expenses)}</span>
          </span>
        </span>
      </OpenWindow>
    );
  }
  const over = Number(plan.left) < 0;
  return (
    <OpenWindow w="limit" className={`${CARD} mt-6`}>
      <span className="block text-sm font-medium text-muted">
        {over ? t.plan.month.over : t.plan.month.left}
      </span>
      <span
        className={`amount mt-2 block text-4xl font-semibold tracking-tight ${over ? "text-negative" : ""}`}
      >
        {money(plan.left.replace("-", ""))}
      </span>
      <span className="mt-4 block">
        <Meter value={plan.expenses} total={plan.limit} />
      </span>
      <span className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm text-muted">
        <span>{t.plan.month.spentOf(money(plan.expenses), money(plan.limit))}</span>
        {plan.per_day !== null && <span>{t.plan.month.perDay(money(plan.per_day))}</span>}
      </span>
    </OpenWindow>
  );
}

/** One row for each budget, and the categories that could have one. */
function Budgets(props: { plan: MonthPlan }) {
  const t = useMessages();
  const { plan } = props;
  const money = (amount: string) => formatAmount(amount, plan.currency);
  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-2">
        <h2 className="font-medium">{t.plan.budgets.title}</h2>
        <OpenWindow w="new-budget" className="action">
          <PlusIcon />
          {t.plan.budgets.new}
        </OpenWindow>
      </div>
      {plan.budgets.length === 0 && <p className="py-4 text-muted">{t.plan.budgets.empty}</p>}
      <ul className="divide-y divide-line">
        {plan.budgets.map((budget) => (
          <li key={budget.category_id}>
            <BudgetRow budget={budget} money={money} />
          </li>
        ))}
      </ul>
      {plan.suggestions.length > 0 && (
        <p className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">{t.plan.budgets.suggestions}</span>
          {plan.suggestions.map((row) => (
            <OpenWindow
              key={row.category_id}
              w={`budget:${row.category_id}`}
              className="rounded-full border border-dashed border-control px-3 py-1 hover:bg-surface"
            >
              {row.name}
              {Number(row.average) > 0 && (
                <span className="text-muted"> · {t.plan.budgets.average(money(row.average))}</span>
              )}
            </OpenWindow>
          ))}
        </p>
      )}
    </section>
  );
}

function BudgetRow(props: { budget: Budget; money: (amount: string) => string }) {
  const t = useMessages();
  const { budget, money } = props;
  const over = Number(budget.left) < 0;
  return (
    <OpenWindow
      w={`budget:${budget.category_id}`}
      className="-mx-2 block rounded-(--radius-control) px-2 py-3 hover:bg-surface"
    >
      <span className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className="truncate font-medium">{budget.name}</span>
        <span className="amount text-sm">
          {t.plan.budgets.of(money(budget.spent), money(budget.limit))}
        </span>
      </span>
      <span className="mt-2 block">
        <Meter value={budget.spent} total={budget.limit} />
      </span>
      <span className={`amount mt-1.5 block text-sm ${over ? "text-negative" : "text-muted"}`}>
        {over
          ? t.plan.budgets.over(money(budget.left.replace("-", "")))
          : t.plan.budgets.left(money(budget.left))}
      </span>
    </OpenWindow>
  );
}

/** What the goal still needs, in words. */
export function goalStatus(goal: Goal | GoalBrief, t: Messages, language: string): string {
  const status = t.plan.goals.status;
  const money = (amount: string) => formatAmount(amount, goal.currency);
  if (goal.status === "reached") return status.reached;
  if (goal.status === "dated" && goal.monthly_needed && goal.target_date) {
    return status.dated(
      money(goal.monthly_needed),
      shortMonthLabel(monthOf(goal.target_date), language),
    );
  }
  if (goal.status === "overdue") return status.overdue(money(goal.remaining));
  return status.open(money(goal.remaining));
}

type GoalBrief = Pick<Goal, "currency" | "status" | "monthly_needed" | "target_date" | "remaining">;

function Goals(props: { goals: Goal[] }) {
  const t = useMessages();
  const active = props.goals.filter((goal) => !goal.is_archived);
  const archived = props.goals.filter((goal) => goal.is_archived);
  return (
    <section className="mt-10">
      <h2 className="border-b border-line pb-2 font-medium">{t.plan.goals.title}</h2>
      {active.length === 0 && (
        <p className="mt-4 max-w-prose text-muted">{t.plan.goals.emptyHelp}</p>
      )}
      <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {active.map((goal) => (
          <li key={goal.id}>
            <GoalCard goal={goal} />
          </li>
        ))}
        <li>
          <OpenWindow
            w="new-goal"
            className="flex h-full min-h-24 items-center justify-center rounded-(--radius-window) border border-dashed border-control p-4 font-medium hover:bg-surface"
          >
            {t.plan.goals.new}
          </OpenWindow>
        </li>
      </ul>
      {archived.length > 0 && (
        <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="text-muted">{t.plan.goals.archivedList}</span>
          {archived.map((goal) => (
            <OpenWindow key={goal.id} w={`goal:${goal.id}`} className="action">
              {goal.name}
            </OpenWindow>
          ))}
        </p>
      )}
    </section>
  );
}

function GoalCard(props: { goal: Goal }) {
  const t = useMessages();
  const language = useLanguage();
  const { goal } = props;
  const money = (amount: string) => formatAmount(amount, goal.currency);
  return (
    <OpenWindow w={`goal:${goal.id}`} className={CARD}>
      <span className="block truncate font-medium">{goal.name}</span>
      <span className="amount mt-3 block text-xl font-semibold">{money(goal.saved)}</span>
      <span className="amount block text-sm text-muted">
        {t.plan.goals.savedOf(`${goal.percent}%`, money(goal.target_amount))}
      </span>
      <span className="mt-3 block">
        <Meter value={goal.saved} total={goal.target_amount} />
      </span>
      <span className="mt-2 block text-sm text-muted">{goalStatus(goal, t, language)}</span>
    </OpenWindow>
  );
}

/** The cash of the next months, from the records. The card opens the sheet. */
function MonthsAhead(props: { forecast: Forecast }) {
  const t = useMessages();
  const language = useLanguage();
  const sheets = useQuery(savedSheetsQuery);
  const { forecast } = props;
  const money = (amount: string) => formatAmount(amount, forecast.currency);
  const tone = (amount: string) => (Number(amount) < 0 ? "text-negative" : "");
  const wide = "max-sm:hidden";
  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-2">
        <h2 className="font-medium">{t.plan.ahead.title}</h2>
        <p className="text-sm text-muted">{t.plan.ahead.today(money(forecast.opening_balance))}</p>
      </div>
      <p className="mt-3 max-w-prose text-sm text-muted">{t.plan.ahead.help}</p>
      <OpenWindow w="sheet" className={`${CARD} mt-4`}>
        <span className="grid grid-cols-[auto_1fr_1fr] gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr_1fr_1fr_1fr]">
          <span className="text-muted">{t.plan.ahead.month}</span>
          <span className={`text-right text-muted ${wide}`}>{t.plan.ahead.income}</span>
          <span className={`text-right text-muted ${wide}`}>{t.plan.ahead.expenses}</span>
          <span className="text-right text-muted">{t.plan.ahead.result}</span>
          <span className="text-right text-muted">{t.plan.ahead.balance}</span>
          {forecast.months.map((row) => (
            <span key={row.month} className="contents">
              <span>{shortMonthLabel(monthOf(row.month), language)}</span>
              <span className={`amount text-right ${wide}`}>{money(row.income)}</span>
              <span className={`amount text-right ${wide}`}>{money(row.expenses)}</span>
              <span className={`amount text-right ${tone(row.result)}`}>{money(row.result)}</span>
              <span className={`amount text-right font-semibold ${tone(row.balance)}`}>
                {money(row.balance)}
              </span>
            </span>
          ))}
        </span>
        <span className="action mt-4 w-fit">
          {t.plan.ahead.open}
          <ChevronRightIcon />
        </span>
      </OpenWindow>
      {!forecast.complete && (
        <p className="mt-3 text-sm text-muted">
          {t.plan.ahead.incomplete(forecast.missing_currencies.join(", "))}
        </p>
      )}
      {sheets.data && sheets.data.length > 0 && (
        <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="text-muted">{t.plan.ahead.saved}</span>
          {sheets.data.map((sheet) => (
            <OpenWindow key={sheet.id} w={`sheet:${sheet.id}`} className="action">
              {sheet.name}
            </OpenWindow>
          ))}
        </p>
      )}
    </section>
  );
}

/** The calculators. They read no record and save nothing. */
function Tools() {
  const t = useMessages();
  return (
    <section className="mt-10">
      <h2 className="border-b border-line pb-2 font-medium">{t.plan.tools.title}</h2>
      <ul className="mt-4 grid gap-4 sm:grid-cols-2">
        <li>
          <OpenWindow w="salary" className={`${CARD} h-full`}>
            <span className="block font-medium">{t.plan.tools.salary}</span>
            <span className="mt-1 block text-sm text-muted">{t.plan.tools.salaryHelp}</span>
          </OpenWindow>
        </li>
        <li>
          <OpenWindow w="growth" className={`${CARD} h-full`}>
            <span className="block font-medium">{t.plan.tools.growth}</span>
            <span className="mt-1 block text-sm text-muted">{t.plan.tools.growthHelp}</span>
          </OpenWindow>
        </li>
      </ul>
    </section>
  );
}
