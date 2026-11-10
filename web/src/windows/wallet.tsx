import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { type Instrument, instrumentsQuery, useCreateAccount } from "../data/ledger";
import {
  accountQuery,
  cardQuery,
  invoiceQuery,
  useChangeAccount,
  useChangeCreditCard,
  useCreateCreditCard,
  useCreateDebitCard,
  useDeleteAccount,
  useDeleteCreditCard,
  usePayInvoice,
  useTransfer,
  useUndoPayment,
  useUndoTransfer,
} from "../data/wallet";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, monthLabel, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, formatAmount, parseAmount } from "../lib/money";
import { StatusLabel } from "../routes/wallet";
import { sessionQuery, useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { autofocus } from "../ui/Window";
import { OpenWindow } from "./host";
import { CURRENCIES } from "./settings";

type Currency = (typeof CURRENCIES)[number];

export function values(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
}

/** Read a typed balance, which may be zero or negative. Null when it is not a number. */
export function parseBalance(text: string, currency: string): string | null {
  const typed = text.trim();
  if (typed === "" || /^-?0+([.,]0*)?$/.test(typed)) return "0";
  const negative = typed.startsWith("-");
  const parsed = parseAmount(typed.replace(/^-/, ""), currency);
  return parsed === null ? null : `${negative ? "-" : ""}${parsed}`;
}

export function Alert(props: { message?: string }) {
  if (!props.message) return null;
  return (
    <p role="alert" className="text-sm text-negative">
      {props.message}
    </p>
  );
}

/** A button that asks before it acts: the first press asks, the second one acts. */
export function ConfirmButton(props: { label: string; pending: boolean; onConfirm: () => void }) {
  const t = useMessages();
  const [asked, setAsked] = useState(false);
  return (
    <button
      type="button"
      className={asked ? "button-danger" : "button-quiet"}
      disabled={props.pending}
      onClick={() => (asked ? props.onConfirm() : setAsked(true))}
      onBlur={() => setAsked(false)}
    >
      {asked ? t.common.confirmDelete : props.label}
    </button>
  );
}

// Accounts

function AccountFields(props: {
  error: unknown;
  bank?: string;
  name?: string;
  balance?: string;
  openingDate?: string | null;
  balanceInvalid: boolean;
  withDate?: boolean;
  currency: string;
  /** Given for a new account only: the currency of an account does not change. */
  onCurrency?: (currency: Currency) => void;
}) {
  const t = useMessages();
  return (
    <>
      <Field label={t.firstAccount.bank}>
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="bank"
            className="field"
            defaultValue={props.bank}
            placeholder={t.firstAccount.bankPlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <Field label={t.firstAccount.name} errors={fieldMessages(props.error, "name")}>
        {(control) => (
          <input
            {...control}
            name="name"
            className="field"
            defaultValue={props.name}
            autoComplete="off"
          />
        )}
      </Field>
      <div className="flex flex-wrap gap-5">
        {props.onCurrency && (
          <Field label={t.wallet.currency}>
            {(control) => (
              <select
                {...control}
                className="field"
                value={props.currency}
                onChange={(event) => props.onCurrency?.(event.target.value as Currency)}
              >
                {CURRENCIES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        <Field
          label={`${t.wallet.openingBalance} (${props.currency})`}
          errors={
            props.balanceInvalid
              ? [t.entry.amountInvalid]
              : fieldMessages(props.error, "opening_balance")
          }
          className="w-48"
        >
          {(control) => (
            <input
              {...control}
              name="balance"
              inputMode="decimal"
              className="field amount"
              defaultValue={props.balance}
              autoComplete="off"
            />
          )}
        </Field>
        {props.withDate && (
          <Field
            label={t.wallet.openingDate}
            help={t.wallet.openingDateHelp}
            errors={fieldMessages(props.error, "opening_date")}
          >
            {(control) => (
              <input
                {...control}
                type="date"
                name="opening_date"
                className="field w-fit"
                defaultValue={props.openingDate ?? ""}
              />
            )}
          </Field>
        )}
      </div>
    </>
  );
}

export function NewAccountWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const create = useCreateAccount();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const [currency, setCurrency] = useState<Currency>(session.preferences?.base_currency ?? "BRL");
  const [balanceInvalid, setBalanceInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const balance = parseBalance(typed.balance ?? "", currency);
    setBalanceInvalid(balance === null);
    if (balance === null) return;
    create.mutate(
      {
        bank_name: typed.bank ?? "",
        name: typed.name ?? "",
        currency,
        opening_balance: balance,
        opening_date: null,
      },
      { onSuccess: props.onDone },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <AccountFields
        error={create.error}
        balanceInvalid={balanceInvalid}
        currency={currency}
        onCurrency={setCurrency}
      />
      <Alert message={formMessage(create.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={create.isPending}>
        {t.firstAccount.create}
      </button>
    </form>
  );
}

export function AccountWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const order = useDateOrder();
  const { data: account } = useSuspenseQuery(accountQuery(props.id));
  const change = useChangeAccount(props.id);
  const remove = useDeleteAccount(props.id);
  const undo = useUndoTransfer();
  const [balanceInvalid, setBalanceInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const balance = parseBalance(typed.balance ?? "", account.currency);
    setBalanceInvalid(balance === null);
    if (balance === null) return;
    change.mutate({
      bank_name: typed.bank ?? "",
      name: typed.name ?? "",
      opening_balance: balance,
      opening_date: typed.opening_date || null,
    });
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <div>
        <p className="text-sm text-muted">
          {account.bank_name} · {account.name}
        </p>
        <p
          className={`amount text-3xl font-semibold ${Number(account.balance) < 0 ? "text-negative" : ""}`}
        >
          {formatAmount(account.balance, account.currency)}
        </p>
      </div>

      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
          {t.wallet.movements}
        </h3>
        {account.movements.length === 0 && (
          <p className="py-4 text-muted">{t.wallet.noMovements}</p>
        )}
        <ul className="divide-y divide-line">
          {account.movements.map((row) => (
            <li key={row.id} className="flex items-center gap-3 py-2.5">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{row.label || t.wallet.transferDone}</span>
                <span className="block text-sm text-muted">{formatDate(row.date, order)}</span>
              </span>
              {row.transfer_id != null && (
                <button
                  type="button"
                  className="action"
                  disabled={undo.isPending}
                  onClick={() => undo.mutate(row.transfer_id as number)}
                >
                  {t.wallet.undo}
                </button>
              )}
              <span
                className={`amount font-semibold ${row.direction === "CREDIT" ? "text-positive" : ""}`}
              >
                {row.direction === "CREDIT" ? "+" : "−"}
                {formatAmount(row.amount, account.currency)}
              </span>
            </li>
          ))}
        </ul>
        <Alert message={formMessage(undo.error, t)} />
      </section>

      <details>
        <summary className="action w-fit">{t.wallet.editAccount}</summary>
        <form onSubmit={submit} className="mt-4 grid gap-5" noValidate>
          <AccountFields
            error={change.error}
            bank={account.bank_name}
            name={account.name}
            balance={editableAmount(account.opening_balance, account.currency)}
            openingDate={account.opening_date}
            balanceInvalid={balanceInvalid}
            currency={account.currency}
            withDate
          />
          <Alert message={formMessage(change.error, t) ?? formMessage(remove.error, t)} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ConfirmButton
              label={t.common.delete}
              pending={remove.isPending}
              onConfirm={() => remove.mutate(undefined, { onSuccess: props.onDone })}
            />
            <button type="submit" className="button-primary" disabled={change.isPending}>
              {t.common.save}
            </button>
          </div>
        </form>
      </details>
    </div>
  );
}

// Cards

function CardFields(props: {
  error: unknown;
  name?: string;
  closingDay?: number;
  dueDay?: number;
  confirm?: boolean;
  credit: boolean;
  focusName?: boolean;
}) {
  const t = useMessages();
  return (
    <>
      <Field label={t.wallet.cardName} errors={fieldMessages(props.error, "name")}>
        {(control) => (
          <input
            {...control}
            {...(props.focusName ? autofocus : {})}
            name="name"
            className="field"
            defaultValue={props.name}
            autoComplete="off"
          />
        )}
      </Field>
      {props.credit && (
        <>
          <div className="flex flex-wrap gap-5">
            <Field
              label={t.wallet.closingDay}
              errors={fieldMessages(props.error, "closing_day")}
              className="w-36"
            >
              {(control) => (
                <input
                  {...control}
                  type="number"
                  min={1}
                  max={31}
                  name="closing_day"
                  className="field"
                  defaultValue={props.closingDay}
                />
              )}
            </Field>
            <Field
              label={t.wallet.dueDay}
              errors={fieldMessages(props.error, "due_day")}
              className="w-36"
            >
              {(control) => (
                <input
                  {...control}
                  type="number"
                  min={1}
                  max={31}
                  name="due_day"
                  className="field"
                  defaultValue={props.dueDay}
                />
              )}
            </Field>
          </div>
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              name="confirm"
              defaultChecked={props.confirm}
              className="mt-1 size-4"
            />
            <span>
              <span className="block font-medium">{t.wallet.confirmPayments}</span>
              <span className="block text-sm text-muted">{t.wallet.confirmPaymentsHelp}</span>
            </span>
          </label>
        </>
      )}
    </>
  );
}

export function AccountSelect(props: {
  label: string;
  name: string;
  accounts: Instrument[];
  errors?: string[];
  defaultValue?: string;
}) {
  return (
    <Field label={props.label} errors={props.errors}>
      {(control) => (
        <select {...control} name={props.name} className="field" defaultValue={props.defaultValue}>
          {props.accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.bank_name} · {account.name}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function NewCardWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const accounts = instruments.filter((item) => item.kind === "account");
  const createCredit = useCreateCreditCard();
  const createDebit = useCreateDebitCard();
  const [kind, setKind] = useState<"credit" | "debit">("credit");
  const active = kind === "credit" ? createCredit : createDebit;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const base = { account: typed.account ?? "", name: typed.name ?? "" };
    if (kind === "debit") {
      createDebit.mutate(base, { onSuccess: props.onDone });
    } else {
      createCredit.mutate(
        {
          ...base,
          closing_day: Number(typed.closing_day) || 0,
          due_day: Number(typed.due_day) || 0,
          confirm_payments: typed.confirm === "on",
        },
        { onSuccess: props.onDone },
      );
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <Segmented
        label={t.wallet.cardKind}
        value={kind}
        onChange={setKind}
        options={[
          { value: "credit", label: t.wallet.credit },
          { value: "debit", label: t.wallet.debit },
        ]}
      />
      <AccountSelect
        label={t.wallet.account}
        name="account"
        accounts={accounts}
        errors={fieldMessages(active.error, "account")}
      />
      <CardFields error={active.error} credit={kind === "credit"} confirm focusName />
      <Alert message={formMessage(active.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={active.isPending}>
        {t.common.add}
      </button>
    </form>
  );
}

export function CardWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const order = useDateOrder();
  const language = useLanguage();
  const { data: card } = useSuspenseQuery(cardQuery(props.id));
  const change = useChangeCreditCard(props.id);
  const remove = useDeleteCreditCard(props.id);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    change.mutate({
      name: typed.name ?? "",
      closing_day: Number(typed.closing_day) || 0,
      due_day: Number(typed.due_day) || 0,
      confirm_payments: typed.confirm === "on",
    });
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
          {t.wallet.invoices}
        </h3>
        {card.invoices.length === 0 && <p className="py-4 text-muted">{t.wallet.noInvoices}</p>}
        <ul className="divide-y divide-line">
          {card.invoices.map((invoice) => (
            <li key={invoice.id}>
              <OpenWindow
                w={`invoice:${invoice.id}`}
                className="-mx-2 flex items-center gap-3 rounded-(--radius-control) px-2 py-2.5 hover:bg-sheet"
              >
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">
                    {monthLabel(invoice.reference_month.slice(0, 7), language)}
                  </span>
                  <span className="block text-sm text-muted">
                    {t.wallet.due(formatDate(invoice.due_date, order))}
                  </span>
                </span>
                <span className="text-right">
                  <span className="amount block font-semibold">
                    {formatAmount(invoice.amount, card.currency)}
                  </span>
                  <span className="block text-sm">
                    <StatusLabel invoice={invoice} t={t} />
                  </span>
                </span>
              </OpenWindow>
            </li>
          ))}
        </ul>
      </section>

      <details>
        <summary className="action w-fit">{t.wallet.editCard}</summary>
        <form onSubmit={submit} className="mt-4 grid gap-5" noValidate>
          <CardFields
            error={change.error}
            name={card.name}
            closingDay={card.closing_day}
            dueDay={card.due_day}
            confirm={card.confirm_payments}
            credit
          />
          <Alert message={formMessage(change.error, t) ?? formMessage(remove.error, t)} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ConfirmButton
              label={t.common.delete}
              pending={remove.isPending}
              onConfirm={() => remove.mutate(undefined, { onSuccess: props.onDone })}
            />
            <button type="submit" className="button-primary" disabled={change.isPending}>
              {t.common.save}
            </button>
          </div>
        </form>
      </details>
    </div>
  );
}

// Invoices

export function InvoiceWindow(props: { id: number }) {
  const t = useMessages();
  const order = useDateOrder();
  const language = useLanguage();
  const { data: invoice } = useSuspenseQuery(invoiceQuery(props.id));
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const accounts = instruments.filter(
    (item) => item.kind === "account" && item.currency === invoice.currency,
  );
  const pay = usePayInvoice(props.id);
  const undo = useUndoPayment();
  const [amountInvalid, setAmountInvalid] = useState(false);
  // One key for each payment form: a repeated request records one payment.
  const [key, setKey] = useState(() => crypto.randomUUID());
  const money = (amount: string) => formatAmount(amount, invoice.currency);
  const open = invoice.confirm_payments && Number(invoice.remaining) > 0;

  function submit(event: FormEvent<HTMLFormElement>) {
    const form = event.currentTarget;
    const typed = values(event);
    const amount = parseAmount(typed.amount ?? "", invoice.currency);
    setAmountInvalid(amount === null);
    if (amount === null) return;
    pay.mutate(
      {
        account_id: Number((typed.account ?? "").split(":")[1]),
        amount,
        date: typed.date || null,
        confirmation_key: key,
      },
      {
        onSuccess: () => {
          setKey(crypto.randomUUID());
          form.reset();
        },
      },
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">
            {invoice.card_name} · {monthLabel(invoice.reference_month.slice(0, 7), language)}
          </p>
          <p className="amount text-3xl font-semibold">{money(invoice.amount)}</p>
        </div>
        <p className="text-right text-sm">
          <span className="block text-muted">
            {t.wallet.due(formatDate(invoice.due_date, order))}
          </span>
          <StatusLabel invoice={invoice} t={t} />
        </p>
      </div>

      {invoice.confirm_payments ? (
        <dl className="flex flex-wrap gap-x-10 gap-y-2">
          <div>
            <dt className="text-sm text-muted">{t.wallet.paidAmount}</dt>
            <dd className="amount font-semibold">{money(invoice.confirmed_amount)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted">{t.wallet.remaining}</dt>
            <dd className="amount font-semibold">{money(invoice.remaining)}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted">{t.wallet.automatic}</p>
      )}

      {open && (
        <form
          onSubmit={submit}
          className="grid gap-4 rounded-(--radius-control) bg-sheet p-4"
          noValidate
        >
          <div className="flex flex-wrap items-end gap-4">
            <Field
              label={`${t.entry.amount} (${invoice.currency})`}
              errors={amountInvalid ? [t.entry.amountInvalid] : fieldMessages(pay.error, "amount")}
              className="w-40"
            >
              {(control) => (
                <input
                  {...control}
                  name="amount"
                  inputMode="decimal"
                  className="field amount"
                  defaultValue={editableAmount(invoice.remaining, invoice.currency)}
                  autoComplete="off"
                />
              )}
            </Field>
            <div className="min-w-48 flex-1">
              <AccountSelect
                label={t.wallet.payFrom}
                name="account"
                accounts={accounts}
                errors={fieldMessages(pay.error, "account_id")}
                defaultValue={`account:${invoice.account_id}`}
              />
            </div>
            <Field label={t.entry.date} errors={fieldMessages(pay.error, "date")}>
              {(control) => (
                <input
                  {...control}
                  type="date"
                  name="date"
                  className="field"
                  defaultValue={todayIso()}
                  max={todayIso()}
                />
              )}
            </Field>
          </div>
          <Alert message={formMessage(pay.error, t) ?? fieldMessages(pay.error, "invoice")[0]} />
          <button type="submit" className="button-primary w-fit" disabled={pay.isPending}>
            {t.wallet.pay}
          </button>
        </form>
      )}

      {invoice.payments.length > 0 && (
        <section>
          <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
            {t.wallet.payments}
          </h3>
          <ul className="divide-y divide-line">
            {invoice.payments.map((payment) => (
              <li key={payment.id} className="flex items-center gap-3 py-2.5">
                <span className="flex-1">{formatDate(payment.date, order)}</span>
                <button
                  type="button"
                  className="action"
                  disabled={undo.isPending}
                  onClick={() => undo.mutate(payment.id)}
                >
                  {t.wallet.undo}
                </button>
                <span className="amount font-semibold">{money(payment.amount)}</span>
              </li>
            ))}
          </ul>
          <Alert message={formMessage(undo.error, t)} />
        </section>
      )}

      <section>
        <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
          {t.wallet.purchases}
        </h3>
        <ul className="divide-y divide-line">
          {invoice.lines.map((line) => (
            <li key={line.transaction_id}>
              <OpenWindow
                w={`transaction:${line.transaction_id}`}
                className="-mx-2 flex items-center gap-3 rounded-(--radius-control) px-2 py-2.5 hover:bg-sheet"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{line.title}</span>
                  <span className="block text-sm text-muted">
                    {formatDate(line.date, order)} · {line.category}
                    {line.installments > 1 && ` · ${t.transactions.installment(line.installments)}`}
                  </span>
                </span>
                <span className="amount font-semibold">{money(line.amount)}</span>
              </OpenWindow>
            </li>
          ))}
        </ul>
        {Number(invoice.credits_amount) > 0 && (
          <p className="flex justify-between border-t border-line py-2.5">
            <span>{t.wallet.credits}</span>
            <span className="amount font-semibold text-positive">
              −{money(invoice.credits_amount)}
            </span>
          </p>
        )}
      </section>
    </div>
  );
}

// Transfers

export function TransferWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const accounts = instruments.filter((item) => item.kind === "account");
  const transfer = useTransfer();
  const [amountInvalid, setAmountInvalid] = useState(false);
  const [receivedInvalid, setReceivedInvalid] = useState(false);
  // The chosen accounts. Two currencies need the amount that arrives.
  const [pair, setPair] = useState([accounts[0]?.id, accounts[1]?.id]);
  const currencyOf = (id: string | undefined) =>
    accounts.find((item) => item.id === id)?.currency ?? "BRL";
  const sent = currencyOf(pair[0]);
  const received = currencyOf(pair[1]);
  const exchange = sent !== received;

  if (accounts.length < 2) return <p className="text-muted">{t.wallet.needTwoAccounts}</p>;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const amount = parseAmount(typed.amount ?? "", sent);
    const arrives = exchange ? parseAmount(typed.received ?? "", received) : null;
    setAmountInvalid(amount === null);
    setReceivedInvalid(exchange && arrives === null);
    if (amount === null || (exchange && arrives === null)) return;
    transfer.mutate(
      {
        source_account_id: Number((typed.source ?? "").split(":")[1]),
        destination_account_id: Number((typed.destination ?? "").split(":")[1]),
        amount,
        destination_amount: arrives,
        date: typed.date || null,
        notes: "",
      },
      { onSuccess: props.onDone },
    );
  }

  return (
    <form
      onSubmit={submit}
      onChange={(event) => {
        const chosen = new FormData(event.currentTarget);
        setPair([String(chosen.get("source")), String(chosen.get("destination"))]);
      }}
      className="grid gap-5"
      noValidate
    >
      <Field
        label={exchange ? `${t.entry.amount} (${sent})` : t.entry.amount}
        errors={amountInvalid ? [t.entry.amountInvalid] : fieldMessages(transfer.error, "amount")}
      >
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="amount"
            inputMode="decimal"
            className="field amount text-2xl font-semibold"
            autoComplete="off"
          />
        )}
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <AccountSelect
          label={t.wallet.from}
          name="source"
          accounts={accounts}
          errors={fieldMessages(transfer.error, "source_account_id")}
          defaultValue={accounts[0]?.id}
        />
        <AccountSelect
          label={t.wallet.to}
          name="destination"
          accounts={accounts}
          errors={fieldMessages(transfer.error, "destination_account_id")}
          defaultValue={accounts[1]?.id}
        />
      </div>
      {exchange && (
        <Field
          label={t.wallet.received(received)}
          help={t.wallet.receivedHelp}
          errors={
            receivedInvalid
              ? [t.entry.amountInvalid]
              : fieldMessages(transfer.error, "destination_amount")
          }
          className="w-56"
        >
          {(control) => (
            <input
              {...control}
              name="received"
              inputMode="decimal"
              className="field amount"
              autoComplete="off"
            />
          )}
        </Field>
      )}
      <Field label={t.entry.date} errors={fieldMessages(transfer.error, "date")} className="w-fit">
        {(control) => (
          <input {...control} type="date" name="date" className="field" defaultValue={todayIso()} />
        )}
      </Field>
      <Alert message={formMessage(transfer.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={transfer.isPending}>
        {t.wallet.transfer}
      </button>
    </form>
  );
}
