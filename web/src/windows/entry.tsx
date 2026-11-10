import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
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
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { autofocus } from "../ui/Window";

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
    const parsed = parseAmount(amount, currency);
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
        installments: isCredit && kind === "EXPENSE" ? installments : 1,
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
      {locked && (
        <p className="rounded-(--radius-control) bg-sheet p-3 text-sm">{t.entry.locked}</p>
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
            <input
              {...control}
              {...autofocus}
              inputMode="decimal"
              autoComplete="off"
              className="field amount text-2xl font-semibold"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
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
              <select
                {...control}
                className="field"
                value={instrument}
                onChange={(event) => {
                  touched.current.instrument = true;
                  setInstrument(event.target.value);
                }}
              >
                <InstrumentOptions instruments={usable} />
              </select>
            )}
          </Field>
          <Field label={t.entry.category} errors={fieldMessages(error, "category_id")}>
            {(control) => (
              <select
                {...control}
                className="field"
                value={category}
                onChange={(event) => {
                  touched.current.category = true;
                  setCategory(event.target.value);
                }}
              >
                <option value="">{t.entry.chooseCategory}</option>
                {choices.map((item) => (
                  <option key={item.id} value={item.id}>
                    {categoryLabel(item, categories)}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
        <Field label={t.entry.date} errors={fieldMessages(error, "date")} className="w-fit">
          {(control) => (
            <input
              {...control}
              type="date"
              className="field"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          )}
        </Field>
        <details className="group" open={installments > 1 || notes !== "" || undefined}>
          <summary className="link w-fit cursor-pointer text-sm">{t.entry.more}</summary>
          <div className="mt-4 grid gap-5">
            {isCredit && kind === "EXPENSE" && (
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
                    min={1}
                    max={48}
                    className="field"
                    value={installments}
                    onChange={(event) =>
                      setInstallments(Math.max(1, Number(event.target.value) || 1))
                    }
                  />
                )}
              </Field>
            )}
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
          </div>
        </details>
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

function InstrumentOptions(props: { instruments: Instrument[] }) {
  const t = useMessages();
  const groups: [Instrument["kind"], string][] = [
    ["account", t.entry.accounts],
    ["debit", t.entry.debitCards],
    ["credit", t.entry.creditCards],
  ];
  return groups.map(([kind, label]) => {
    const items = props.instruments.filter((item) => item.kind === kind);
    if (items.length === 0) return null;
    return (
      <optgroup key={kind} label={label}>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {instrumentLabel(item)}
          </option>
        ))}
      </optgroup>
    );
  });
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
          <input
            {...control}
            name="balance"
            inputMode="decimal"
            className="field amount"
            autoComplete="off"
          />
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
