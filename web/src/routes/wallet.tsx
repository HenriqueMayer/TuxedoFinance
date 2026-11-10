import { useQuery } from "@tanstack/react-query";
import { type Position, positionsQuery } from "../data/investments";
import { type AccountRow, type CreditCardRow, type InvoiceRow, walletQuery } from "../data/wallet";
import { useLanguage, useMessages } from "../i18n";
import type { Messages } from "../i18n/en";
import { formatDate } from "../lib/dates";
import { formatAmount, formatQuantity } from "../lib/money";
import { useDateOrder } from "../session";
import { OpenWindow } from "../windows/host";

/** What the owner has and owes: accounts by bank, each with its cards. Every card opens a window. */
export function WalletPage() {
  const t = useMessages();
  const { data, isPending, isError, refetch } = useQuery(walletQuery);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t.nav.wallet}</h1>
        <div className="flex flex-wrap gap-2">
          {data && data.banks.length > 0 && (
            <>
              <OpenWindow w="transfer" className="button-quiet">
                {t.wallet.transfer}
              </OpenWindow>
              <OpenWindow w="new-card" className="button-quiet">
                {t.wallet.newCard}
              </OpenWindow>
            </>
          )}
          <OpenWindow w="new-account" className="button-primary">
            {t.wallet.newAccount}
          </OpenWindow>
        </div>
      </div>

      {isPending && <p className="py-10 text-muted">{t.common.loading}</p>}
      {isError && (
        <div role="alert" className="grid justify-items-start gap-3 py-10">
          <p>{t.common.loadFailed}</p>
          <button type="button" className="button-quiet" onClick={() => refetch()}>
            {t.common.retry}
          </button>
        </div>
      )}
      {data && data.banks.length === 0 && (
        <div className="grid justify-items-start gap-2 py-10">
          <p className="text-lg font-medium">{t.wallet.empty}</p>
          <p className="text-muted">{t.wallet.emptyHelp}</p>
        </div>
      )}
      {data && data.banks.length > 0 && (
        <>
          <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3">
            {data.totals.map((total) => (
              <div key={total.currency}>
                <dt className="text-sm text-muted">{t.wallet.total}</dt>
                <dd className="amount text-3xl font-semibold">
                  {formatAmount(total.balance, total.currency)}
                </dd>
              </div>
            ))}
          </dl>
          {data.banks.map((bank) => (
            <section key={bank.id} className="mt-8">
              <h2 className="flex items-center gap-2 border-b border-line pb-2 font-medium">
                <span
                  aria-hidden="true"
                  className="size-2.5 rounded-full"
                  style={{ background: bank.color }}
                />
                {bank.name}
              </h2>
              <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {bank.accounts.map((account) => (
                  <Account key={account.id} account={account} />
                ))}
              </ul>
            </section>
          ))}
        </>
      )}
      {data && <Investments />}
    </>
  );
}

/** The investments of the owner, after the accounts. Each one opens its window. */
function Investments() {
  const t = useMessages();
  const { data } = useQuery(positionsQuery);
  if (!data) return null;
  const active = data.positions.filter((position) => !position.is_archived);
  const archived = data.positions.filter((position) => position.is_archived);
  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-2">
        <h2 className="font-medium">{t.invest.title}</h2>
        {data.positions.length > 0 && (
          <p className="text-sm">
            <span className="text-muted">{t.invest.total} </span>
            <span className="amount font-semibold">{formatAmount(data.total, data.currency)}</span>
          </p>
        )}
      </div>
      {!data.complete && (
        <p className="mt-3 text-sm text-muted">
          {t.home.worth.incomplete(data.missing_currencies.join(", "))}{" "}
          <OpenWindow w="rates" className="link">
            {t.rates.add}
          </OpenWindow>
        </p>
      )}
      <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {active.map((position) => (
          <li key={position.id}>
            <Investment position={position} />
          </li>
        ))}
        <li>
          <OpenWindow
            w="new-investment"
            className="flex h-full min-h-24 items-center justify-center rounded-(--radius-window) border border-dashed border-control p-4 font-medium hover:bg-surface"
          >
            {t.invest.new}
          </OpenWindow>
        </li>
      </ul>
      {archived.length > 0 && (
        <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="text-muted">{t.invest.archived}</span>
          {archived.map((position) => (
            <OpenWindow key={position.id} w={`investment:${position.id}`} className="link">
              {position.name}
            </OpenWindow>
          ))}
        </p>
      )}
    </section>
  );
}

function Investment(props: { position: Position }) {
  const t = useMessages();
  const language = useLanguage();
  const { position } = props;
  const units = position.valuation_mode === "UNITS";
  return (
    <OpenWindow w={`investment:${position.id}`} className={CARD}>
      <span className="block truncate text-sm text-muted">{position.institution_name}</span>
      <span className="block truncate font-medium">{position.name}</span>
      <span className="amount mt-3 block text-xl font-semibold">
        {formatAmount(position.value, position.currency)}
      </span>
      {units && (
        <span className="mt-1 block truncate text-sm text-muted">
          {t.invest.units(formatQuantity(position.quantity ?? "0", language))}
          {!position.has_price && ` · ${t.invest.noPriceShort}`}
        </span>
      )}
    </OpenWindow>
  );
}

const CARD =
  "block rounded-(--radius-window) border border-line bg-surface p-4 transition-shadow hover:shadow-md";

/** An account and, under it, the cards that settle through it. */
function Account(props: { account: AccountRow }) {
  const t = useMessages();
  const { account } = props;
  return (
    <>
      <li>
        <OpenWindow w={`account:${account.id}`} className={CARD}>
          <span className="block text-sm text-muted">{t.wallet.account}</span>
          <span className="block truncate font-medium">{account.name}</span>
          <span
            className={`amount mt-3 block text-xl font-semibold ${Number(account.balance) < 0 ? "text-negative" : ""}`}
          >
            {formatAmount(account.balance, account.currency)}
          </span>
        </OpenWindow>
      </li>
      {account.credit_cards.map((card) => (
        <li key={`credit-${card.id}`}>
          <CreditCard card={card} currency={account.currency} accountName={account.name} />
        </li>
      ))}
    </>
  );
}

function CreditCard(props: { card: CreditCardRow; currency: string; accountName: string }) {
  const t = useMessages();
  const order = useDateOrder();
  const invoice = props.card.next_invoice;
  return (
    <OpenWindow w={`card:${props.card.id}`} className={CARD}>
      <span className="block text-sm text-muted">
        {t.wallet.credit} · {props.accountName}
      </span>
      <span className="block truncate font-medium">{props.card.name}</span>
      {invoice ? (
        <>
          <span className="amount mt-3 block text-xl font-semibold">
            {formatAmount(invoice.remaining, props.currency)}
          </span>
          <span className="mt-1 flex items-center justify-between gap-2 text-sm">
            <span className="text-muted">{t.wallet.due(formatDate(invoice.due_date, order))}</span>
            <StatusLabel invoice={invoice} t={t} />
          </span>
        </>
      ) : (
        <span className="mt-3 block text-muted">{t.wallet.nothingDue}</span>
      )}
    </OpenWindow>
  );
}

/** The state of an invoice in words. Color only adds to the words. */
export function StatusLabel(props: {
  invoice: { status: InvoiceRow["status"] | "AWAITING" };
  t: Messages;
}) {
  const tone =
    props.invoice.status === "OVERDUE" || props.invoice.status === "AWAITING"
      ? "text-negative"
      : props.invoice.status === "PAID"
        ? "text-positive"
        : "text-muted";
  return (
    <span className={`font-medium ${tone}`}>{props.t.wallet.status[props.invoice.status]}</span>
  );
}
