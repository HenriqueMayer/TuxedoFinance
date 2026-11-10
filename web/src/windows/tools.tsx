import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { type Growth, type Salary, useGrowth, useSalary } from "../data/plan";
import { useLanguage, useMessages } from "../i18n";
import { fieldMessages, formMessage } from "../lib/errors";
import { formatAmount, parseAmount } from "../lib/money";
import { sessionQuery } from "../session";
import { Field } from "../ui/Field";
import { Segmented } from "../ui/Segmented";
import { autofocus } from "../ui/Window";
import { Alert, values } from "./wallet";

/** Read an optional amount: an empty field is zero. Null when the text is not an amount. */
function optionalAmount(text: string | undefined, currency: string): string | null {
  const typed = (text ?? "").trim();
  if (typed === "" || /^0+([.,]0*)?$/.test(typed)) return "0";
  return parseAmount(typed, currency);
}

function AmountField(props: {
  name: string;
  label: string;
  errors: string[];
  first?: boolean;
  className?: string;
}) {
  return (
    <Field label={props.label} errors={props.errors} className={props.className ?? "w-48"}>
      {(control) => (
        <input
          {...control}
          {...(props.first ? autofocus : {})}
          name={props.name}
          inputMode="decimal"
          className="field amount"
          autoComplete="off"
        />
      )}
    </Field>
  );
}

function Line(props: { label: string; children: ReactNode; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className={props.strong ? "font-medium" : "text-muted"}>{props.label}</dt>
      <dd className={`amount ${props.strong ? "font-semibold" : ""}`}>{props.children}</dd>
    </div>
  );
}

const SALARY_FIELDS = ["gross", "pension", "transport", "food", "health", "other"] as const;

/** The net pay of a Brazilian CLT salary. The server calculates it; nothing is saved. */
export function SalaryWindow() {
  const t = useMessages();
  const calculate = useSalary();
  const [invalid, setInvalid] = useState<string[]>([]);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const wrong: string[] = [];
    const amounts = {} as Record<(typeof SALARY_FIELDS)[number], string>;
    for (const name of SALARY_FIELDS) {
      const value =
        name === "gross"
          ? parseAmount(typed.gross ?? "", "BRL")
          : optionalAmount(typed[name], "BRL");
      if (value === null) wrong.push(name);
      amounts[name] = value ?? "0";
    }
    const dependents = Number(typed.dependents || "0");
    if (!Number.isInteger(dependents) || dependents < 0 || dependents > 30) {
      wrong.push("dependents");
    }
    setInvalid(wrong);
    if (wrong.length > 0) return;
    calculate.mutate({ ...amounts, dependents });
  }

  const errors = (name: string) =>
    invalid.includes(name) ? [t.plan.tools.numberInvalid] : fieldMessages(calculate.error, name);

  return (
    <div className="grid grid-cols-1 gap-6">
      <form onSubmit={submit} className="grid gap-5" noValidate>
        <div className="flex flex-wrap gap-4">
          <AmountField
            name="gross"
            label={`${t.plan.tools.gross} (BRL)`}
            errors={errors("gross")}
            first
          />
          <Field label={t.plan.tools.dependents} errors={errors("dependents")} className="w-32">
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
        </div>
        <details>
          <summary className="link w-fit cursor-pointer text-sm">{t.plan.tools.optional}</summary>
          <div className="mt-4 flex flex-wrap gap-4">
            {(["pension", "transport", "food", "health", "other"] as const).map((name) => (
              <AmountField
                key={name}
                name={name}
                label={t.plan.tools[name]}
                errors={errors(name)}
                className="w-52"
              />
            ))}
          </div>
        </details>
        <Alert message={formMessage(calculate.error, t)} />
        <button type="submit" className="button-primary w-fit" disabled={calculate.isPending}>
          {t.plan.tools.calculate}
        </button>
      </form>
      {calculate.data && <SalaryResult result={calculate.data} />}
    </div>
  );
}

function SalaryResult(props: { result: Salary }) {
  const t = useMessages();
  const { result } = props;
  const money = (amount: string) => formatAmount(amount, "BRL");
  return (
    <section aria-live="polite">
      <p className="text-sm text-muted">{t.plan.tools.net}</p>
      <p className="amount text-3xl font-semibold">{money(result.month.net)}</p>
      <dl className="mt-3 divide-y divide-line border-y border-line">
        <Line label={t.plan.tools.gross}>{money(result.month.gross)}</Line>
        <Line label={t.plan.tools.inss}>−{money(result.month.inss)}</Line>
        <Line label={t.plan.tools.irrf}>−{money(result.month.irrf)}</Line>
        {Number(result.month.deductions) > 0 && (
          <Line label={t.plan.tools.deductions}>−{money(result.month.deductions)}</Line>
        )}
        <Line label={t.plan.tools.thirteenth}>{money(result.thirteenth.net)}</Line>
        <Line label={t.plan.tools.vacation}>{money(result.vacation.net)}</Line>
        <Line label={t.plan.tools.annual}>{money(result.annual_net)}</Line>
        <Line label={t.plan.tools.average} strong>
          {money(result.monthly_average_net)}
        </Line>
        <Line label={t.plan.tools.fgts}>{money(result.annual_fgts)}</Line>
      </dl>
      <p className="mt-3 text-sm text-muted">
        {result.assumed ? t.plan.tools.assumed(result.year) : t.plan.tools.tables(result.year)}{" "}
        {t.plan.tools.noFine}
      </p>
    </section>
  );
}

/** A balance that grows with a contribution and a yield each month. */
export function GrowthWindow() {
  const t = useMessages();
  const { data: session } = useSuspenseQuery(sessionQuery);
  const currency = session.preferences?.base_currency ?? "BRL";
  const calculate = useGrowth();
  const [period, setPeriod] = useState<"monthly" | "annual">("annual");
  const [invalid, setInvalid] = useState<string[]>([]);

  function submit(event: FormEvent<HTMLFormElement>) {
    const typed = values(event);
    const wrong: string[] = [];
    const initial = optionalAmount(typed.initial, currency);
    const contribution = optionalAmount(typed.contribution, currency);
    const rate = (typed.rate ?? "").trim().replace(",", ".");
    const months = Number(typed.months);
    if (initial === null) wrong.push("initial");
    if (contribution === null) wrong.push("contribution");
    if (!/^-?\d+(\.\d{1,4})?$/.test(rate)) wrong.push("rate");
    if (!Number.isInteger(months) || months < 1) wrong.push("months");
    setInvalid(wrong);
    if (wrong.length > 0) return;
    calculate.mutate({
      initial: initial ?? "0",
      contribution: contribution ?? "0",
      rate,
      rate_period: period,
      months,
    });
  }

  const errors = (name: string) =>
    invalid.includes(name) ? [t.plan.tools.numberInvalid] : fieldMessages(calculate.error, name);

  return (
    <div className="grid grid-cols-1 gap-6">
      <form onSubmit={submit} className="grid gap-5" noValidate>
        <div className="flex flex-wrap gap-4">
          <AmountField
            name="initial"
            label={`${t.plan.tools.initial} (${currency})`}
            errors={errors("initial")}
            first
          />
          <AmountField
            name="contribution"
            label={t.plan.tools.contribution}
            errors={errors("contribution")}
            className="w-52"
          />
        </div>
        <div className="flex flex-wrap items-start gap-4">
          <Field label={t.plan.tools.rate} errors={errors("rate")} className="w-28">
            {(control) => (
              <input
                {...control}
                name="rate"
                inputMode="decimal"
                className="field amount"
                autoComplete="off"
              />
            )}
          </Field>
          <Segmented
            label={t.plan.tools.ratePeriod}
            value={period}
            options={[
              { value: "annual", label: t.plan.tools.perYear },
              { value: "monthly", label: t.plan.tools.perMonth },
            ]}
            onChange={setPeriod}
          />
          <Field label={t.plan.tools.period} errors={errors("months")} className="w-28">
            {(control) => (
              <input
                {...control}
                name="months"
                type="number"
                min={1}
                max={600}
                defaultValue={12}
                className="field amount"
              />
            )}
          </Field>
        </div>
        <Alert message={formMessage(calculate.error, t)} />
        <button type="submit" className="button-primary w-fit" disabled={calculate.isPending}>
          {t.plan.tools.calculate}
        </button>
      </form>
      {calculate.data && <GrowthResult result={calculate.data} currency={currency} />}
    </div>
  );
}

function GrowthResult(props: { result: Growth; currency: string }) {
  const t = useMessages();
  const language = useLanguage();
  const { result } = props;
  const money = (amount: string) => formatAmount(amount, props.currency);
  const last = result.rows.length;
  // A long period shows one row for each year, and the last month.
  const rows =
    last <= 24
      ? result.rows
      : result.rows.filter((row) => row.month % 12 === 0 || row.month === last);
  return (
    <section aria-live="polite">
      <p className="text-sm text-muted">{t.plan.tools.ending}</p>
      <p className="amount text-3xl font-semibold">{money(result.ending)}</p>
      <dl className="mt-3 divide-y divide-line border-y border-line">
        <Line label={t.plan.tools.contributed}>{money(result.contributed)}</Line>
        <Line label={t.plan.tools.yielded} strong>
          {money(result.total_yield)}
        </Line>
      </dl>
      <p className="mt-3 text-sm text-muted">
        {t.plan.tools.monthlyRate(
          Number(result.monthly_rate).toLocaleString(language, { maximumFractionDigits: 4 }),
        )}
      </p>
      <ul className="mt-4 divide-y divide-line text-sm">
        {rows.map((row) => (
          <li key={row.month} className="flex items-baseline justify-between gap-4 py-1.5">
            <span className="text-muted">{t.plan.tools.monthN(row.month)}</span>
            <span className="amount">{money(row.balance)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
