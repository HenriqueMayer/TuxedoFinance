import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import {
  type Category,
  categoriesQuery,
  type Instrument,
  instrumentsQuery,
  suggestion,
  type Transaction,
  transactionQuery,
  useCreateAccount,
  useDeleteTransaction,
  useSaveTransaction,
} from "../data/ledger";
import { useMessages } from "../i18n";
import { todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, parseAmount } from "../lib/money";
import { AmountInput } from "../ui/AmountInput";
import { DateField, MonthField } from "../ui/DateField";
import { Field } from "../ui/Field";
import { NoteIcon, RepeatIcon, SplitIcon } from "../ui/icons";
import { OptionChip } from "../ui/OptionChip";
import { Segmented } from "../ui/Segmented";
import { type Choice, Select } from "../ui/Select";
import { autofocus } from "../ui/Window";
import { OpenWindow } from "./host";

type Kind = "EXPENSE" | "INCOME";

/** The window that records a new entry. With no account yet, it first creates one. */
export function AddEntry(props: { onDone: () => void }) {
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  if (instruments.length === 0) return <FirstAccount />;
  return <EntryForm instruments={instruments} onDone={props.onDone} />;
}

/** The window that changes or deletes one entry. */
export function EditEntry(props: { id: number; onDone: () => void }) {
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const { data: entry } = useSuspenseQuery(transactionQuery(props.id));
  return <EntryForm instruments={instruments} entry={entry} onDone={props.onDone} />;
}

function EntryForm(props: { instruments: Instrument[]; entry?: Transaction; onDone: () => void }) {
  const t = useMessages();
  const { entry, instruments } = props;
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const save = useSaveTransaction(entry?.id);

  const [kind, setKind] = useState<Kind>(entry?.transaction_type ?? "EXPENSE");
  const [instrument, setInstrument] = useState(entry?.instrument.id ?? instruments[0]?.id ?? "");
  const currency = instruments.find((item) => item.id === instrument)?.currency ?? "BRL";
  const [amount, setAmount] = useState(entry ? editableAmount(entry.amount, currency) : "");
  const [title, setTitle] = useState(entry?.title ?? "");
  const [category, setCategory] = useState(entry ? String(entry.category.id) : "");
  const [date, setDate] = useState(entry?.date ?? todayIso());
  const [installments, setInstallments] = useState(entry?.installments ?? 1);
  const [notes, setNotes] = useState(entry?.notes ?? "");
  const [repeats, setRepeats] = useState(entry?.is_fixed ?? false);
  const [until, setUntil] = useState(entry?.fixed_until?.slice(0, 7) ?? "");
  const [confirmEach, setConfirmEach] = useState(entry?.requires_confirmation ?? false);
  // The options that the owner turned on. Each one shows its field.
  const [split, setSplit] = useState((entry?.installments ?? 1) > 1);
  const [noted, setNoted] = useState(Boolean(entry?.notes));
  // The stored amount and date give every past month of a repeating entry,
  // so they change in the monthly schedule, not here.
  const pastMonths = Boolean(entry?.is_fixed && entry.date.slice(0, 7) < todayIso().slice(0, 7));
  const [amountError, setAmountError] = useState(false);
  // What the owner chose by hand is never replaced by a suggestion.
  const touched = useRef({ instrument: Boolean(entry), category: Boolean(entry) });

  // A new entry starts with the instrument that the owner used last.
  useEffect(() => {
    if (entry) return;
    let current = true;
    suggestion("")
      .then((suggested) => {
        if (current && suggested.instrument && !touched.current.instrument) {
          setInstrument(suggested.instrument);
        }
      })
      .catch(() => undefined); // A suggestion is optional; the form works without it.
    return () => {
      current = false;
    };
  }, [entry]);

  async function suggestFor(value: string) {
    if (entry || !value.trim()) return;
    try {
      const suggested = await suggestion(value);
      const known = categories.find((item) => item.id === suggested.category_id);
      if (known && !touched.current.category && allows(known, kind)) setCategory(String(known.id));
      if (suggested.instrument && !touched.current.instrument) setInstrument(suggested.instrument);
    } catch {
      // See above.
    }
  }

  const isCredit = instrument.startsWith("credit:");
  // A purchase on a credit card can be paid in monthly parts.
  const canSplit = isCredit && kind === "EXPENSE";
  const usable = instruments.filter((item) => kind === "EXPENSE" || item.kind === "account");
  const choices = categories.filter((item) => allows(item, kind));
  const locked = entry?.locked ?? false;

  function changeKind(next: Kind) {
    setKind(next);
    if (next === "INCOME" && !instrument.startsWith("account:")) {
      // Income is received in an account, never on a card.
      setInstrument(instruments.find((item) => item.kind === "account")?.id ?? "");
    }
    const chosen = categories.find((item) => String(item.id) === category);
    if (chosen && !allows(chosen, next)) setCategory("");
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = pastMonths && entry ? entry.amount : parseAmount(amount, currency);
    setAmountError(parsed === null);
    if (parsed === null) return;
    save.mutate(
      {
        transaction_type: kind,
        title,
        amount: parsed,
        date,
        category_id: Number(category) || 0,
        instrument,
        installments: canSplit && split && !repeats ? installments : 1,
        is_fixed: repeats,
        fixed_until: repeats && until ? `${until}-01` : null,
        requires_confirmation: repeats && confirmEach && !isCredit,
        notes,
      },
      { onSuccess: props.onDone },
    );
  }

  const error = save.error;
  const message = formMessage(error, t);
  const amountErrors = amountError ? [t.entry.amountInvalid] : fieldMessages(error, "amount");

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      {locked &&
        (entry?.recurring_income_id ? (
          <p className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-control) bg-sheet p-3 text-sm">
            <span>{t.plan.incomes.lockedEntry}</span>
            <OpenWindow w={`income:${entry.recurring_income_id}`} className="action">
              {t.plan.incomes.open}
            </OpenWindow>
          </p>
        ) : (
          <p className="rounded-(--radius-control) bg-sheet p-3 text-sm">{t.entry.locked}</p>
        ))}
      {entry?.is_fixed && (
        <p className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-control) bg-sheet p-3 text-sm">
          <span>{pastMonths ? t.entry.pastMonths : t.transactions.recurring}</span>
          <OpenWindow w={`schedule:${entry.id}`} className="action">
            {t.entry.schedule}
          </OpenWindow>
        </p>
      )}
      <fieldset disabled={locked || save.isPending} className="grid gap-5">
        <Segmented
          label={t.entry.type}
          value={kind}
          onChange={changeKind}
          options={[
            { value: "EXPENSE", label: t.entry.expense },
            { value: "INCOME", label: t.entry.income },
          ]}
        />
        <Field label={`${t.entry.amount} (${currency})`} errors={amountErrors}>
          {(control) => (
            <AmountInput
              currency={currency}
              {...control}
              {...autofocus}
              className="field amount text-2xl font-semibold disabled:opacity-60"
              value={amount}
              disabled={pastMonths}
              onChange={setAmount}
            />
          )}
        </Field>
        <Field label={t.entry.title} errors={fieldMessages(error, "title")}>
          {(control) => (
            <input
              {...control}
              className="field"
              autoComplete="off"
              maxLength={150}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              onBlur={(event) => suggestFor(event.target.value)}
            />
          )}
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label={t.entry.instrument} errors={fieldMessages(error, "instrument")}>
            {(control) => (
              <Select
                {...control}
                value={instrument}
                options={instrumentChoices(usable, t)}
                onChange={(value) => {
                  touched.current.instrument = true;
                  setInstrument(value);
                }}
              />
            )}
          </Field>
          <Field label={t.entry.category} errors={fieldMessages(error, "category_id")}>
            {(control) => (
              <Select
                {...control}
                value={category}
                placeholder={t.entry.chooseCategory}
                options={categoryChoices(choices, categories)}
                onChange={(value) => {
                  touched.current.category = true;
                  setCategory(value);
                }}
              />
            )}
          </Field>
        </div>
        <Field label={t.entry.date} errors={fieldMessages(error, "date")} className="w-48">
          {(control) => (
            <DateField {...control} value={date} disabled={pastMonths} onChange={setDate} />
          )}
        </Field>
        {/* The options of an entry are in view. Each one shows its field when it is on. */}
        <div className="grid">
          {/* biome-ignore lint/a11y/useSemanticElements: a row of toggle buttons with one name. */}
          <div role="group" aria-label={t.entry.more} className="flex flex-wrap gap-2">
            <button
              type="button"
              className="chip"
              aria-pressed={repeats}
              onClick={() => setRepeats(!repeats)}
            >
              <RepeatIcon />
              {t.entry.repeats}
            </button>
            {canSplit && (
              <button
                type="button"
                className="chip"
                aria-pressed={split && !repeats}
                disabled={repeats}
                onClick={() => {
                  setSplit(!split);
                  setInstallments(split ? 1 : Math.max(installments, 2));
                }}
              >
                <SplitIcon />
                {t.entry.split}
              </button>
            )}
            <button
              type="button"
              className="chip"
              aria-pressed={noted}
              onClick={() => {
                setNoted(!noted);
                if (noted) setNotes("");
              }}
            >
              <NoteIcon />
              {t.entry.notes}
            </button>
          </div>
          <Reveal open={repeats}>
            <div className="grid gap-4 rounded-(--radius-control) bg-sheet p-4">
              <Field
                label={t.entry.until}
                errors={fieldMessages(error, "fixed_until")}
                className="w-56"
              >
                {(control) => (
                  <MonthField
                    {...control}
                    value={until}
                    min={date.slice(0, 7)}
                    empty={t.entry.noEnd}
                    onChange={setUntil}
                  />
                )}
              </Field>
              {!isCredit && (
                <OptionChip
                  label={t.entry.confirmEach}
                  on={confirmEach}
                  onChange={setConfirmEach}
                  help={t.entry.confirmEachHelp}
                />
              )}
              {fieldMessages(error, "requires_confirmation").length > 0 && (
                <p role="alert" className="text-sm text-negative">
                  {fieldMessages(error, "requires_confirmation").join(" ")}
                </p>
              )}
            </div>
          </Reveal>
          <Reveal open={canSplit && split && !repeats}>
            <Field
              label={t.entry.installments}
              help={t.entry.installmentsHelp}
              errors={fieldMessages(error, "installments")}
              className="w-40"
            >
              {(control) => (
                <input
                  {...control}
                  type="number"
                  min={2}
                  max={48}
                  className="field"
                  value={installments}
                  onChange={(event) =>
                    setInstallments(Math.max(1, Number(event.target.value) || 1))
                  }
                />
              )}
            </Field>
          </Reveal>
          <Reveal open={noted}>
            <Field label={t.entry.notes} errors={fieldMessages(error, "notes")}>
              {(control) => (
                <textarea
                  {...control}
                  rows={2}
                  className="field"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              )}
            </Field>
          </Reveal>
        </div>
      </fieldset>
      {message && (
        <p role="alert" className="text-sm text-negative">
          {message}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
        {entry && !locked ? <DeleteEntry id={entry.id} onDone={props.onDone} /> : <span />}
        {!locked && (
          <button type="submit" className="button-accent" disabled={save.isPending}>
            {t.common.save}
          </button>
        )}
      </div>
    </form>
  );
}

/** Deleting needs two presses: the first one asks, the second one deletes. */
function DeleteEntry(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const remove = useDeleteTransaction(props.id);
  const [asked, setAsked] = useState(false);
  return (
    <button
      type="button"
      className={asked ? "button-danger" : "button-quiet"}
      disabled={remove.isPending}
      onClick={() =>
        asked ? remove.mutate(undefined, { onSuccess: props.onDone }) : setAsked(true)
      }
      onBlur={() => setAsked(false)}
    >
      {asked ? t.common.confirmDelete : t.common.delete}
    </button>
  );
}

/**
 * A field that an option of the form shows. It opens downward in a short
 * motion. While it is closed, the keyboard does not reach it.
 */
function Reveal(props: { open: boolean; children: ReactNode }) {
  return (
    <div className="reveal" data-open={props.open ? "" : undefined} inert={!props.open}>
      <div>
        <div className="pt-4">{props.children}</div>
      </div>
    </div>
  );
}

/** The accounts and the cards as the choices of a select, under their headings. */
export function instrumentChoices(
  instruments: Instrument[],
  t: ReturnType<typeof useMessages>,
): Choice[] {
  const headings: [Instrument["kind"], string][] = [
    ["account", t.entry.accounts],
    ["debit", t.entry.debitCards],
    ["credit", t.entry.creditCards],
  ];
  return headings.flatMap(([kind, group]) =>
    instruments
      .filter((item) => item.kind === kind)
      .map((item) => ({ value: item.id, label: instrumentLabel(item), group })),
  );
}

/** Categories as the choices of a select. `all` gives the parent of a subcategory. */
export function categoryChoices(categories: Category[], all: Category[]): Choice[] {
  // By the whole name, so that a subcategory follows its parent.
  return categories
    .map((item) => ({ value: String(item.id), label: categoryLabel(item, all) }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function instrumentLabel(item: Instrument): string {
  return item.kind === "account"
    ? `${item.bank_name} · ${item.name}`
    : `${item.name} · ${item.bank_name}`;
}

function allows(category: Category, kind: Kind): boolean {
  return category.transaction_type === null || category.transaction_type === kind;
}

export function categoryLabel(category: Category, all: Category[]): string {
  const parent = all.find((item) => item.id === category.parent_id);
  return parent ? `${parent.name} › ${category.name}` : category.name;
}

/** Shown in place of the entry form while the owner has no account. */
function FirstAccount() {
  const t = useMessages();
  const create = useCreateAccount();
  const [balanceError, setBalanceError] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const typed = (values.balance ?? "").trim();
    const balance = typed === "" || /^0+([.,]0*)?$/.test(typed) ? "0" : parseAmount(typed, "BRL");
    setBalanceError(balance === null);
    if (balance === null) return;
    // When the account exists, the instruments query refreshes and this
    // component is replaced by the entry form.
    create.mutate({
      bank_name: values.bank ?? "",
      name: values.name ?? "",
      currency: "BRL",
      opening_balance: balance,
      opening_date: null,
    });
  }

  const message = formMessage(create.error, t);
  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <div>
        <h3 className="text-lg font-semibold">{t.firstAccount.title}</h3>
        <p className="mt-1 text-sm text-muted">{t.firstAccount.help}</p>
      </div>
      <Field label={t.firstAccount.bank} errors={fieldMessages(create.error, "name")}>
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="bank"
            className="field"
            placeholder={t.firstAccount.bankPlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <Field label={t.firstAccount.name}>
        {(control) => (
          <input
            {...control}
            name="name"
            className="field"
            defaultValue={t.firstAccount.namePlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <Field
        label={`${t.firstAccount.balance} (BRL)`}
        errors={balanceError ? [t.entry.amountInvalid] : []}
        className="w-48"
      >
        {(control) => (
          <AmountInput currency={"BRL"} {...control} name="balance" className="field amount" />
        )}
      </Field>
      {message && (
        <p role="alert" className="text-sm text-negative">
          {message}
        </p>
      )}
      <button type="submit" className="button-accent w-fit" disabled={create.isPending}>
        {t.firstAccount.create}
      </button>
    </form>
  );
}
