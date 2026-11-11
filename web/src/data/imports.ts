import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type ImportDetail = Schemas["ImportOut"];
export type ImportRow = Schemas["RowOut"];
export type ImportMapping = Schemas["Mapping"];
export type ImportDecision = Schemas["Decision"];

export const importsQuery = queryOptions({
  queryKey: ["imports"],
  queryFn: () => unwrap(api.GET("/api/imports")),
});

export function importQuery(id: number) {
  return queryOptions({
    queryKey: ["imports", id],
    queryFn: () =>
      unwrap(api.GET("/api/imports/{batch_id}", { params: { path: { batch_id: id } } })),
  });
}

/** Each operation answers with the import as it is now; the answer replaces the cached one. */
function useImportAnswer(options: { records?: boolean } = {}) {
  const queryClient = useQueryClient();
  return (detail: ImportDetail) => {
    queryClient.setQueryData(["imports", detail.id], detail);
    queryClient.invalidateQueries({ queryKey: ["imports"], exact: true });
    if (options.records) {
      // A confirmation or an undo changes entries, balances and the reads of Home.
      for (const key of ["transactions", "wallet", "home"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    }
  };
}

/** Read a file as Base64, in pieces that the call stack accepts. */
export async function fileContent(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

export function useUpload() {
  const answer = useImportAnswer();
  return useMutation({
    mutationFn: (body: Schemas["UploadIn"]) => unwrap(api.POST("/api/imports", { body })),
    onSuccess: answer,
  });
}

export function useSetMapping(id: number) {
  const answer = useImportAnswer();
  return useMutation({
    mutationFn: (body: ImportMapping) =>
      unwrap(
        api.PUT("/api/imports/{batch_id}/mapping", { params: { path: { batch_id: id } }, body }),
      ),
    onSuccess: answer,
  });
}

export function useSaveDecisions(id: number) {
  const answer = useImportAnswer();
  return useMutation({
    mutationFn: (decisions: ImportDecision[]) =>
      unwrap(
        api.PUT("/api/imports/{batch_id}/decisions", {
          params: { path: { batch_id: id } },
          body: { decisions },
        }),
      ),
    onSuccess: answer,
  });
}

export function useConfirmImport(id: number) {
  const answer = useImportAnswer({ records: true });
  return useMutation({
    mutationFn: (digest: string) =>
      unwrap(
        api.POST("/api/imports/{batch_id}/confirm", {
          params: { path: { batch_id: id } },
          body: { digest },
        }),
      ),
    onSuccess: answer,
  });
}

export function useUndoImport(id: number) {
  const answer = useImportAnswer({ records: true });
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/imports/{batch_id}/undo", { params: { path: { batch_id: id } } })),
    onSuccess: answer,
  });
}

export function useDiscardImport(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/api/imports/{batch_id}", { params: { path: { batch_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["imports"], exact: true }),
  });
}
