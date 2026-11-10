import { useQuery } from "@tanstack/react-query";
import { type AccountRow, type CreditCardRow, type InvoiceRow, walletQuery } from "../data/wallet";
import { useMessages } from "../i18n";
import type { Messages } from "../i18n/en";
import { formatDate } from "../lib/dates";
import { formatAmount } from "../lib/money";
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
    </>
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
