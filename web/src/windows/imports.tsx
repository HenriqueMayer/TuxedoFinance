import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import {
  fileContent,
  type ImportDecision,
  type ImportDetail,
  type ImportMapping,
  type ImportRow,
  importQuery,
  importsQuery,
  useConfirmImport,
  useDiscardImport,
  useSaveDecisions,
  useSetMapping,
  useUndoImport,
  useUpload,
} from "../data/imports";
import { type Category, categoriesQuery, type Instrument, instrumentsQuery } from "../data/ledger";
import { useLanguage, useMessages } from "../i18n";
import { formatDate, monthLabel, monthOf, todayIso } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { formatAmount, parseAmount } from "../lib/money";
import { useDateOrder } from "../session";
import { Field } from "../ui/Field";
import { categoryLabel } from "./entry";
import { OpenWindow } from "./host";
import { AccountSelect, Alert, ConfirmButton, values } from "./wallet";

type Action = ImportDecision["action"];

/** Choose an account and a statement file. The file is read for review; nothing is recorded. */
export function ImportStartWindow() {
  const t = useMessages();
  const order = useDateOrder();
  const navigate = useNavigate();
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const { data: imports } = useSuspenseQuery(importsQuery);
  const accounts = instruments.filter((item) => item.kind === "account");
  const upload = useUpload();
  const [missing, setMissing] = useState(false);
  const [balanceInvalid, setBalanceInvalid] = useState(false);

  if (accounts.length === 0) return <p className="text-muted">{t.imports.noAccounts}</p>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    const account = accounts.find((item) => item.id === form.get("account"));
    const typed = String(form.get("balance") ?? "").trim();
    // The balance of a statement can be negative.
    const balance = typed === "" ? null : parseAmount(typed, account?.currency ?? "BRL");
    const sign = typed.startsWith("-") ? "-" : "";
    const noFile = !(file instanceof File) || file.size === 0;
    setMissing(noFile);
    setBalanceInvalid(typed !== "" && balance === null);
    if (noFile || !account || (typed !== "" && balance === null)) return;
    upload.mutate(
      {
        account_id: Number(account.id.split(":")[1]),
        file_name: file.name,
        content: await fileContent(file),
        closing_balance: balance === null ? null : `${sign}${balance}`,
        closing_date: balance === null ? null : String(form.get("date") || todayIso()),
      },
      {
        // The review takes the place of this window, so Back still closes it.
        onSuccess: (staged) =>
          navigate({
            to: ".",
            search: (previous) => ({ ...previous, w: `import:${staged.id}` }),
            replace: true,
            resetScroll: false,
            state: (state) => state,
          }),
      },
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <form onSubmit={submit} className="grid gap-5" noValidate>
        <p className="max-w-prose text-sm text-muted">{t.imports.help}</p>
        <AccountSelect
          label={t.imports.account}
          name="account"
          accounts={accounts}
          errors={fieldMessages(upload.error, "account_id")}
          defaultValue={accounts[0]?.id}
        />
        <Field
          label={t.imports.file}
          errors={missing ? [t.imports.fileMissing] : fieldMessages(upload.error, "content")}
        >
          {(control) => (
            <input
              {...control}
              type="file"
              name="file"
              accept=".ofx,.qfx,.csv,text/csv"
              className="field h-auto py-2"
            />
          )}
        </Field>
        <details>
          <summary className="action w-fit">{t.imports.check}</summary>
          <div className="mt-4 flex flex-wrap gap-4">
            <Field
              label={t.imports.closingBalance}
              errors={balanceInvalid ? [t.entry.amountInvalid] : []}
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
            <Field label={t.imports.closingDate}>
              {(control) => (
                <input {...control} type="date" name="date" className="field" max={todayIso()} />
              )}
            </Field>
          </div>
        </details>
        <Alert message={formMessage(upload.error, t)} />
        <button type="submit" className="button-primary w-fit" disabled={upload.isPending}>
          {t.imports.upload}
        </button>
      </form>
      {imports.length > 0 && (
        <section>
          <h3 className="border-b border-line pb-2 text-sm font-medium text-muted">
            {t.imports.recent}
          </h3>
          <ul className="divide-y divide-line">
            {imports.map((item) => (
              <li key={item.id}>
                <OpenWindow
                  w={`import:${item.id}`}
                  className="-mx-2 flex items-center gap-3 rounded-(--radius-control) px-2 py-2.5 hover:bg-sheet"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{item.file_name}</span>
                    <span className="block truncate text-sm text-muted">
                      {item.account_name} · {formatDate(item.created_at.slice(0, 10), order)}
                    </span>
                  </span>
                  <span className="text-sm text-muted">{t.imports.status[item.status]}</span>
                </OpenWindow>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** One import: its columns, its review, or its result. */
export function ImportWindow(props: { id: number; onDone: () => void }) {
  const t = useMessages();
  const { data } = useSuspenseQuery(importQuery(props.id));
  const open = data.status === "STAGED" || data.status === "READY";
  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="min-w-0 truncate font-medium">{data.file_name}</p>
        <p className="text-sm text-muted">
          {data.account_name} · {t.imports.status[data.status]}
        </p>
      </div>
      {open && data.needs_opening_date && (
        <p role="alert" className="rounded-(--radius-control) bg-sheet p-4 text-sm">
          {t.imports.openingDate}{" "}
          <OpenWindow w={`account:${data.account_id}`} className="action">
            {t.imports.openAccount}
          </OpenWindow>
        </p>
      )}
      {data.status === "STAGED" && <Columns batch={data} />}
      {data.status === "READY" && <Review batch={data} onDone={props.onDone} />}
      {data.status === "CONFIRMED" && <Result batch={data} />}
      {data.status === "UNDONE" && <p className="text-muted">{t.imports.undone}</p>}
    </div>
  );
}

const DATE_FORMATS: [string, string][] = [
  ["%d/%m/%Y", "31/12/2026"],
  ["%Y-%m-%d", "2026-12-31"],
  ["%m/%d/%Y", "12/31/2026"],
  ["%d-%m-%Y", "31-12-2026"],
  ["%d.%m.%Y", "31.12.2026"],
  ["%Y/%m/%d", "2026/12/31"],
];

/** The columns of a CSV file. The server proposes them; the owner confirms. */
function Columns(props: { batch: ImportDetail }) {
  const t = useMessages();
  const { batch } = props;
  const proposal = batch.mapping;
  const save = useSetMapping(batch.id);
  const [two, setTwo] = useState(Boolean(proposal && !proposal.amount_column));

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const mapping: ImportMapping = {
      date_column: typed.date ?? "",
      description_column: typed.description ?? "",
      amount_column: two ? "" : (typed.amount ?? ""),
      debit_column: two ? (typed.debit ?? "") : "",
      credit_column: two ? (typed.credit ?? "") : "",
      id_column: typed.id ?? "",
      currency_column: "",
      date_format: typed.format ?? "%Y-%m-%d",
      decimal_mark: typed.mark === "," ? "," : ".",
    };
    save.mutate(mapping);
  }

  const column = (name: string, label: string, value: string | undefined, optional = false) => (
    <Field label={label} className="min-w-40">
      {(control) => (
        <select {...control} name={name} className="field" defaultValue={value ?? ""}>
          {(optional || !value) && <option value="">{optional ? t.imports.none : ""}</option>}
          {batch.headers.map((header) => (
            <option key={header} value={header}>
              {header}
            </option>
          ))}
        </select>
      )}
    </Field>
  );

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <div>
        <h3 className="font-medium">{t.imports.columns}</h3>
        <p className="mt-1 max-w-prose text-sm text-muted">{t.imports.columnsHelp}</p>
      </div>
      <div className="flex flex-wrap gap-4">
        {column("date", t.imports.dateColumn, proposal?.date_column)}
        {column("description", t.imports.descriptionColumn, proposal?.description_column)}
        {!two && column("amount", t.imports.amountColumn, proposal?.amount_column)}
        {two && column("debit", t.imports.debitColumn, proposal?.debit_column)}
        {two && column("credit", t.imports.creditColumn, proposal?.credit_column)}
        {column("id", t.imports.idColumn, proposal?.id_column, true)}
      </div>
      <label className="flex items-center gap-3">
        <input
          type="checkbox"
          className="size-4"
          checked={two}
          onChange={(event) => setTwo(event.target.checked)}
        />
        <span>{t.imports.twoColumns}</span>
      </label>
      <div className="flex flex-wrap gap-4">
        <Field label={t.imports.dateFormat}>
          {(control) => (
            <select
              {...control}
              name="format"
              className="field"
              defaultValue={proposal?.date_format}
            >
              {DATE_FORMATS.map(([format, example]) => (
                <option key={format} value={format}>
                  {example}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label={t.imports.decimalMark}>
          {(control) => (
            <select
              {...control}
              name="mark"
              className="field"
              defaultValue={proposal?.decimal_mark}
            >
              <option value=",">{t.imports.comma}</option>
              <option value=".">{t.imports.point}</option>
            </select>
          )}
        </Field>
      </div>
      <section>
        <h4 className="text-sm font-medium text-muted">{t.imports.sample}</h4>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                {batch.headers.map((header) => (
                  <th key={header} scope="col" className="px-2 py-1.5 text-left font-medium">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {batch.sample.map((row, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: the sample rows have no identity and never reorder.
                <tr key={index} className="border-b border-line">
                  {batch.headers.map((header) => (
                    <td key={header} className="px-2 py-1.5 whitespace-nowrap">
                      {row[header]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <Alert message={formMessage(save.error, t)} />
      <button type="submit" className="button-primary w-fit" disabled={save.isPending}>
        {t.imports.readRows}
      </button>
    </form>
  );
}

/** The rows of the statement, each with its decision, and the confirmation. */
function Review(props: { batch: ImportDetail; onDone: () => void }) {
  const t = useMessages();
  const { batch } = props;
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const { data: instruments } = useSuspenseQuery(instrumentsQuery);
  const others = instruments.filter(
    (item) => item.kind === "account" && item.id !== `account:${batch.account_id}`,
  );
  const save = useSaveDecisions(batch.id);
  const confirm = useConfirmImport(batch.id);
  const discard = useDiscardImport(batch.id);
  const waiting = batch.rows.filter((row) => !row.action);

  return (
    <>
      <div>
        <h3 className="font-medium">{t.imports.review}</h3>
        <p className="mt-1 max-w-prose text-sm text-muted">{t.imports.reviewHelp}</p>
      </div>
      <ul className="divide-y divide-line border-y border-line">
        {batch.rows.map((row) => (
          <li key={row.id} className="py-3">
            <RowDecision
              // The key shows the saved decision when the server answers.
              key={`${row.action}-${row.category_id}-${row.matched_movement_id}-${row.invoice_id}-${row.counterparty_account_id}`}
              batch={batch}
              row={row}
              categories={categories}
              others={others}
            />
          </li>
        ))}
      </ul>
      <div className="grid gap-3">
        <p className={batch.undecided > 0 ? "font-medium" : "text-muted"}>
          {batch.undecided > 0 ? t.imports.undecided(batch.undecided) : t.imports.allDecided}
        </p>
        <Alert
          message={
            formMessage(save.error, t) ??
            formMessage(confirm.error, t) ??
            formMessage(discard.error, t)
          }
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ConfirmButton
            label={t.imports.discard}
            pending={discard.isPending}
            onConfirm={() => discard.mutate(undefined, { onSuccess: props.onDone })}
          />
          <div className="flex flex-wrap gap-3">
            {waiting.length > 0 && (
              <button
                type="button"
                className="button-quiet"
                disabled={save.isPending}
                onClick={() =>
                  save.mutate(waiting.map((row) => ({ row_id: row.id, action: "SKIP" as const })))
                }
              >
                {t.imports.skipRest}
              </button>
            )}
            <button
              type="button"
              className="button-primary"
              disabled={batch.undecided > 0 || confirm.isPending}
              onClick={() => confirm.mutate(batch.digest)}
            >
              {t.imports.confirm}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/** One row. A complete decision is saved at once; an incomplete one waits for its value. */
function RowDecision(props: {
  batch: ImportDetail;
  row: ImportRow;
  categories: Category[];
  others: Instrument[];
}) {
  const t = useMessages();
  const language = useLanguage();
  const order = useDateOrder();
  const { batch, row } = props;
  const save = useSaveDecisions(batch.id);
  const [action, setAction] = useState<Action | "">(row.action);
  const [account, setAccount] = useState(
    row.counterparty_account_id ? `account:${row.counterparty_account_id}` : "",
  );
  const [amountInvalid, setAmountInvalid] = useState(false);
  const income = !row.amount.startsWith("-");
  const absolute = row.amount.replace("-", "");
  const kind = income ? "INCOME" : "EXPENSE";
  const choices = props.categories.filter(
    (item) => item.transaction_type === null || item.transaction_type === kind,
  );
  const other = props.others.find((item) => item.id === account);
  const exchange = Boolean(other && other.currency !== batch.currency);

  const offered: Action[] = ["CREATE"];
  if (row.matches.length > 0) offered.push("MATCH");
  if (!income && batch.invoices.length > 0) offered.push("PAY_INVOICE");
  if (props.others.length > 0) offered.push("TRANSFER");
  offered.push("SKIP");

  function send(decision: Omit<ImportDecision, "row_id">) {
    save.mutate([{ row_id: row.id, ...decision }]);
  }

  function choose(next: Action) {
    setAction(next);
    save.reset();
    if (next === "SKIP") send({ action: "SKIP" });
    // One recorded movement can only be that one.
    const only = row.matches.length === 1 ? row.matches[0] : undefined;
    if (next === "MATCH" && only) send({ action: "MATCH", matched_movement_id: only.id });
  }

  function transfer(accountId: string, typed?: string) {
    const target = props.others.find((item) => item.id === accountId);
    if (!target) return;
    const id = Number(accountId.split(":")[1]);
    if (target.currency === batch.currency) {
      // In one currency both sides have the amount of the row.
      send({ action: "TRANSFER", counterparty_account_id: id, counterparty_amount: absolute });
      return;
    }
    if (typed === undefined) return; // The amount of the other side is still to type.
    const amount = parseAmount(typed, target.currency);
    setAmountInvalid(amount === null);
    if (amount !== null) {
      send({ action: "TRANSFER", counterparty_account_id: id, counterparty_amount: amount });
    }
  }

  const label = t.imports.action(row.description);
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline gap-3">
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{row.description}</span>
          <span className="block text-sm text-muted">{formatDate(row.date, order)}</span>
        </span>
        <span className={`amount font-semibold ${income ? "text-positive" : ""}`}>
          {income ? "+" : "−"}
          {formatAmount(absolute, batch.currency)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <select
          aria-label={label}
          className="field w-auto"
          value={action}
          disabled={save.isPending}
          onChange={(event) => choose(event.target.value as Action)}
        >
          {action === "" && <option value="">{t.imports.choose}</option>}
          {offered.map((item) => (
            <option key={item} value={item}>
              {t.imports.actions[item]}
            </option>
          ))}
        </select>
        {action === "CREATE" && (
          <select
            aria-label={`${t.entry.category}: ${row.description}`}
            className="field w-auto max-w-full"
            defaultValue={row.category_id ?? ""}
            disabled={save.isPending}
            onChange={(event) =>
              send({ action: "CREATE", category_id: Number(event.target.value) })
            }
          >
            <option value="" disabled>
              {t.entry.chooseCategory}
            </option>
            {choices.map((item) => (
              <option key={item.id} value={item.id}>
                {categoryLabel(item, props.categories)}
              </option>
            ))}
          </select>
        )}
        {action === "MATCH" && (
          <select
            aria-label={`${t.imports.movement}: ${row.description}`}
            className="field w-auto max-w-full"
            defaultValue={row.matched_movement_id ?? ""}
            disabled={save.isPending}
            onChange={(event) =>
              send({ action: "MATCH", matched_movement_id: Number(event.target.value) })
            }
          >
            <option value="" disabled>
              {t.imports.choose}
            </option>
            {row.matches.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        )}
        {action === "PAY_INVOICE" && (
          <select
            aria-label={`${t.imports.invoice}: ${row.description}`}
            className="field w-auto max-w-full"
            defaultValue={row.invoice_id ?? ""}
            disabled={save.isPending}
            onChange={(event) =>
              send({ action: "PAY_INVOICE", invoice_id: Number(event.target.value) })
            }
          >
            <option value="" disabled>
              {t.imports.choose}
            </option>
            {batch.invoices.map((item) => (
              <option key={item.id} value={item.id}>
                {t.imports.invoiceOption(
                  item.card_name,
                  monthLabel(monthOf(item.month), language),
                  formatAmount(item.remaining, batch.currency),
                )}
              </option>
            ))}
          </select>
        )}
        {action === "TRANSFER" && (
          <select
            aria-label={`${t.imports.otherAccount}: ${row.description}`}
            className="field w-auto max-w-full"
            value={account}
            disabled={save.isPending}
            onChange={(event) => {
              setAccount(event.target.value);
              transfer(event.target.value);
            }}
          >
            <option value="" disabled>
              {t.imports.choose}
            </option>
            {props.others.map((item) => (
              <option key={item.id} value={item.id}>
                {item.bank_name} · {item.name}
              </option>
            ))}
          </select>
        )}
        {action === "TRANSFER" && exchange && other && (
          <input
            aria-label={t.imports.otherAmount(other.currency)}
            aria-invalid={amountInvalid}
            placeholder={t.imports.otherAmount(other.currency)}
            inputMode="decimal"
            className="field amount w-56"
            autoComplete="off"
            defaultValue={row.counterparty_amount ?? ""}
            onBlur={(event) => transfer(account, event.currentTarget.value)}
          />
        )}
      </div>
      {row.duplicate && <p className="text-sm text-muted">{t.imports.duplicate}</p>}
      <Alert message={formMessage(save.error, t)} />
    </div>
  );
}

/** A confirmed import: what it did, the balance check, and the undo. */
function Result(props: { batch: ImportDetail }) {
  const t = useMessages();
  const order = useDateOrder();
  const { batch } = props;
  const undo = useUndoImport(batch.id);
  const skipped = batch.rows.filter((row) => row.action === "SKIP").length;
  const check = batch.reconciliation;
  const money = (amount: string) => formatAmount(amount, batch.currency);
  return (
    <>
      <div className="grid gap-1">
        <p className="text-lg font-medium">{t.imports.confirmed(batch.rows.length - skipped)}</p>
        {skipped > 0 && <p className="text-muted">{t.imports.skipped(skipped)}</p>}
        {check && (
          <p className={Number(check.difference) === 0 ? "text-muted" : ""}>
            {Number(check.difference) === 0
              ? t.imports.balanceMatches(formatDate(check.date, order))
              : t.imports.balanceDiffers(
                  formatDate(check.date, order),
                  money(check.expected),
                  money(check.actual),
                )}
          </p>
        )}
      </div>
      <ul className="divide-y divide-line border-y border-line">
        {batch.rows.map((row) => (
          <li key={row.id} className="flex items-baseline gap-3 py-2">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{row.description}</span>
              <span className="block text-sm text-muted">
                {formatDate(row.date, order)} · {row.action ? t.imports.actions[row.action] : ""}
              </span>
            </span>
            <span className="amount">{money(row.amount)}</span>
          </li>
        ))}
      </ul>
      <div className="grid gap-2">
        <p className="text-sm text-muted">{t.imports.undoHelp}</p>
        <Alert message={formMessage(undo.error, t)} />
        <button
          type="button"
          className="button-quiet w-fit"
          disabled={undo.isPending}
          onClick={() => undo.mutate()}
        >
          {t.imports.undo}
        </button>
      </div>
    </>
  );
}
