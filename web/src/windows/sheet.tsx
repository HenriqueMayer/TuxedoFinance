import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import type { components } from "../api/schema";
import {
  type Sheet,
  type SheetChanges,
  type SheetMonths,
  savedSheetQuery,
  sheetQuery,
  useDeleteSheet,
  useSaveSheet,
} from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import { monthOf, shortMonthLabel } from "../lib/dates";
import { fieldMessages, formMessage } from "../lib/errors";
import { editableAmount, formatAmount, parseAmount } from "../lib/money";
import { AmountInput } from "../ui/AmountInput";
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { Select } from "../ui/Select";
import { Alert, ConfirmButton, values } from "./wallet";

type Saved = components["schemas"]["SavedSheetOut"];
type Row = Sheet["rows"][number];
type Cell = Row["cells"][number];

const EMPTY: SheetChanges = { cells: {}, manual: [] };

/** The stored changes with every amount as text, as this window keeps them. */
function fromSaved(saved: Saved): SheetChanges {
  const cells: SheetChanges["cells"] = {};
  for (const [key, months] of Object.entries(saved.changes.cells ?? {})) {
    cells[key] = Object.fromEntries(
      Object.entries(months).map(([month, amount]) => [month, String(amount)]),
    );
  }
  const manual = (saved.changes.manual ?? []).map((row) => ({
    ...row,
    amount: row.amount === null || row.amount === undefined ? null : String(row.amount),
  }));
  return { cells, manual };
}

/**
 * Read a typed cell. An empty cell returns "" and means the recorded value.
 * Zero is a value. Null means that the text is not an amount.
 */
function readCell(text: string, currency: string): string | null {
  const typed = text.trim();
  if (typed === "") return "";
  if (/^0+([.,]0*)?$/.test(typed)) return "0.00";
  return parseAmount(typed, currency);
}

/** The sheet of the months ahead: the live one, or a saved set of changes. */
export function SheetWindow(props: { id?: number; onDone: () => void }) {
  if (props.id === undefined) return <SheetEditor onDone={props.onDone} />;
  return <SavedSheet id={props.id} onDone={props.onDone} />;
}

function SavedSheet(props: { id: number; onDone: () => void }) {
  const { data } = useSuspenseQuery(savedSheetQuery(props.id));
  return <SheetEditor saved={data} onDone={props.onDone} />;
}

function SheetEditor(props: { saved?: Saved; onDone: () => void }) {
  const t = useMessages();
  const navigate = useNavigate();
  const { saved } = props;
  const [changes, setChanges] = useState<SheetChanges>(saved ? fromSaved(saved) : EMPTY);
  const [months, setMonths] = useState<SheetMonths>(saved?.months === 12 ? 12 : 6);
  const sheet = useQuery(sheetQuery(months, changes));
  const save = useSaveSheet(saved?.id);
  const remove = useDeleteSheet(saved?.id ?? 0);
  const changed = Object.keys(changes.cells).length > 0 || changes.manual.length > 0;

  function setCell(row: Row, cell: Cell, value: string) {
    const month = monthOf(cell.month);
    const typed = { ...(changes.cells[row.key] ?? {}) };
    if (!cell.changed && (value === "" || value === cell.value)) return; // Nothing was typed.
    if (value === "") delete typed[month];
    else typed[month] = value;
    const cells = { ...changes.cells };
    if (Object.keys(typed).length > 0) cells[row.key] = typed;
    else delete cells[row.key];
    setChanges({ ...changes, cells });
    save.reset();
  }

  function addRow(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const label = (typed.label ?? "").trim();
    const amount = readCell(typed.amount ?? "", sheet.data?.currency ?? "BRL");
    if (!label || amount === null) return;
    const id = Math.random().toString(36).slice(2, 10);
    const section = typed.section === "income" ? "income" : "expense";
    setChanges({
      ...changes,
      manual: [...changes.manual, { id, label, section, amount: amount === "" ? null : amount }],
    });
    save.reset();
    event.currentTarget.reset();
  }

  function removeRow(key: string) {
    const cells = { ...changes.cells };
    delete cells[key];
    setChanges({ cells, manual: changes.manual.filter((row) => `manual:${row.id}` !== key) });
    save.reset();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    save.mutate(
      { name: typed.name ?? "", months, changes },
      {
        onSuccess: (created) => {
          if (saved) return;
          // The saved sheet takes the place of this window, so Back still closes it.
          navigate({
            to: ".",
            search: (previous) => ({ ...previous, w: `sheet:${created.id}` }),
            replace: true,
            resetScroll: false,
            state: (state) => state,
          });
        },
      },
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-prose text-sm text-muted">{t.plan.sheet.help}</p>
        <Segmented
          label={t.plan.sheet.months}
          value={String(months) as "6" | "12"}
          options={[
            { value: "6", label: t.plan.sheet.six },
            { value: "12", label: t.plan.sheet.twelve },
          ]}
          onChange={(value) => setMonths(value === "12" ? 12 : 6)}
        />
      </div>

      {sheet.isPending && <p className="text-muted">{t.common.loading}</p>}
      {sheet.isError && <Alert message={formMessage(sheet.error, t)} />}
      {sheet.data && (
        <>
          <p className="text-sm">
            {t.plan.ahead.today(formatAmount(sheet.data.opening_balance, sheet.data.currency))}
          </p>
          <Table sheet={sheet.data} changed={changed} onCell={setCell} onRemove={removeRow} />
          {!sheet.data.complete && (
            <p className="text-sm text-muted">
              {t.plan.ahead.incomplete(sheet.data.missing_currencies.join(", "))}
            </p>
          )}
        </>
      )}

      <form
        onSubmit={addRow}
        className="flex flex-wrap items-end gap-4 rounded-(--radius-control) bg-sheet p-4"
        noValidate
      >
        <Field label={t.plan.sheet.rowName} className="min-w-0 flex-1 basis-48">
          {(control) => (
            <input
              {...control}
              name="label"
              className="field"
              maxLength={80}
              placeholder={t.plan.sheet.rowNamePlaceholder}
              autoComplete="off"
            />
          )}
        </Field>
        <Field label={t.plan.sheet.rowKind}>
          {(control) => (
            <Select
              {...control}
              name="section"
              defaultValue="expense"
              options={[
                { value: "income", label: t.plan.sheet.incomeSection },
                { value: "expense", label: t.plan.sheet.expenseSection },
              ]}
            />
          )}
        </Field>
        <Field label={t.plan.sheet.rowAmount} className="w-44">
          {(control) => (
            <AmountInput
              currency={sheet.data?.currency ?? "BRL"}
              {...control}
              name="amount"
              className="field amount"
            />
          )}
        </Field>
        <button type="submit" className="button-quiet">
          {t.plan.sheet.addRow}
        </button>
      </form>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-4" noValidate>
        <Field
          label={t.plan.sheet.name}
          errors={fieldMessages(save.error, "name")}
          className="min-w-0 flex-1 basis-56"
        >
          {(control) => (
            <input
              {...control}
              name="name"
              className="field"
              maxLength={120}
              defaultValue={saved?.name ?? ""}
              placeholder={t.plan.sheet.namePlaceholder}
              autoComplete="off"
            />
          )}
        </Field>
        <button type="submit" className="button-primary" disabled={save.isPending}>
          {t.plan.sheet.save}
        </button>
        {changed && (
          <button
            type="button"
            className="button-quiet"
            onClick={() => {
              setChanges(EMPTY);
              save.reset();
            }}
          >
            {t.plan.sheet.clear}
          </button>
        )}
        {saved && (
          <ConfirmButton
            label={t.plan.sheet.delete}
            pending={remove.isPending}
            onConfirm={() => remove.mutate(undefined, { onSuccess: props.onDone })}
          />
        )}
      </form>
      {save.isSuccess && saved && (
        <p role="status" className="text-sm text-muted">
          {t.plan.sheet.saved}
        </p>
      )}
      <Alert
        message={
          fieldMessages(save.error, "changes")[0] ??
          formMessage(save.error, t) ??
          formMessage(remove.error, t)
        }
      />
    </div>
  );
}

const HEAD = "px-2 py-2 text-right text-sm font-medium text-muted whitespace-nowrap";
const LABEL = "sticky left-0 z-10 bg-surface py-1.5 pr-3 text-left font-normal";

function Table(props: {
  sheet: Sheet;
  changed: boolean;
  onCell: (row: Row, cell: Cell, value: string) => void;
  onRemove: (key: string) => void;
}) {
  const t = useMessages();
  const language = useLanguage();
  const { sheet } = props;
  const money = (amount: string) => formatAmount(amount, sheet.currency);
  const label = (month: string) => shortMonthLabel(monthOf(month), language);
  const sections = [
    {
      name: t.plan.sheet.incomeSection,
      rows: sheet.rows.filter((row) => row.section === "income"),
    },
    {
      name: t.plan.sheet.expenseSection,
      rows: sheet.rows.filter((row) => row.section !== "income"),
    },
  ];
  const totals: {
    name: string;
    value: (total: Sheet["totals"][number]) => string;
    strong?: boolean;
  }[] = [
    { name: t.plan.ahead.income, value: (total) => total.income },
    { name: t.plan.ahead.expenses, value: (total) => total.expenses },
    { name: t.plan.ahead.result, value: (total) => total.result },
    { name: t.plan.ahead.balance, value: (total) => total.balance, strong: true },
  ];
  if (props.changed) {
    totals.push({ name: t.plan.sheet.withoutChanges, value: (total) => total.live_balance });
  }

  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={`${LABEL} text-sm font-medium text-muted`}>
              {t.plan.sheet.source}
            </th>
            {sheet.totals.map((total) => (
              <th key={total.month} scope="col" className={HEAD}>
                {label(total.month)}
              </th>
            ))}
          </tr>
        </thead>
        {sections.map(
          (section) =>
            section.rows.length > 0 && (
              <tbody key={section.name}>
                <tr>
                  <th
                    scope="rowgroup"
                    colSpan={sheet.totals.length + 1}
                    className="pt-4 pb-1 text-left text-xs font-semibold tracking-wide text-muted uppercase"
                  >
                    <span className="sticky left-0">{section.name}</span>
                  </th>
                </tr>
                {section.rows.map((row) => {
                  const name = row.label || t.plan.sheet.other;
                  return (
                    <tr key={row.key} className="border-b border-line">
                      <th scope="row" className={LABEL}>
                        <span className="flex max-w-56 min-w-32 items-center gap-2">
                          <span className="truncate">{name}</span>
                          {row.manual && (
                            <button
                              type="button"
                              className="action"
                              aria-label={t.plan.sheet.removeRow(name)}
                              onClick={() => props.onRemove(row.key)}
                            >
                              ×
                            </button>
                          )}
                        </span>
                      </th>
                      {row.cells.map((cell) => (
                        <td key={cell.month} className="p-0.5">
                          <CellInput
                            // The key shows the calculated value after each change.
                            key={`${cell.value}-${cell.changed}`}
                            cell={cell}
                            currency={sheet.currency}
                            label={t.plan.sheet.cell(name, label(cell.month))}
                            onChange={(value) => props.onCell(row, cell, value)}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            ),
        )}
        <tfoot>
          {totals.map((total, index) => (
            <tr key={total.name} className={index === 0 ? "border-t-2 border-control" : ""}>
              <th
                scope="row"
                className={`${LABEL} ${total.strong ? "font-semibold" : "text-muted"} ${index === 0 ? "pt-3" : ""}`}
              >
                {total.name}
              </th>
              {sheet.totals.map((month) => {
                const amount = total.value(month);
                return (
                  <td
                    key={month.month}
                    className={`amount px-2 py-1.5 text-right whitespace-nowrap ${index === 0 ? "pt-3" : ""} ${total.strong ? "font-semibold" : ""} ${Number(amount) < 0 ? "text-negative" : ""}`}
                  >
                    {money(amount)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tfoot>
      </table>
    </div>
  );
}

/** One cell. Typing a value changes the sheet when the cell loses focus or on Enter. */
function CellInput(props: {
  cell: Cell;
  currency: string;
  label: string;
  onChange: (value: string) => void;
}) {
  const t = useMessages();
  const { cell } = props;
  const [invalid, setInvalid] = useState(false);
  const shown = cell.changed || cell.value !== "0.00";
  return (
    <AmountInput
      currency={props.currency}
      aria-label={props.label}
      aria-invalid={invalid}
      title={
        invalid
          ? t.plan.sheet.invalid
          : cell.changed
            ? t.plan.sheet.recorded(formatAmount(cell.live, props.currency))
            : undefined
      }
      placeholder="–"
      defaultValue={shown ? editableAmount(cell.value, props.currency) : ""}
      className={`amount w-full min-w-24 rounded-(--radius-control) border bg-transparent px-2 py-1.5 text-right ${
        invalid
          ? "border-negative"
          : cell.changed
            ? "border-ink font-semibold"
            : "border-transparent hover:border-line"
      }`}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
      onBlur={(event) => {
        const value = readCell(event.currentTarget.value, props.currency);
        setInvalid(value === null);
        if (value !== null) props.onChange(value);
      }}
    />
  );
}
