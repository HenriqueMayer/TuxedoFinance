import { queryOptions, useMutation } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useWalletChanged } from "./wallet";

type Schemas = components["schemas"];
export type Program = Schemas["ProgramOut"];
export type ProgramDetail = Schemas["ProgramDetailOut"];
export type LoyaltyEntry = Schemas["EntryOut"];

// The keys start with "wallet": a redemption changes an account, and a Wallet change refreshes these.
export const programsQuery = queryOptions({
  queryKey: ["wallet", "programs"],
  queryFn: () => unwrap(api.GET("/api/loyalty/programs")),
});

export function programQuery(id: number) {
  return queryOptions({
    queryKey: ["wallet", "program", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/loyalty/programs/{program_id}", { params: { path: { program_id: id } } }),
      ),
  });
}

/** Create a program, or change the one with `id`. */
export function useSaveProgram(id?: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["ProgramIn"]) =>
      unwrap(
        id === undefined
          ? api.POST("/api/loyalty/programs", { body })
          : api.PUT("/api/loyalty/programs/{program_id}", {
              params: { path: { program_id: id } },
              body,
            }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteProgram(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/loyalty/programs/{program_id}", { params: { path: { program_id: id } } }),
      ),
    onSuccess: changed,
  });
}

export function useRecordPoints(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["EntryIn"]) =>
      unwrap(
        api.POST("/api/loyalty/programs/{program_id}/entries", {
          params: { path: { program_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

/** Points leave the program and money enters an account. */
export function useRedeem(id: number) {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (body: Schemas["RedemptionIn"]) =>
      unwrap(
        api.POST("/api/loyalty/programs/{program_id}/redemptions", {
          params: { path: { program_id: id } },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useUndoPoints() {
  const changed = useWalletChanged();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(api.DELETE("/api/loyalty/entries/{entry_id}", { params: { path: { entry_id: id } } })),
    onSuccess: changed,
  });
}
