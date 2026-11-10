import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./api/client";
import type { components } from "./api/schema";

export type Session = components["schemas"]["SessionOut"];

/** The session of the browser. Reading it also sets the CSRF cookie. */
export const sessionQuery = queryOptions({
  queryKey: ["session"],
  queryFn: () => unwrap(api.GET("/api/session")),
  staleTime: Number.POSITIVE_INFINITY, // Changes only through the mutations below.
});

export function useSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["LoginIn"]) =>
      unwrap(api.POST("/api/session/login", { body })),
    onSuccess: (session) => queryClient.setQueryData(sessionQuery.queryKey, session),
  });
}

export function useSignUp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["SignupIn"]) =>
      unwrap(api.POST("/api/session/signup", { body })),
    onSuccess: (session) => queryClient.setQueryData(sessionQuery.queryKey, session),
  });
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/session/logout")),
    // Another user must never see cached data of this one.
    onSuccess: () => queryClient.clear(),
  });
}

/** The owner's date order. "DMY" until the session is known. */
export function useDateOrder(): "DMY" | "MDY" {
  return useQuery(sessionQuery).data?.preferences?.date_format ?? "DMY";
}

/**
 * Save preferences. The choice shows at once and is restored if the server
 * refuses it, so a control answers the press that changed it.
 */
export function useSavePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["PreferencesIn"]) =>
      unwrap(api.PATCH("/api/session/preferences", { body })),
    onMutate: (body) => {
      const before = queryClient.getQueryData(sessionQuery.queryKey);
      const changes = Object.fromEntries(Object.entries(body).filter(([, value]) => value != null));
      queryClient.setQueryData(sessionQuery.queryKey, (session) =>
        session?.preferences
          ? { ...session, preferences: { ...session.preferences, ...changes } }
          : session,
      );
      return { before };
    },
    onError: (_error, _body, context) =>
      queryClient.setQueryData(sessionQuery.queryKey, context?.before),
    onSuccess: (preferences) =>
      queryClient.setQueryData(sessionQuery.queryKey, (session) =>
        session ? { ...session, preferences } : session,
      ),
  });
}
