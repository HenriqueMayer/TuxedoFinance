import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type Wallet = Schemas["WalletOut"];
export type AccountRow = Schemas["AccountRow"];
export type CreditCardRow = Schemas["CreditCardRow"];
export type InvoiceRow = Schemas["InvoiceRow"];
export type Invoice = Schemas["InvoiceOut"];

export const walletQuery = queryOptions({
  queryKey: ["wallet", "overview"],
  queryFn: () => unwrap(api.GET("/api/banking/wallet")),
});

export function accountQuery(id: number) {
  return queryOptions({
    queryKey: ["wallet", "account", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/banking/accounts/{account_id}", { params: { path: { account_id: id } } }),
      ),
  });
}

export function cardQuery(id: number) {
  return queryOptions({
    queryKey: ["wallet", "card", id],
    queryFn: () =>
      unwrap(api.GET("/api/banking/credit-cards/{card_id}", { params: { path: { card_id: id } } })),
  });
}

export function invoiceQuery(id: number) {
  return queryOptions({
    queryKey: ["wallet", "invoice", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/banking/invoices/{invoice_id}", { params: { path: { invoice_id: id } } }),
      ),
  });
}

/** A Wallet change can alter balances, the instruments of an entry and the rows that name them. */
export function useWalletChanged() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["wallet", "instruments", "transactions", "home"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useChangeAccount(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["AccountChange"]) =>
      unwrap(
        api.PUT("/api/banking/accounts/{account_id}", {
          params: { path: { account_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteAccount(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/banking/accounts/{account_id}", { params: { path: { account_id: id } } }),
      ),
    onSuccess: changed,
  });
}

export function useCreateCreditCard() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["CreditCardIn"]) =>
      unwrap(api.POST("/api/banking/credit-cards", { body })),
    onSuccess: changed,
  });
}

export function useCreateDebitCard() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["CardIn"]) => unwrap(api.POST("/api/banking/debit-cards", { body })),
    onSuccess: changed,
  });
}

export function useChangeCreditCard(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["CreditCardChange"]) =>
      unwrap(
        api.PUT("/api/banking/credit-cards/{card_id}", { params: { path: { card_id: id } }, body }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteCreditCard(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/banking/credit-cards/{card_id}", { params: { path: { card_id: id } } }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteDebitCard() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE("/api/banking/debit-cards/{card_id}", { params: { path: { card_id: id } } }),
      ),
    onSuccess: changed,
  });
}

export function usePayInvoice(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["PaymentIn"]) =>
      unwrap(
        api.POST("/api/banking/invoices/{invoice_id}/payments", {
          params: { path: { invoice_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useUndoPayment() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE("/api/banking/invoice-payments/{payment_id}", {
          params: { path: { payment_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}

export function useTransfer() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["TransferIn"]) =>
      unwrap(api.POST("/api/banking/transfers", { body })),
    onSuccess: changed,
  });
}

export function useUndoTransfer() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE("/api/banking/transfers/{transfer_id}", {
          params: { path: { transfer_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}
