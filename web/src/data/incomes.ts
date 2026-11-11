import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type Income = Schemas["IncomeOut"];
export type IncomeInput = Schemas["IncomeIn"];
export type SalarySplit = Schemas["SalarySplitOut"];

// The key starts with "home": an entry or a Wallet change refreshes the incomes too.
export const incomesQuery = queryOptions({
  queryKey: ["home", "plan", "incomes"],
  queryFn: () => unwrap(api.GET("/api/incomes")),
});

/** The parts of an income are entries: balances, lists and Home blocks follow them. */
function useIncomeChanged() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["transactions", "wallet", "home"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );
}

/** Create an income, or change the one with this id. */
export function useSaveIncome(id?: number) {
  const changed = useIncomeChanged();
  return useMutation({
    mutationFn: (body: IncomeInput) =>
      id === undefined
        ? unwrap(api.POST("/api/incomes", { body }))
        : unwrap(
            api.PUT("/api/incomes/{income_id}", { params: { path: { income_id: id } }, body }),
          ),
    onSuccess: changed,
  });
}

export function useDeleteIncome(id: number) {
  const changed = useIncomeChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/api/incomes/{income_id}", { params: { path: { income_id: id } } })),
    onSuccess: changed,
  });
}

/** The advance and the rest of a CLT salary. The server calculates them; nothing is saved. */
export function useSalarySplit() {
  return useMutation({
    mutationFn: (body: Schemas["SalarySplitIn"]) =>
      unwrap(api.POST("/api/plan/tools/salary-split", { body })),
  });
}
