import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  type Operation,
  type PositionDetail,
  positionQuery,
  positionsQuery,
  useChangePosition,
  useCreatePosition,
  useDeleteOperation,
  useDeletePosition,
  useRecordOperation,
  useSetValue,
} from "../data/investments";
import { instrumentsQuery } from "../data/ledger";
import { walletQuery } from "../data/wallet";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import {
  editableAmount,
  editableDecimal,
  formatAmount,
  formatQuantity,
  parseAmount,
  parseDecimal,
} from "../lib/money";
import { sessionQuery, useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { autofocus } from "../ui/Window";
import { CURRENCIES } from "./settings";
import { AccountSelect, Alert, ConfirmButton, values } from "./wallet";

type Mode = PositionDetail["valuation_mode"];
type Currency = (typeof CURRENCIES)[number];

/** Create an investment: where it is, how it is valued, and what it already holds. */
export function NewInvestmentWindow(props: { onDone: () => void }) {
  const t = useMessages();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const { data: wallet } = useSuspenseQuery(walletQuery);
  const { data: portfolio } = useSuspenseQuery(positionsQuery);
  const create = useCreatePosition();
  const [mode, setMode] = useState<Mode>("MONETARY");
  const [currency, setCurrency] = useState<Currency>(session.preferences?.base_currency ?? "BRL");
  const [invalid, setInvalid] = useState<string[]>([]);
  // A typed name of a known institution means that institution.
  const institutions = [
    ...new Set([
      ...wallet.banks.map((bank) => bank.name),
      ...portfolio.positions.map((position) => position.institution_name),
    ]),
  ];

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const wrong: string[] = [];
    // An empty opening value means that the investment starts empty.
    const read = (name: string, parse: (text: string) => string | null) => {
      const text = (typed[name] ?? "").trim();
      if (text === "") return "0";
      const value = parse(text);
      if (value === null) wrong.push(name);
      return value ?? "0";
    };
    const balance = mode === "MONETARY" ? read("balance", (x) => parseAmount(x, currency)) : "0";
    const quantity = mode === "UNITS" ? read("quantity", parseDecimal) : "0";
    const price = mode === "UNITS" ? read("price", parseDecimal) : "0";
    setInvalid(wrong);
    if (wrong.length > 0) return;
    create.mutate(
      {
        name: typed.name ?? "",
        institution_name: typed.institution ?? "",
        currency,
        valuation_mode: mode,
        opening_balance: balance,
        opening_quantity: quantity,
        opening_unit_price: price,
        opening_date: typed.date || null,
      },
      { onSuccess: props.onDone },
    );
  }

  const numberError = (name: string, field: string) =>
    invalid.includes(name) ? [t.invest.numberInvalid] : fieldMessages(create.error, field);

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <Field label={t.invest.name} errors={fieldMessages(create.error, "name")}>
        {(control) => (
          <input
            {...control}
            {...autofocus}
            name="name"
            className="field"
            placeholder={t.invest.namePlaceholder}
            autoComplete="off"
          />
        )}
      </Field>
      <Field
        label={t.invest.institution}
        errors={[
          ...fieldMessages(create.error, "institution_name"),
          ...fieldMessages(create.error, "institution_id"),
        ]}
      >
        {(control) => (
          <>
            <input
              {...control}
              name="institution"
              className="field"
              list="investment-institutions"
              placeholder={t.invest.institutionPlaceholder}
              defaultValue={institutions.length === 1 ? institutions[0] : ""}
              autoComplete="off"
            />
            <datalist id="investment-institutions">
              {institutions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </>
        )}
      </Field>
      <div className="grid gap-1.5">
        <Segmented
          label={t.invest.kind}
          value={mode}
          options={[
            { value: "MONETARY", label: t.invest.balanceKind },
            { value: "UNITS", label: t.invest.unitsKind },
          ]}
          onChange={setMode}
        />
        <p className="text-sm text-muted">{t.invest.kindHelp[mode]}</p>
      </div>
      <Field label={t.invest.currency} className="w-fit">
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
      <fieldset className="grid gap-4 rounded-(--radius-control) bg-sheet p-4">
        <legend className="sr-only">{t.invest.opening}</legend>
        <p className="text-sm text-muted">{t.invest.openingHelp}</p>
        <div className="flex flex-wrap gap-4">
          {mode === "MONETARY" ? (
            <Field
              label={`${t.invest.balanceToday} (${currency})`}
              errors={numberError("balance", "opening_balance")}
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
          ) : (
            <>
              <Field
                label={t.invest.quantity}
                errors={numberError("quantity", "opening_quantity")}
                className="w-36"
              >
                {(control) => (
                  <input
                    {...control}
                    name="quantity"
                    inputMode="decimal"
                    className="field amount"
                    autoComplete="off"
                  />
                )}
              </Field>
              <Field
                label={`${t.invest.paidPrice} (${currency})`}
                errors={numberError("price", "opening_unit_price")}
                className="w-48"
              >
                {(control) => (
                  <input
                    {...control}
                    name="price"
                    inputMode="decimal"
                    className="field amount"
                    autoComplete="off"
                  />
                )}
              </Field>
            </>
          )}
          <Field label={t.invest.since} errors={fieldMessages(create.error, "opening_date")}>
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
      </fieldset>
      <Alert message={formMessage(create.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={create.isPending}>
        {t.invest.create}
      </button>
    </form>
  );
}

type Action = "value" | "DEPOSIT" | "WITHDRAWAL";

/** One investment: what it is worth, the forms that change it, and its operations. */
export function InvestmentWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { data: position } = useSuspenseQuery(positionQuery(props.id));
  const [action, setAction] = useState<Action>("value");
  const units = position.valuation_mode === "UNITS";
  const money = (amount: string) => formatAmount(amount, position.currency);

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm text-muted">
          {position.institution_name} · {position.name}
        </p>
        <p className="amount text-3xl font-semibold">{money(position.value)}</p>
        {units && (
          <p className="mt-1 text-sm text-muted">
            {t.invest.units(formatQuantity(position.quantity ?? "0", language))}
            {" · "}
            {position.unit_price && position.price_date
              ? t.invest.priceOn(money(position.unit_price), formatDate(position.price_date, order))
              : t.invest.noPrice}
          </p>
        )}
        <dl className="mt-3 flex flex-wrap gap-x-10 gap-y-2">
          {units && (
            <div>
              <dt className="text-sm text-muted">{t.invest.cost}</dt>
              <dd className="amount font-semibold">{money(position.cost)}</dd>
            </div>
          )}
          {units && position.gain !== null && position.has_price && (
            <div>
              <dt className="text-sm text-muted">{t.invest.gain}</dt>
              <dd
                className={`amount font-semibold ${Number(position.gain) < 0 ? "text-negative" : "text-positive"}`}
              >
                {Number(position.gain) < 0 ? "−" : "+"}
                {money(position.gain.replace("-", ""))}
              </dd>
            </div>
          )}
          {Number(position.yields) > 0 && (
            <div>
              <dt className="text-sm text-muted">{t.invest.yields}</dt>
              <dd className="amount font-semibold text-positive">+{money(position.yields)}</dd>
            </div>
          )}
        </dl>
      </div>

      {position.is_archived ? (
        <p className="text-sm text-muted">{t.invest.isArchived}</p>
      ) : (
        <section className="grid gap-4 rounded-(--radius-control) bg-sheet p-4">
          <Segmented
            label={t.invest.action}
            value={action}
            options={[
              { value: "value", label: t.invest.update },
              { value: "DEPOSIT", label: t.invest.deposit },
              { value: "WITHDRAWAL", label: t.invest.withdraw },
            ]}
            onChange={setAction}
          />
          {action === "value" ? (
            // The key shows the new value in the field after it is saved.
            <ValueForm key={`${position.value}-${position.unit_price}`} position={position} />
          ) : (
            <OperationForm
              key={action}
              position={position}
              kind={action}
              onDone={() => setAction("value")}
            />
          )}
        </section>
      )}

      <History position={position} />
      <EditPosition position={position} onDone={props.onDone} />
    </div>
  );
}

/** The value of today from one number: the balance, or the unit price. */
function ValueForm(props: { position: PositionDetail }) {
  const t = useMessages();
  const { position } = props;
  const units = position.valuation_mode === "UNITS";
  const save = useSetValue(position.id);
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event).value ?? "";
    const value = units ? parseDecimal(typed) : parseAmount(typed, position.currency);
    setInvalid(value === null);
    if (value !== null) save.mutate(value);
  }

  return (
    <form onSubmit={submit} className="grid gap-3" noValidate>
      <div className="flex flex-wrap items-end gap-3">
        <Field
          label={`${units ? t.invest.priceToday : t.invest.balanceToday} (${position.currency})`}
          errors={invalid ? [t.invest.numberInvalid] : fieldMessages(save.error, "value")}
          className="w-48"
        >
          {(control) => (
            <input
              {...control}
              {...autofocus}
              name="value"
              inputMode="decimal"
              className="field amount"
              defaultValue={
                units
                  ? position.unit_price
                    ? editableDecimal(position.unit_price, position.currency)
                    : ""
                  : editableAmount(position.value, position.currency)
              }
              autoComplete="off"
            />
          )}
        </Field>
        <button type="submit" className="button-primary" disabled={save.isPending}>
          {t.common.save}
        </button>
      </div>
      {!units && <p className="text-sm text-muted">{t.invest.balanceHelp}</p>}
      <Alert message={formMessage(save.error, t)} />
    </form>
  );
}

/** A deposit from an account, or a withdrawal to one. */
function OperationForm(props: {
  position: PositionDetail;
  kind: "DEPOSIT" | "WITHDRAWAL";
  onDone: () => void;
}) {
  const t = useMessages();
  const { position, kind } = props;
  const units = position.valuation_mode === "UNITS";
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  // The money moves at its face value, so the account has the currency of the investment.
  const accounts = instruments.filter(
    (item) => item.kind === "account" && item.currency === position.currency,
  );
  const record = useRecordOperation(position.id);
  const [invalid, setInvalid] = useState<string[]>([]);

  if (accounts.length === 0) {
    return <p className="text-sm text-muted">{t.invest.needAccount(position.currency)}</p>;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const amount = units ? null : parseAmount(typed.amount ?? "", position.currency);
    const quantity = units ? parseDecimal(typed.quantity ?? "") : null;
    const price = units ? parseDecimal(typed.price ?? "") : null;
    const wrong = [
      !units && amount === null && "amount",
      units && quantity === null && "quantity",
      units && price === null && "price",
    ].filter((name) => typeof name === "string");
    setInvalid(wrong);
    if (wrong.length > 0) return;
    record.mutate(
      {
        kind,
        date: typed.date || null,
        account_id: Number((typed.account ?? "").split(":")[1]),
        amount,
        quantity,
        unit_price: price,
        cash_amount: null,
      },
      { onSuccess: props.onDone },
    );
  }

  const numberError = (name: string, field: string) =>
    invalid.includes(name) ? [t.invest.numberInvalid] : fieldMessages(record.error, field);

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <div className="flex flex-wrap items-end gap-4">
        {units ? (
          <>
            <Field
              label={t.invest.quantity}
              errors={numberError("quantity", "quantity")}
              className="w-32"
            >
              {(control) => (
                <input
                  {...control}
                  {...autofocus}
                  name="quantity"
                  inputMode="decimal"
                  className="field amount"
                  autoComplete="off"
                />
              )}
            </Field>
            <Field
              label={`${t.invest.unitPrice} (${position.currency})`}
              errors={numberError("price", "unit_price")}
              className="w-40"
            >
              {(control) => (
                <input
                  {...control}
                  name="price"
                  inputMode="decimal"
                  className="field amount"
                  defaultValue={
                    position.unit_price
                      ? editableDecimal(position.unit_price, position.currency)
                      : ""
                  }
                  autoComplete="off"
                />
              )}
            </Field>
          </>
        ) : (
          <Field
            label={`${t.entry.amount} (${position.currency})`}
            errors={
              invalid.includes("amount")
                ? [t.entry.amountInvalid]
                : fieldMessages(record.error, "amount")
            }
            className="w-40"
          >
            {(control) => (
              <input
                {...control}
                {...autofocus}
                name="amount"
                inputMode="decimal"
                className="field amount"
                autoComplete="off"
              />
            )}
          </Field>
        )}
        <div className="min-w-48 flex-1">
          <AccountSelect
            label={kind === "DEPOSIT" ? t.invest.fromAccount : t.invest.toAccount}
            name="account"
            accounts={accounts}
            errors={fieldMessages(record.error, "account_id")}
            defaultValue={accounts[0]?.id}
          />
        </div>
        <Field label={t.entry.date} errors={fieldMessages(record.error, "date")}>
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
      <Alert message={formMessage(record.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={record.isPending}>
        {kind === "DEPOSIT" ? t.invest.deposit : t.invest.withdraw}
      </button>
    </form>
  );
}

function History(props: { position: PositionDetail }) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const undo = useDeleteOperation();
  const { position } = props;
  const money = (amount: string) => formatAmount(amount, position.currency);

  function detail(row: Operation) {
    const parts = [formatDate(row.date, order)];
    if (row.account_name) parts.push(row.account_name);
    if (row.quantity && row.unit_price) {
      parts.push(`${formatQuantity(row.quantity, language)} × ${money(row.unit_price)}`);
    }
    return parts.join(" · ");
  }

  return (
    <section>
      <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
        {t.invest.history}
      </h3>
      {position.operations.length === 0 && !position.opening && (
        <p className="py-4 text-muted">{t.invest.noHistory}</p>
      )}
      <ul className="divide-y divide-line">
        {position.operations.map((row) => (
          <li key={row.id} className="flex items-center gap-3 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{t.invest.kinds[row.kind]}</span>
              <span className="block truncate text-sm text-muted">{detail(row)}</span>
            </span>
            <button
              type="button"
              className="link text-sm"
              disabled={undo.isPending}
              onClick={() => undo.mutate(row.id)}
            >
              {t.wallet.undo}
            </button>
            <span
              className={`amount font-semibold ${row.kind === "WITHDRAWAL" ? "" : "text-positive"}`}
            >
              {row.kind === "WITHDRAWAL" ? "−" : "+"}
              {money(row.value)}
            </span>
          </li>
        ))}
        {position.opening && (
          <li className="flex items-center gap-3 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{t.invest.opening}</span>
              {position.opening.date && (
                <span className="block text-sm text-muted">
                  {formatDate(position.opening.date, order)}
                </span>
              )}
            </span>
            <span className="amount font-semibold">{money(position.opening.value)}</span>
          </li>
        )}
      </ul>
      <Alert
        message={
          formMessage(undo.error, t) ??
          fieldMessages(undo.error, "date")[0] ??
          fieldMessages(undo.error, "amount")[0]
        }
      />
    </section>
  );
}

function EditPosition(props: { position: PositionDetail; onDone: () => void }) {
  const t = useMessages();
  const { position } = props;
  const change = useChangePosition(position.id);
  const remove = useDeletePosition(position.id);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    change.mutate({ name: typed.name ?? "", is_archived: typed.archived === "on" });
  }

  return (
    <details>
      <summary className="link w-fit cursor-pointer text-sm">{t.invest.edit}</summary>
      <form onSubmit={submit} className="mt-4 grid gap-5" noValidate>
        <Field label={t.invest.name} errors={fieldMessages(change.error, "name")}>
          {(control) => (
            <input
              {...control}
              name="name"
              className="field"
              defaultValue={position.name}
              autoComplete="off"
            />
          )}
        </Field>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            name="archived"
            className="size-4"
            defaultChecked={position.is_archived}
          />
          <span>{t.invest.archive}</span>
        </label>
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
