import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  type Income,
  incomesQuery,
  useDeleteIncome,
  useSalarySplit,
  useSaveIncome,
} from "../data/incomes";
import { categoriesQuery, useSaveCategory } from "../data/ledger";
import { walletQuery } from "../data/wallet";
import { useMessages } from "../i18n";
import { todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, formatAmount, parseAmount } from "../lib/money";
import { AmountInput } from "../ui/AmountInput";
import { MonthField } from "../ui/DateField";
import { Field } from "../ui/Field";
import { CloseIcon, PlusIcon } from "../ui/icons";
import { Select } from "../ui/Select";
import { autofocus } from "../ui/Window";
import { categoryChoices } from "./entry";
import { OpenWindow } from "./host";
import { Alert, ConfirmButton, values } from "./wallet";

/** The server takes this number of parts at most. */
const MAX_PARTS = 6;

type Part = { key: number; id?: number; day: string; amount: string };

/** A whole day of the month from typed text, or null. */
function dayOf(text: string): number | null {
  const day = Number(text);
  return /^\d{1,2}$/.test(text.trim()) && day >= 1 && day <= 31 ? day : null;
}

/** The recurring income with this id, or a new one. */
export function IncomeWindow(props: { id?: number; onDone: () => void }) {
  const { data } = useSuspenseQuery(incomesQuery);
  const income = data.items.find((item) => item.id === props.id);
  if (props.id !== undefined && !income) return null; // A deleted income: the window is closing.
  return <IncomeForm income={income} onDone={props.onDone} />;
}

/**
 * The form of a recurring income: where it arrives, and its parts. A part
 * is a day of the month and an amount; a salary with an advance has two.
 * The parts of a CLT salary can come from a calculation of the server.
 */
function IncomeForm(props: { income: Income | undefined; onDone: () => void }) {
  const t = useMessages();
  const text = t.plan.incomes;
  const { income } = props;
  const { data: wallet } = useSuspenseQuery(walletQuery);
  const save = useSaveIncome(income?.id);
  const split = useSalarySplit();

  const accounts = wallet.banks.flatMap((bank) =>
    bank.accounts.map((account) => ({ ...account, bank: bank.name })),
  );
  const [account, setAccount] = useState(String(income?.account.id ?? accounts[0]?.id ?? ""));
  const currency = accounts.find((item) => String(item.id) === account)?.currency ?? "BRL";
  const [category, setCategory] = useState(String(income?.category.id ?? ""));
  const [confirm, setConfirm] = useState(income?.confirm ?? false);
  const [clt, setClt] = useState(Boolean(income?.gross));
  const [count, setCount] = useState(income?.parts.length ?? 1);
  const [parts, setParts] = useState<Part[]>(
    income
      ? income.parts.map((part, key) => ({
          key,
          id: part.id,
          day: String(part.day),
          amount: editableAmount(part.amount, income.currency),
        }))
      : [{ key: 0, day: "5", amount: "" }],
  );
  const [invalid, setInvalid] = useState<string[]>([]);

  const setPart = (key: number, change: Partial<Part>) =>
    setParts(parts.map((part) => (part.key === key ? { ...part, ...change } : part)));
  const addPart = () => {
    setParts([...parts, { key: count, day: "", amount: "" }]);
    setCount(count + 1);
  };

  /** Ask the server for the two receipts of the typed salary, and write them as the parts. */
  function calculate(form: HTMLFormElement) {
    const typed = Object.fromEntries(new FormData(form)) as Record<string, string>;
    const gross = parseAmount(typed.gross ?? "", "BRL");
    const other = (typed.other ?? "").trim() === "" ? "0" : parseAmount(typed.other ?? "", "BRL");
    const percent = Number((typed.advance_percent ?? "").replace(",", "."));
    const days = [dayOf(typed.advance_day ?? ""), dayOf(typed.rest_day ?? "")];
    const dependents = Number(typed.dependents || "0");
    const wrong = [
      gross === null && "gross",
      other === null && "other",
      !(percent > 0 && percent < 100) && "advance_percent",
      days[0] === null && "advance_day",
      days[1] === null && "rest_day",
      !(Number.isInteger(dependents) && dependents >= 0 && dependents <= 30) && "dependents",
    ].filter((name): name is string => Boolean(name));
    setInvalid(wrong);
    if (wrong.length > 0 || gross === null || other === null) return;
    split.mutate(
      {
        gross,
        advance_percent: String(percent),
        dependents,
        other,
        pension: "0",
        transport: "0",
        food: "0",
        health: "0",
      },
      {
        onSuccess: (result) => {
          // A part that already has one of the two days keeps its entry.
          const next = [
            { day: String(days[0]), amount: result.advance },
            { day: String(days[1]), amount: result.remainder },
          ].map((part, index) => ({
            key: count + index,
            id: parts.find((old) => old.id !== undefined && old.day === part.day)?.id,
            day: part.day,
            amount: editableAmount(part.amount, "BRL"),
          }));
          setParts(next);
          setCount(count + 2);
        },
      },
    );
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const read = parts.map((part) => ({
      id: part.id,
      day: dayOf(part.day),
      amount: parseAmount(part.amount, currency),
    }));
    const gross = clt ? parseAmount(typed.gross ?? "", "BRL") : null;
    const percent = clt ? Number((typed.advance_percent ?? "").replace(",", ".")) : null;
    const wrong = [
      (typed.name ?? "").trim() === "" && "name",
      account === "" && "account_id",
      category === "" && "category_id",
      read.some((part) => part.day === null || part.amount === null) && "parts",
    ].filter((name): name is string => Boolean(name));
    setInvalid(wrong);
    if (wrong.length > 0) return;
    save.mutate(
      {
        name: typed.name ?? "",
        account_id: Number(account),
        category_id: Number(category),
        start: !income && typed.start ? `${typed.start}-01` : null,
        until: typed.until ? `${typed.until}-01` : null,
        confirm,
        // The inputs of the calculation are kept only while both are valid.
        gross: gross !== null && percent !== null && percent > 0 && percent < 100 ? gross : null,
        advance_percent:
          gross !== null && percent !== null && percent > 0 && percent < 100
            ? String(percent)
            : null,
        parts: read.map((part) => ({
          id: part.id ?? null,
          day: part.day ?? 1,
          amount: part.amount ?? "0",
        })),
      },
      { onSuccess: props.onDone },
    );
  }

  const errors = (name: string, message: string = text.invalid) =>
    invalid.includes(name) ? [message] : fieldMessages(save.error, name);
  const splitErrors = (name: string) =>
    invalid.includes(name) ? [text.invalid] : fieldMessages(split.error, name);

  if (accounts.length === 0) return <p className="text-muted">{text.noAccount}</p>;

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-5" noValidate>
      {/* A fieldset is as wide as its content at least: `min-w-0` lets it shrink on a phone. */}
      <fieldset disabled={save.isPending} className="grid min-w-0 grid-cols-1 gap-5">
        <Field label={text.name} errors={errors("name")} help={text.nameHelp}>
          {(control) => (
            <input
              {...control}
              {...(income ? {} : autofocus)}
              name="name"
              defaultValue={income?.name ?? ""}
              maxLength={150}
              className="field"
            />
          )}
        </Field>
        <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
          <Field label={text.account} errors={errors("account_id")}>
            {(control) => (
              <Select
                {...control}
                value={account}
                onChange={setAccount}
                options={accounts.map((item) => ({
                  value: String(item.id),
                  label: `${item.bank} · ${item.name}`,
                  hint: item.currency,
                }))}
              />
            )}
          </Field>
          <CategoryChoice value={category} onChange={setCategory} errors={errors("category_id")} />
        </div>

        <div className="grid gap-3">
          <div>
            <p className="text-sm font-medium">{text.parts}</p>
            <p className="text-sm text-muted">{text.partsHelp}</p>
          </div>
          <ul className="grid gap-3">
            {parts.map((part, index) => (
              <li key={part.key} className="flex flex-wrap items-end gap-3">
                <Field label={text.day} className="w-20">
                  {(control) => (
                    <input
                      {...control}
                      type="number"
                      min={1}
                      max={31}
                      inputMode="numeric"
                      value={part.day}
                      onChange={(event) => setPart(part.key, { day: event.target.value })}
                      className="field amount"
                    />
                  )}
                </Field>
                <Field label={`${text.amount} (${currency})`} className="min-w-0 flex-1 basis-24">
                  {(control) => (
                    <AmountInput
                      {...control}
                      currency={currency}
                      value={part.amount}
                      onChange={(amount) => setPart(part.key, { amount })}
                      className="field amount"
                    />
                  )}
                </Field>
                {part.id !== undefined && (
                  <OpenWindow w={`schedule:${part.id}`} className="action mb-1">
                    {text.schedule}
                  </OpenWindow>
                )}
                {parts.length > 1 && (
                  <button
                    type="button"
                    className="action mb-1 px-2"
                    aria-label={text.removePart(index + 1)}
                    title={text.removePart(index + 1)}
                    onClick={() => setParts(parts.filter((other) => other.key !== part.key))}
                  >
                    <CloseIcon />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <Alert message={errors("parts").join(" ") || undefined} />
          <div className="flex flex-wrap gap-2">
            {parts.length < MAX_PARTS && (
              <button type="button" className="action" onClick={addPart}>
                <PlusIcon />
                {text.addPart}
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="button" className="chip" aria-pressed={clt} onClick={() => setClt(!clt)}>
            {text.clt}
          </button>
          <button
            type="button"
            className="chip"
            aria-pressed={confirm}
            onClick={() => setConfirm(!confirm)}
          >
            {text.confirm}
          </button>
        </div>
        {confirm && <p className="-mt-2 text-sm text-muted">{text.confirmHelp}</p>}
        {clt && (
          <div className="grid gap-4 rounded-(--radius-control) bg-sheet p-4">
            <p className="text-sm text-muted">{text.cltHelp}</p>
            <div className="flex flex-wrap items-end gap-4">
              <Field
                label={`${t.plan.tools.gross} (BRL)`}
                errors={splitErrors("gross")}
                className="w-44"
              >
                {(control) => (
                  <AmountInput
                    {...control}
                    currency="BRL"
                    name="gross"
                    defaultValue={income?.gross ? editableAmount(income.gross, "BRL") : ""}
                    className="field amount"
                  />
                )}
              </Field>
              <Field
                label={text.advancePercent}
                errors={splitErrors("advance_percent")}
                className="w-36"
              >
                {(control) => (
                  <input
                    {...control}
                    name="advance_percent"
                    inputMode="decimal"
                    defaultValue={income?.advance_percent ? Number(income.advance_percent) : 40}
                    className="field amount"
                  />
                )}
              </Field>
              <Field label={text.advanceDay} errors={splitErrors("advance_day")} className="w-32">
                {(control) => (
                  <input
                    {...control}
                    name="advance_day"
                    type="number"
                    min={1}
                    max={31}
                    defaultValue={20}
                    className="field amount"
                  />
                )}
              </Field>
              <Field label={text.restDay} errors={splitErrors("rest_day")} className="w-32">
                {(control) => (
                  <input
                    {...control}
                    name="rest_day"
                    type="number"
                    min={1}
                    max={31}
                    defaultValue={5}
                    className="field amount"
                  />
                )}
              </Field>
              <Field
                label={t.plan.tools.dependents}
                errors={splitErrors("dependents")}
                className="w-32"
              >
                {(control) => (
                  <input
                    {...control}
                    name="dependents"
                    type="number"
                    min={0}
                    max={30}
                    defaultValue={0}
                    className="field amount"
                  />
                )}
              </Field>
              <Field
                label={`${t.plan.tools.other} (BRL)`}
                errors={splitErrors("other")}
                className="w-44"
              >
                {(control) => (
                  <AmountInput {...control} currency="BRL" name="other" className="field amount" />
                )}
              </Field>
            </div>
            <Alert message={formMessage(split.error, t)} />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <button
                type="button"
                className="button-quiet"
                disabled={split.isPending}
                onClick={(event) => event.currentTarget.form && calculate(event.currentTarget.form)}
              >
                {text.calculate}
              </button>
              {split.data && (
                <p className="text-sm text-muted" aria-live="polite">
                  {text.calculated(
                    formatAmount(split.data.net, "BRL"),
                    formatAmount(split.data.inss, "BRL"),
                    formatAmount(split.data.irrf, "BRL"),
                    split.data.year,
                  )}
                  {split.data.assumed && ` ${t.plan.tools.assumed(split.data.year)}`}
                </p>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
          {!income && (
            <Field label={text.start} help={text.startHelp}>
              {(control) => (
                <MonthField {...control} name="start" defaultValue={todayIso().slice(0, 7)} />
              )}
            </Field>
          )}
          <Field label={t.entry.until} errors={errors("until")} help={t.entry.untilHelp}>
            {(control) => (
              <MonthField
                {...control}
                name="until"
                defaultValue={income?.until?.slice(0, 7) ?? ""}
                empty={t.entry.noEnd}
              />
            )}
          </Field>
        </div>
        <p className="text-sm text-muted">{income ? text.changeHelp : text.createHelp}</p>
      </fieldset>
      <Alert message={formMessage(save.error, t)} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        {income ? <DeleteIncome id={income.id} onDone={props.onDone} /> : <span />}
        <button type="submit" className="button-primary" disabled={save.isPending}>
          {t.common.save}
        </button>
      </div>
    </form>
  );
}

/**
 * The category of an income: one of the income categories or of those
 * without a type. A new income category is created here, with its name, and
 * becomes the choice. Without any category to list, the field says so and
 * the name is asked at once.
 */
function CategoryChoice(props: {
  value: string;
  onChange: (value: string) => void;
  errors: string[];
}) {
  const t = useMessages();
  const text = t.plan.incomes;
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const create = useSaveCategory();
  const choices = categories.filter((item) => item.transaction_type !== "EXPENSE");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const open = adding || choices.length === 0;

  function add() {
    create.mutate(
      { name, transaction_type: "INCOME", parent_id: null },
      {
        onSuccess: (created) => {
          props.onChange(String(created.id));
          setName("");
          setAdding(false);
        },
      },
    );
  }

  return (
    <div className="grid min-w-0 content-start gap-2">
      {choices.length === 0 ? (
        <div className="grid gap-1.5">
          <p className="text-sm font-medium">{text.category}</p>
          <p className="text-sm text-muted">{text.noCategory}</p>
          {props.errors.length > 0 && (
            <p className="text-sm text-negative">{props.errors.join(" ")}</p>
          )}
        </div>
      ) : (
        <Field label={text.category} errors={props.errors} help={text.categoryHelp}>
          {(control) => (
            <Select
              {...control}
              value={props.value}
              onChange={props.onChange}
              placeholder={t.common.choose}
              options={categoryChoices(choices, categories)}
            />
          )}
        </Field>
      )}
      {open ? (
        <div className="grid gap-2 rounded-(--radius-control) bg-sheet p-3">
          <div className="flex flex-wrap items-end gap-2">
            <Field label={text.categoryName} className="min-w-0 flex-1 basis-32">
              {(control) => (
                <input
                  {...control}
                  {...(adding ? autofocus : {})}
                  value={name}
                  maxLength={100}
                  onChange={(event) => setName(event.target.value)}
                  // Enter creates the category; it does not save the income.
                  onKeyDown={(event) => {
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    add();
                  }}
                  className="field"
                />
              )}
            </Field>
            <button
              type="button"
              className="button-quiet"
              disabled={create.isPending || name.trim() === ""}
              onClick={add}
            >
              {text.createCategory}
            </button>
            {choices.length > 0 && (
              <button
                type="button"
                className="action mb-1"
                onClick={() => {
                  setAdding(false);
                  create.reset();
                }}
              >
                {t.common.cancel}
              </button>
            )}
          </div>
          <Alert message={formMessage(create.error, t) ?? fieldMessages(create.error, "name")[0]} />
        </div>
      ) : (
        <button type="button" className="action w-fit" onClick={() => setAdding(true)}>
          <PlusIcon />
          {text.newCategory}
        </button>
      )}
    </div>
  );
}

function DeleteIncome(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const remove = useDeleteIncome(props.id);
  return (
    <span className="grid gap-1">
      <span>
        <ConfirmButton
          label={t.common.delete}
          pending={remove.isPending}
          onConfirm={() => remove.mutate(undefined, { onSuccess: props.onDone })}
        />
      </span>
      <span className="max-w-xs text-sm text-muted">{t.plan.incomes.deleteHelp}</span>
    </span>
  );
}
