/**
 * The data source of the public demonstration.
 *
 * The backend exports the answers of the API for one fictional owner
 * (`backend/reports/demo.py`). This module serves those answers to the
 * client in place of the network, so the demonstration needs no server.
 *
 * It is read-only. A request that would change a record is refused with a
 * message that the form shows. Nothing here calculates a financial rule: an
 * answer is a recorded one. The one exception is a search in Transactions,
 * which filters the recorded rows of the month and adds their amounts.
 */
import { currentLanguage, currentMessages } from "../i18n";
import { freezeToday } from "../lib/dates";

type Json = Record<string, unknown>;
type Dataset = {
  today: string;
  answers: Record<string, unknown>;
  sheets: { months: number; changes: unknown; answer: unknown }[];
};

const loaded = new Map<string, Promise<Dataset>>();

function dataset(): Promise<Dataset> {
  const language = currentLanguage();
  let pending = loaded.get(language);
  if (!pending) {
    pending = fetch(`${import.meta.env.BASE_URL}demo/${language}.json`).then((response) => {
      if (!response.ok)
        throw new Error(`The demonstration data did not load (${response.status}).`);
      return response.json() as Promise<Dataset>;
    });
    loaded.set(language, pending);
  }
  return pending;
}

/** Load the data and show the day of the data as today. Call once before the first render. */
export async function prepareDemo(): Promise<void> {
  freezeToday((await dataset()).today);
}

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The name of a recorded answer: the method, the path and the sorted query. */
function key(method: string, path: string, query: Record<string, string>): string {
  const text = Object.keys(query)
    .sort()
    .map((name) => `${name}=${query[name]}`)
    .join("&");
  return text ? `${method} ${path}?${text}` : `${method} ${path}`;
}

/** A value as text with its keys in order, so two equal values give equal text. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const record = value as Json;
    return `{${Object.keys(record)
      .sort()
      .map((name) => `${JSON.stringify(name)}:${canonical(record[name])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

function cents(amount: unknown): number {
  return Math.round(Number(amount) * 100);
}

type Row = {
  title: string;
  transaction_type: "INCOME" | "EXPENSE";
  amount: string;
  month_amount?: string | null;
  category: { name: string };
  instrument: { name: string; bank_name?: string };
};
type Page = { items: Row[]; pages: number };

/** The recorded rows of a month that match a search or a type, as one page. */
function search(answers: Dataset["answers"], query: Record<string, string>): unknown {
  const { q = "", type = "", page: _page, ...base } = query;
  const first = answers[key("GET", "/api/ledger/transactions", base)] as Page | undefined;
  const rows = [...(first?.items ?? [])];
  for (let number = 2; number <= (first?.pages ?? 1); number += 1) {
    const next = answers[key("GET", "/api/ledger/transactions", { ...base, page: String(number) })];
    rows.push(...((next as Page | undefined)?.items ?? []));
  }
  const text = q.trim().toLowerCase();
  const items = rows.filter((row) => {
    if (type && row.transaction_type !== type) return false;
    const words = `${row.title} ${row.category.name} ${row.instrument.name}`.toLowerCase();
    return !text || words.includes(text);
  });
  const total = (kind: Row["transaction_type"]) =>
    (
      items
        .filter((row) => row.transaction_type === kind)
        .reduce((sum, row) => sum + cents(row.month_amount ?? row.amount), 0) / 100
    ).toFixed(2);
  return {
    items,
    count: items.length,
    page: 1,
    pages: 1,
    income: total("INCOME"),
    expense: total("EXPENSE"),
  };
}

/** Answer a request of the client from the recorded data. */
export async function demoFetch(request: Request): Promise<Response> {
  const data = await dataset();
  const url = new URL(request.url);
  const path = url.pathname.slice(url.pathname.indexOf("/api/"));
  const query = Object.fromEntries([...url.searchParams].filter(([, value]) => value !== ""));

  if (request.method === "GET") {
    if (path === "/api/ledger/transactions" && (query.q || query.type)) {
      return answer(200, search(data.answers, query));
    }
    const found =
      data.answers[key("GET", path, query)] ??
      // An unknown description has no suggestion: the answer without a title applies.
      (path === "/api/ledger/transactions/suggestion"
        ? data.answers[key("GET", path, {})]
        : undefined);
    return found === undefined ? answer(404, { detail: "Not found" }) : answer(200, found);
  }

  if (request.method === "POST" && path === "/api/plan/sheet") {
    const body = (await request.json()) as { months?: number; changes?: unknown };
    const wanted = canonical(body.changes ?? { cells: {}, manual: [] });
    const sheet = data.sheets.find(
      (item) => item.months === (body.months ?? 6) && canonical(item.changes) === wanted,
    );
    if (sheet) return answer(200, sheet.answer);
  }

  const message = currentMessages().demo.readOnly;
  return answer(403, { detail: message, errors: { __all__: [message] } });
}
