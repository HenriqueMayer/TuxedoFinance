import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

export type Transaction = components["schemas"]["TransactionOut"];
export type TransactionInput = components["schemas"]["TransactionIn"];
export type Category = components["schemas"]["CategoryOut"];
export type CategoryInput = components["schemas"]["CategoryIn"];
export type Instrument = components["schemas"]["InstrumentOut"];

export type TransactionFilters = {
  month?: string;
  q?: string;
  type?: string;
  page?: number;
};

export const categoriesQuery = queryOptions({
  queryKey: ["categories"],
  queryFn: () => unwrap(api.GET("/api/ledger/categories")),
  staleTime: 5 * 60_000,
});

export const instrumentsQuery = queryOptions({
  queryKey: ["instruments"],
  queryFn: () => unwrap(api.GET("/api/banking/instruments")),
  staleTime: 5 * 60_000,
});

export function transactionsQuery(filters: TransactionFilters) {
  return queryOptions({
    queryKey: ["transactions", "list", filters],
    queryFn: () => unwrap(api.GET("/api/ledger/transactions", { params: { query: filters } })),
    // A changed filter keeps the previous rows on screen until the new ones
    // arrive, so the page does not collapse and the scroll position holds.
    placeholderData: keepPreviousData,
  });
}

export function transactionQuery(id: number) {
  return queryOptions({
    queryKey: ["transactions", "one", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/ledger/transactions/{transaction_id}", {
          params: { path: { transaction_id: id } },
        }),
      ),
  });
}

/** The category and instrument of the latest entry with this title. */
export function suggestion(title: string) {
  return unwrap(api.GET("/api/ledger/transactions/suggestion", { params: { query: { title } } }));
}

/**
 * Everything that a changed transaction can change. Balances, invoices and
 * Home blocks derive from transactions, so their queries are refreshed too.
 */
function useLedgerChanged() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["transactions", "wallet", "home"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

export function useSaveTransaction(id?: number) {
  const changed = useLedgerChanged();
  return useMutation({
    mutationFn: (body: TransactionInput) =>
      unwrap(
        id === undefined
          ? api.POST("/api/ledger/transactions", { body })
          : api.PUT("/api/ledger/transactions/{transaction_id}", {
              params: { path: { transaction_id: id } },
              body,
            }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteTransaction(id: number) {
  const changed = useLedgerChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/ledger/transactions/{transaction_id}", {
          params: { path: { transaction_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["AccountIn"]) =>
      unwrap(api.POST("/api/banking/accounts", { body })),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["instruments"] }),
        queryClient.invalidateQueries({ queryKey: ["wallet"] }),
      ]),
  });
}

export function useSaveCategory(id?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CategoryInput) =>
      unwrap(
        id === undefined
          ? api.POST("/api/ledger/categories", { body })
          : api.PUT("/api/ledger/categories/{category_id}", {
              params: { path: { category_id: id } },
              body,
            }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["categories"] }),
        // A renamed category changes the rows that show it.
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
      ]),
  });
}

export function useDeleteCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE("/api/ledger/categories/{category_id}", {
          params: { path: { category_id: id } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });
}
