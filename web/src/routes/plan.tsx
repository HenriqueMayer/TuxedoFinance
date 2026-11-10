import { useQuery } from "@tanstack/react-query";
import { type Budget, type Goal, goalsQuery, type MonthPlan, planQuery } from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import type { Messages } from "../i18n/en";
import { monthLabel, monthOf, shortMonthLabel } from "../lib/dates";
import { formatAmount } from "../lib/money";
import { Meter } from "../ui/Meter";
import { OpenWindow } from "../windows/host";

const CARD =
  "block rounded-(--radius-window) border border-line bg-surface p-5 transition-shadow hover:shadow-md";

/** What the owner intends: the limit of the month, the category budgets and the goals. */
export function PlanPage() {
  const t = useMessages();
  const language = useLanguage();
  const plan = useQuery(planQuery);
  const goals = useQuery(goalsQuery);

  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t.nav.plan}</h1>
        {plan.data && (
          <p className="text-muted">{monthLabel(monthOf(plan.data.month), language)}</p>
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
          <span className="link font-medium">{t.plan.month.setLimit}</span>
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
        <OpenWindow w="new-budget" className="link text-sm font-medium">
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
              <span className="text-muted"> · {t.plan.budgets.average(money(row.average))}</span>
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
            <OpenWindow key={goal.id} w={`goal:${goal.id}`} className="link">
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
