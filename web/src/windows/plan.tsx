import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, type ReactNode, useState } from "react";
import { categoriesQuery } from "../data/ledger";
import {
  type Goal,
  type GoalSource,
  goalsQuery,
  planQuery,
  useChangeGoal,
  useCreateGoal,
  useDeleteGoal,
  useReserve,
  useSetLimit,
} from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import { todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, formatAmount, parseAmount } from "../lib/money";
import { goalStatus } from "../routes/plan";
import { sessionQuery } from "../session";
import { Field } from "../ui/Field";
import { Meter } from "../ui/Meter";
import { autofocus } from "../ui/Window";
import { CURRENCIES } from "./settings";
import { Alert, ConfirmButton, values } from "./wallet";

type Currency = (typeof CURRENCIES)[number];

/**
 * One amount that holds from this month on: the limit of the month, or the
 * budget of a category. `children` are the fields before the amount.
 */
function LimitForm(props: {
  currency: string;
  current: string | null;
  categoryId?: number;
  removeLabel: string;
  help?: ReactNode;
  children?: ReactNode;
  onDone: () => void;
}) {
  const t = useMessages();
  const save = useSetLimit();
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const amount = parseAmount(typed.amount ?? "", props.currency);
    setInvalid(amount === null);
    if (amount === null) return;
    const category = props.categoryId ?? (Number(typed.category) || undefined);
    save.mutate({ amount, category_id: category }, { onSuccess: props.onDone });
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      {props.children}
      <Field
        label={`${t.plan.limit.amount} (${props.currency})`}
        errors={invalid ? [t.plan.limit.invalid] : fieldMessages(save.error, "amount")}
        help={t.plan.limit.help}
        className="max-w-sm"
      >
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="amount"
            inputMode="decimal"
            className="field amount"
            autoComplete="off"
            defaultValue={props.current ? editableAmount(props.current, props.currency) : ""}
          />
        )}
      </Field>
      {props.help}
      <Alert message={fieldMessages(save.error, "category_id")[0] ?? formMessage(save.error, t)} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        {props.current ? (
          <button
            type="button"
            className="button-quiet"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(
                { amount: null, category_id: props.categoryId },
                { onSuccess: props.onDone },
              )
            }
          >
            {props.removeLabel}
          </button>
        ) : (
          <span />
        )}
        <button type="submit" className="button-primary" disabled={save.isPending}>
          {t.common.save}
        </button>
      </div>
    </form>
  );
}

/** What the owner intends to spend in each month. */
export function LimitWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const { data: plan } = useSuspenseQuery(planQuery);
  return (
    <LimitForm
      currency={plan.currency}
      current={plan.limit}
      removeLabel={t.plan.limit.remove}
      onDone={props.onDone}
      help={
        <p className="text-sm text-muted">
          {t.plan.budgets.spentHelp(formatAmount(plan.expenses, plan.currency))}
        </p>
      }
    />
  );
}

/** The budget of one category: new for a category without one, otherwise a change. */
export function BudgetWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const { data: plan } = useSuspenseQuery(planQuery);
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const budget = plan.budgets.find((row) => row.category_id === props.id);
  const suggestion = plan.suggestions.find((row) => row.category_id === props.id);
  const name = (budget ?? suggestion ?? categories.find((row) => row.id === props.id))?.name;
  const money = (amount: string) => formatAmount(amount, plan.currency);
  if (!name) return <p className="text-muted">{t.common.loadFailed}</p>;
  return (
    <LimitForm
      currency={plan.currency}
      current={budget?.limit ?? null}
      categoryId={props.id}
      removeLabel={t.plan.budgets.remove}
      onDone={props.onDone}
      help={
        <p className="text-sm text-muted">
          {t.plan.budgets.spentHelp(money((budget ?? suggestion)?.spent ?? "0"))}{" "}
          {suggestion && t.plan.budgets.averageHelp(money(suggestion.average))}
        </p>
      }
    >
      <p className="text-lg font-medium">{name}</p>
    </LimitForm>
  );
}

/** A budget for any expense category that has none. */
export function NewBudgetWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const { data: plan } = useSuspenseQuery(planQuery);
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const taken = new Set(plan.budgets.map((row) => row.category_id));
  const names = new Map(categories.map((row) => [row.id, row.name]));
  const choices = categories
    .filter((row) => row.transaction_type !== "INCOME" && !taken.has(row.id))
    .map((row) => ({
      id: row.id,
      label: row.parent_id ? `${names.get(row.parent_id) ?? ""} › ${row.name}` : row.name,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return (
    <LimitForm
      currency={plan.currency}
      current={null}
      removeLabel={t.plan.budgets.remove}
      onDone={props.onDone}
      help={<p className="text-sm text-muted">{t.plan.budgets.help}</p>}
    >
      <Field label={t.plan.budgets.category} className="max-w-sm">
        {(control) => (
          <select {...control} name="category" className="field" defaultValue="">
            <option value="" disabled>
              {t.plan.budgets.choose}
            </option>
            {choices.map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        )}
      </Field>
    </LimitForm>
  );
}

/** Create a goal, then open it to reserve a balance. */
export function NewGoalWindow() {
  const t = useMessages();
  const navigate = useNavigate();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const create = useCreateGoal();
  const [currency, setCurrency] = useState<Currency>(session.preferences?.base_currency ?? "BRL");
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const target = parseAmount(typed.target ?? "", currency);
    setInvalid(target === null);
    if (target === null) return;
    create.mutate(
      {
        name: typed.name ?? "",
        target_amount: target,
        currency,
        target_date: typed.date || null,
      },
      {
        // The new goal takes the place of this window, so Back still closes it.
        onSuccess: (created) =>
          navigate({
            to: ".",
            search: (previous) => ({ ...previous, w: `goal:${created.id}` }),
            replace: true,
            resetScroll: false,
            state: (state) => state,
          }),
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <Field label={t.plan.goals.name} errors={fieldMessages(create.error, "name")}>
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="name"
            className="field"
            placeholder={t.plan.goals.namePlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <div className="flex flex-wrap gap-4">
        <Field
          label={t.plan.goals.target}
          errors={invalid ? [t.plan.limit.invalid] : fieldMessages(create.error, "target_amount")}
          className="w-48"
        >
          {(control) => (
            <input
              {...control}
              name="target"
              inputMode="decimal"
              className="field amount"
              autoComplete="off"
            />
          )}
        </Field>
        <Field label={t.plan.goals.currency}>
          {(control) => (
            <select
              {...control}
              className="field"
              value={currency}
              onChange={(event) => setCurrency(event.target.value as Currency)}
            >
              {CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
      <Field
        label={t.plan.goals.date}
        errors={fieldMessages(create.error, "target_date")}
        help={t.plan.goals.dateHelp}
        className="w-fit"
      >
        {(control) => (
          <input {...control} type="date" name="date" className="field" min={todayIso()} />
        )}
      </Field>
      <Alert message={formMessage(create.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={create.isPending}>
        {t.plan.goals.create}
      </button>
    </form>
  );
}

/** One goal: what it holds, the balances reserved for it, and its details. */
export function GoalWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const language = useLanguage();
  const { data } = useSuspenseQuery(goalsQuery);
  const goal = data.goals.find((row) => row.id === props.id);
  if (!goal) return null; // A deleted goal: the window is closing.
  const money = (amount: string) => formatAmount(amount, goal.currency);

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm text-muted">{goal.name}</p>
        <p className="amount text-3xl font-semibold">{money(goal.saved)}</p>
        <p className="amount mt-1 text-sm text-muted">
          {t.plan.goals.savedOf(`${goal.percent}%`, money(goal.target_amount))}
        </p>
        <p className="mt-3">
          <Meter value={goal.saved} total={goal.target_amount} />
        </p>
        <p className="mt-2 text-sm">{goalStatus(goal, t, language)}</p>
        {!goal.complete && (
          <p className="mt-2 text-sm text-muted">
            {t.plan.goals.incomplete(goal.missing_currencies.join(", "))}
          </p>
        )}
      </div>

      {goal.is_archived ? (
        <p className="text-sm text-muted">{t.plan.goals.isArchived}</p>
      ) : (
        <ReserveForm goal={goal} sources={data.sources} />
      )}
      <Reservations goal={goal} />
      <EditGoal goal={goal} onDone={props.onDone} />
    </div>
  );
}

function ReserveForm(props: { goal: Goal; sources: GoalSource[] }) {
  const t = useMessages();
  const { goal, sources } = props;
  const reserve = useReserve(goal.id);
  const [key, setKey] = useState(sources[0]?.key ?? "");
  const [invalid, setInvalid] = useState(false);
  const source = sources.find((row) => row.key === key);
  const held = goal.reservations.find((row) => row.source === key);
  if (!source) return <p className="text-sm text-muted">{t.plan.goals.noSources}</p>;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const amount = parseAmount(typed.amount ?? "", source?.currency ?? goal.currency);
    setInvalid(amount === null);
    if (amount === null) return;
    reserve.mutate({ source: key, amount });
  }

  return (
    <form
      onSubmit={submit}
      className="grid gap-4 rounded-(--radius-control) bg-sheet p-4"
      noValidate
    >
      <div className="flex flex-wrap items-start gap-4">
        <Field
          label={t.plan.goals.source}
          errors={fieldMessages(reserve.error, "source")}
          className="min-w-0 flex-1 basis-56"
        >
          {(control) => (
            <select
              {...control}
              className="field"
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
                reserve.reset();
              }}
            >
              {sources.map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label} · {t.plan.goals.free(formatAmount(row.free, row.currency))}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label={`${t.plan.goals.amount} (${source.currency})`}
          errors={invalid ? [t.plan.goals.amountInvalid] : fieldMessages(reserve.error, "amount")}
          className="w-48"
        >
          {(control) => (
            <input
              {...control}
              // The key shows what this balance already holds when the balance changes.
              key={`${key}-${held?.amount ?? ""}`}
              name="amount"
              inputMode="decimal"
              className="field amount"
              autoComplete="off"
              defaultValue={held ? editableAmount(held.amount, source.currency) : ""}
            />
          )}
        </Field>
      </div>
      <p className="text-sm text-muted">{t.plan.goals.reserveHelp}</p>
      <Alert message={formMessage(reserve.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={reserve.isPending}>
        {t.plan.goals.reserve}
      </button>
    </form>
  );
}

function Reservations(props: { goal: Goal }) {
  const t = useMessages();
  const { goal } = props;
  const reserve = useReserve(goal.id);
  return (
    <section>
      <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
        {t.plan.goals.reservations}
      </h3>
      {goal.reservations.length === 0 && (
        <p className="py-4 text-muted">{t.plan.goals.noReservations}</p>
      )}
      <ul className="divide-y divide-line">
        {goal.reservations.map((row) => (
          <li key={row.source} className="flex items-center gap-3 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{row.label}</span>
              {row.backed !== row.amount && (
                <span className="block text-sm text-muted">
                  {t.plan.goals.partly(formatAmount(row.backed, row.currency))}
                </span>
              )}
            </span>
            {!goal.is_archived && (
              <button
                type="button"
                className="link text-sm"
                disabled={reserve.isPending}
                onClick={() => reserve.mutate({ source: row.source, amount: "0" })}
              >
                {t.plan.goals.remove}
              </button>
            )}
            <span className="amount font-semibold">{formatAmount(row.amount, row.currency)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EditGoal(props: { goal: Goal; onDone: () => void }) {
  const t = useMessages();
  const { goal } = props;
  const change = useChangeGoal(goal.id);
  const remove = useDeleteGoal(goal.id);
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const target = parseAmount(typed.target ?? "", goal.currency);
    setInvalid(target === null);
    if (target === null) return;
    change.mutate({
      name: typed.name ?? "",
      target_amount: target,
      target_date: typed.date || null,
      is_archived: typed.archived === "on",
    });
  }

  return (
    <details>
      <summary className="link w-fit cursor-pointer text-sm">{t.plan.goals.edit}</summary>
      <form onSubmit={submit} className="mt-4 grid gap-5" noValidate>
        <Field label={t.plan.goals.name} errors={fieldMessages(change.error, "name")}>
          {(control) => (
            <input
              {...control}
              name="name"
              className="field"
              defaultValue={goal.name}
              autoComplete="off"
            />
          )}
        </Field>
        <div className="flex flex-wrap gap-4">
          <Field
            label={`${t.plan.goals.target} (${goal.currency})`}
            errors={invalid ? [t.plan.limit.invalid] : fieldMessages(change.error, "target_amount")}
            className="w-48"
          >
            {(control) => (
              <input
                {...control}
                name="target"
                inputMode="decimal"
                className="field amount"
                autoComplete="off"
                defaultValue={editableAmount(goal.target_amount, goal.currency)}
              />
            )}
          </Field>
          <Field label={t.plan.goals.date} errors={fieldMessages(change.error, "target_date")}>
            {(control) => (
              <input
                {...control}
                type="date"
                name="date"
                className="field"
                defaultValue={goal.target_date ?? ""}
              />
            )}
          </Field>
        </div>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            name="archived"
            className="size-4"
            defaultChecked={goal.is_archived}
          />
          <span>{t.plan.goals.archived}</span>
        </label>
        <Alert message={formMessage(change.error, t) ?? formMessage(remove.error, t)} />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ConfirmButton
            label={t.plan.goals.delete}
            pending={remove.isPending}
            onConfirm={() => remove.mutate(undefined, { onSuccess: props.onDone })}
          />
          <button type="submit" className="button-primary" disabled={change.isPending}>
            {t.common.save}
          </button>
        </div>
      </form>
    </details>
  );
}
