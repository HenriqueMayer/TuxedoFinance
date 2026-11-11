import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type MonthPlan = Schemas["MonthPlanOut"];
export type Budget = Schemas["Budget"];
export type Goal = Schemas["GoalOut"];
export type GoalSource = Schemas["GoalSource"];

// The keys start with "home": an entry or a Wallet change refreshes the plan too.
export const planQuery = queryOptions({
  queryKey: ["home", "plan", "month"],
  queryFn: () => unwrap(api.GET("/api/plan/month")),
});

export const goalsQuery = queryOptions({
  queryKey: ["home", "plan", "goals"],
  queryFn: () => unwrap(api.GET("/api/plan/goals")),
});

/** A plan change alters the Plan page and the Home blocks that read it. */
function usePlanChanged() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["home"] });
}

/** Set the limit of the month, or the budget of a category, from the current month on. */
export function useSetLimit() {
  const changed = usePlanChanged();
  return useMutation({
    mutationFn: (body: { amount: string | null; category_id?: number }) =>
      unwrap(api.PUT("/api/plan/limit", { body })),
    onSuccess: changed,
  });
}

export function useCreateGoal() {
  const changed = usePlanChanged();
  return useMutation({
    mutationFn: (body: Schemas["GoalIn"]) => unwrap(api.POST("/api/plan/goals", { body })),
    onSuccess: changed,
  });
}

export function useChangeGoal(id: number) {
  const changed = usePlanChanged();
  return useMutation({
    mutationFn: (body: Schemas["GoalEdit"]) =>
      unwrap(api.PUT("/api/plan/goals/{goal_id}", { params: { path: { goal_id: id } }, body })),
    onSuccess: changed,
  });
}

export function useDeleteGoal(id: number) {
  const changed = usePlanChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/api/plan/goals/{goal_id}", { params: { path: { goal_id: id } } })),
    onSuccess: changed,
  });
}

/** Reserve a part of a balance for the goal. Zero removes the reservation. */
export function useReserve(id: number) {
  const changed = usePlanChanged();
  return useMutation({
    mutationFn: (body: Schemas["ReservationIn"]) =>
      unwrap(
        api.PUT("/api/plan/goals/{goal_id}/reservations", {
          params: { path: { goal_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

// The months ahead, the sheet and the calculators

export type Forecast = Schemas["ForecastOut"];
export type Sheet = Schemas["SheetOut"];
export type SheetChanges = Required<Schemas["SheetChanges"]>;
export type SheetMonths = 6 | 12;
export type Salary = Schemas["SalaryOut"];
export type Growth = Schemas["GrowthOut"];

export const forecastQuery = queryOptions({
  queryKey: ["home", "plan", "forecast"],
  queryFn: () => unwrap(api.GET("/api/plan/forecast")),
});

/** The sheet for a set of changes. The server calculates it; nothing is saved. */
export function sheetQuery(months: SheetMonths, changes: SheetChanges) {
  return queryOptions({
    queryKey: ["home", "plan", "sheet", months, changes],
    queryFn: () => unwrap(api.POST("/api/plan/sheet", { body: { months, changes } })),
    // A change keeps the table on screen until the new values arrive.
    placeholderData: keepPreviousData,
  });
}

export const savedSheetsQuery = queryOptions({
  queryKey: ["plan-sheets"],
  queryFn: () => unwrap(api.GET("/api/plan/sheets")),
});

export function savedSheetQuery(id: number) {
  return queryOptions({
    queryKey: ["plan-sheets", id],
    queryFn: () =>
      unwrap(api.GET("/api/plan/sheets/{sheet_id}", { params: { path: { sheet_id: id } } })),
  });
}

/** Save the changes of a sheet under a name: a new saved sheet, or the one with `id`. */
export function useSaveSheet(id?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["SavedSheetIn"]) =>
      unwrap(
        id === undefined
          ? api.POST("/api/plan/sheets", { body })
          : api.PUT("/api/plan/sheets/{sheet_id}", { params: { path: { sheet_id: id } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plan-sheets"] }),
  });
}

export function useDeleteSheet(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/api/plan/sheets/{sheet_id}", { params: { path: { sheet_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plan-sheets"] }),
  });
}

export function useSalary() {
  return useMutation({
    mutationFn: (body: Schemas["SalaryIn"]) => unwrap(api.POST("/api/plan/tools/salary", { body })),
  });
}

export function useGrowth() {
  return useMutation({
    mutationFn: (body: Schemas["GrowthIn"]) => unwrap(api.POST("/api/plan/tools/growth", { body })),
  });
}

// The closing of a month

export type Closing = Schemas["ClosingOut"];
export type ClosingAccount = Schemas["ClosingAccount"];

/** The closing review of a month ("YYYY-MM"), or of the month that waits for it. */
export function closingQuery(month?: string) {
  return queryOptions({
    queryKey: ["home", "plan", "closing", month ?? "next"],
    queryFn: () => unwrap(api.GET("/api/plan/closing", { params: { query: { month } } })),
  });
}

/** A closing change can alter a balance, the limit and what Home asks for. */
function useClosingChanged() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["home", "wallet"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
    );
}

export function useClosingBalance() {
  const changed = useClosingChanged();
  return useMutation({
    mutationFn: (body: Schemas["ClosingBalanceIn"]) =>
      unwrap(api.PUT("/api/plan/closing/balances", { body })),
    onSuccess: changed,
  });
}

export function useClosingAdjust() {
  const changed = useClosingChanged();
  return useMutation({
    mutationFn: (body: Schemas["ClosingAdjustIn"]) =>
      unwrap(api.POST("/api/plan/closing/adjustments", { body })),
    onSuccess: changed,
  });
}

export function useClosingUnadjust() {
  const changed = useClosingChanged();
  return useMutation({
    mutationFn: (body: Schemas["ClosingAccountIn"]) =>
      unwrap(api.DELETE("/api/plan/closing/adjustments", { body })),
    onSuccess: changed,
  });
}

export function useCloseMonth() {
  const changed = useClosingChanged();
  return useMutation({
    mutationFn: (body: Schemas["CloseIn"]) => unwrap(api.POST("/api/plan/closing", { body })),
    onSuccess: changed,
  });
}

export function useReopenMonth() {
  const changed = useClosingChanged();
  return useMutation({
    mutationFn: (body: Schemas["ClosingMonth"]) =>
      unwrap(api.DELETE("/api/plan/closing", { body })),
    onSuccess: changed,
  });
}
