import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
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
