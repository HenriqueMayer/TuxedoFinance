import { queryOptions, useMutation } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useWalletChanged } from "./wallet";

type Schemas = components["schemas"];
export type Position = Schemas["PositionOut"];
export type PositionDetail = Schemas["PositionDetailOut"];
export type Operation = Schemas["OperationOut"];

// The keys start with "wallet": a Wallet change refreshes the investments too.
export const positionsQuery = queryOptions({
  queryKey: ["wallet", "positions"],
  queryFn: () => unwrap(api.GET("/api/investments/positions")),
});

export function positionQuery(id: number) {
  return queryOptions({
    queryKey: ["wallet", "position", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/investments/positions/{position_id}", {
          params: { path: { position_id: id } },
        }),
      ),
  });
}

export function useCreatePosition() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["PositionIn"]) =>
      unwrap(api.POST("/api/investments/positions", { body })),
    onSuccess: changed,
  });
}

export function useChangePosition(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["PositionEdit"]) =>
      unwrap(
        api.PUT("/api/investments/positions/{position_id}", {
          params: { path: { position_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useDeletePosition(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/investments/positions/{position_id}", {
          params: { path: { position_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}

/** Record what the investment is worth today: a balance, or a unit price. */
export function useSetValue(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (value: string) =>
      unwrap(
        api.POST("/api/investments/positions/{position_id}/value", {
          params: { path: { position_id: id } },
          body: { value },
        }),
      ),
    onSuccess: changed,
  });
}

export function useRecordOperation(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["OperationIn"]) =>
      unwrap(
        api.POST("/api/investments/positions/{position_id}/operations", {
          params: { path: { position_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteOperation() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE("/api/investments/operations/{operation_id}", {
          params: { path: { operation_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}
