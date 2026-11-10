import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { instrumentsQuery } from "../data/ledger";
import {
  type LoyaltyEntry,
  type ProgramDetail,
  programQuery,
  useDeleteProgram,
  useRecordPoints,
  useRedeem,
  useSaveProgram,
  useUndoPoints,
} from "../data/loyalty";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { formatAmount, formatQuantity, parseAmount, parseDecimal } from "../lib/money";
import { useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { autofocus } from "../ui/Window";
import { AccountSelect, Alert, ConfirmButton, values } from "./wallet";

function ProgramFields(props: { error: unknown; name?: string; unit?: string; first?: boolean }) {
  const t = useMessages();
  return (
    <div className="flex flex-wrap gap-4">
      <Field
        label={t.loyalty.name}
        errors={fieldMessages(props.error, "name")}
        className="min-w-0 flex-1 basis-56"
      >
        {(control) => (
          <input
            {...control}
            {...(props.first ? autofocus : {})}
            name="name"
            className="field"
            defaultValue={props.name}
            placeholder={t.loyalty.namePlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <Field label={t.loyalty.unit} className="w-40">
        {(control) => (
          <input
            {...control}
            name="unit"
            className="field"
            maxLength={30}
            defaultValue={props.unit ?? t.loyalty.defaultUnit}
            placeholder={t.loyalty.unitPlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
    </div>
  );
}

/** Create a program, then open it to record its points. */
export function NewProgramWindow() {
  const t = useMessages();
  const navigate = useNavigate();
  const create = useSaveProgram();

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    create.mutate(
      { name: typed.name ?? "", unit_name: typed.unit ?? "" },
      {
        // The new program takes the place of this window, so Back still closes it.
        onSuccess: (created) =>
          navigate({
            to: ".",
            search: (previous) => ({ ...previous, w: `program:${created.id}` }),
            replace: true,
            resetScroll: false,
            state: (state) => state,
          }),
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <ProgramFields error={create.error} first />
      <Alert message={formMessage(create.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={create.isPending}>
        {t.loyalty.create}
      </button>
    </form>
  );
}

type Action = "EARNED" | "USED" | "EXPIRED" | "REDEEM";

/** One program: its points, the forms that change them, and its entries. */
export function ProgramWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const language = useLanguage();
  const { data: program } = useSuspenseQuery(programQuery(props.id));
  const [action, setAction] = useState<Action>("EARNED");
  return (
    <div className="grid grid-cols-1 gap-6">
      <div>
        <p className="text-sm text-muted">{program.name}</p>
        <p className="amount text-3xl font-semibold">
          {t.loyalty.balance(formatQuantity(program.balance, language), program.unit_name)}
        </p>
      </div>
      <section className="grid gap-4 rounded-(--radius-control) bg-sheet p-4">
        <Segmented
          label={t.loyalty.action}
          value={action}
          options={[
            { value: "EARNED", label: t.loyalty.kinds.EARNED },
            { value: "USED", label: t.loyalty.kinds.USED },
            { value: "EXPIRED", label: t.loyalty.kinds.EXPIRED },
            { value: "REDEEM", label: t.loyalty.redeem },
          ]}
          onChange={setAction}
        />
        {action === "REDEEM" ? (
          <RedeemForm program={program} />
        ) : (
          <PointsForm key={action} program={program} kind={action} />
        )}
      </section>
      <History program={program} />
      <EditProgram program={program} onDone={props.onDone} />
    </div>
  );
}

function PointsField(props: { program: ProgramDetail; errors: string[] }) {
  const t = useMessages();
  return (
    <Field label={t.loyalty.amount(props.program.unit_name)} errors={props.errors} className="w-48">
      {(control) => (
        <input
          {...control}
          {...autofocus}
          name="points"
          inputMode="decimal"
          className="field amount"
          autoComplete="off"
        />
      )}
    </Field>
  );
}

function DateField(props: { errors: string[] }) {
  const t = useMessages();
  return (
    <Field label={t.entry.date} errors={props.errors}>
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
  );
}

function PointsForm(props: { program: ProgramDetail; kind: "EARNED" | "USED" | "EXPIRED" }) {
  const t = useMessages();
  const record = useRecordPoints(props.program.id);
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const amount = parseDecimal(typed.points ?? "");
    setInvalid(amount === null);
    if (amount === null) return;
    const form = event.currentTarget;
    record.mutate(
      { kind: props.kind, amount, date: typed.date || null, notes: typed.notes ?? "" },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <div className="flex flex-wrap items-start gap-4">
        <PointsField
          program={props.program}
          errors={invalid ? [t.loyalty.amountInvalid] : fieldMessages(record.error, "amount")}
        />
        <DateField errors={fieldMessages(record.error, "date")} />
        <Field label={t.loyalty.notes} className="min-w-0 flex-1 basis-48">
          {(control) => <input {...control} name="notes" className="field" autoComplete="off" />}
        </Field>
      </div>
      <Alert message={formMessage(record.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={record.isPending}>
        {t.loyalty.record}
      </button>
    </form>
  );
}

function RedeemForm(props: { program: ProgramDetail }) {
  const t = useMessages();
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const accounts = instruments.filter((item) => item.kind === "account");
  const redeem = useRedeem(props.program.id);
  const [invalid, setInvalid] = useState<string[]>([]);
  const [account, setAccount] = useState(accounts[0]?.id ?? "");
  const currency = accounts.find((item) => item.id === account)?.currency ?? "BRL";

  if (accounts.length === 0) return <p className="text-sm text-muted">{t.loyalty.noAccount}</p>;

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const points = parseDecimal(typed.points ?? "");
    const amount = parseAmount(typed.money ?? "", currency);
    setInvalid([points === null ? "points" : "", amount === null ? "money" : ""]);
    if (points === null || amount === null) return;
    const form = event.currentTarget;
    redeem.mutate(
      {
        points,
        account_id: Number(account.split(":")[1]),
        amount,
        date: typed.date || null,
        notes: "",
      },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <form
      onSubmit={submit}
      onChange={(event) =>
        setAccount(String(new FormData(event.currentTarget).get("account") ?? account))
      }
      className="grid gap-4"
      noValidate
    >
      <p className="text-sm text-muted">{t.loyalty.redeemHelp}</p>
      <div className="flex flex-wrap items-start gap-4">
        <PointsField
          program={props.program}
          errors={
            invalid.includes("points")
              ? [t.loyalty.amountInvalid]
              : fieldMessages(redeem.error, "points")
          }
        />
        <Field
          label={`${t.loyalty.money} (${currency})`}
          errors={
            invalid.includes("money")
              ? [t.entry.amountInvalid]
              : fieldMessages(redeem.error, "amount")
          }
          className="w-48"
        >
          {(control) => (
            <input
              {...control}
              name="money"
              inputMode="decimal"
              className="field amount"
              autoComplete="off"
            />
          )}
        </Field>
      </div>
      <div className="flex flex-wrap items-start gap-4">
        <AccountSelect
          label={t.loyalty.account}
          name="account"
          accounts={accounts}
          errors={fieldMessages(redeem.error, "account_id")}
          defaultValue={accounts[0]?.id}
        />
        <DateField errors={fieldMessages(redeem.error, "date")} />
      </div>
      <Alert message={formMessage(redeem.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={redeem.isPending}>
        {t.loyalty.redeem}
      </button>
    </form>
  );
}

function History(props: { program: ProgramDetail }) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const undo = useUndoPoints();
  const { program } = props;

  function detail(row: LoyaltyEntry) {
    const parts = [formatDate(row.date, order)];
    if (row.cash_amount && row.cash_currency && row.account_name) {
      parts.push(
        t.loyalty.received(formatAmount(row.cash_amount, row.cash_currency), row.account_name),
      );
    } else if (row.notes) {
      parts.push(row.notes);
    }
    return parts.join(" · ");
  }

  return (
    <section>
      <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
        {t.loyalty.history}
      </h3>
      {program.entries.length === 0 && <p className="py-4 text-muted">{t.loyalty.noHistory}</p>}
      <ul className="divide-y divide-line">
        {program.entries.map((row) => (
          <li key={row.id} className="flex items-center gap-3 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{t.loyalty.kinds[row.kind]}</span>
              <span className="block truncate text-sm text-muted">{detail(row)}</span>
            </span>
            {row.undoable && (
              <button
                type="button"
                className="link text-sm"
                disabled={undo.isPending}
                onClick={() => undo.mutate(row.id)}
              >
                {t.wallet.undo}
              </button>
            )}
            <span className="amount font-semibold">
              {row.kind === "EARNED" ? "+" : "−"}
              {formatQuantity(row.amount, language)}
            </span>
          </li>
        ))}
      </ul>
      <Alert message={formMessage(undo.error, t)} />
    </section>
  );
}

function EditProgram(props: { program: ProgramDetail; onDone: () => void }) {
  const t = useMessages();
  const { program } = props;
  const change = useSaveProgram(program.id);
  const remove = useDeleteProgram(program.id);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    change.mutate({ name: typed.name ?? "", unit_name: typed.unit ?? "" });
  }

  return (
    <details>
      <summary className="link w-fit cursor-pointer text-sm">{t.loyalty.edit}</summary>
      <form onSubmit={submit} className="mt-4 grid gap-5" noValidate>
        <ProgramFields error={change.error} name={program.name} unit={program.unit_name} />
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
  );
}
