import { keepPreviousData, queryOptions } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";

export type Home = components["schemas"]["HomeOut"];
export type MonthResult = components["schemas"]["MonthResult"];
export type CategorySpending = components["schemas"]["CategorySpending"];
export type DueRow = components["schemas"]["DueRow"];
export type TrendRow = components["schemas"]["TrendRow"];
export type WorthMonth = components["schemas"]["WorthMonth"];
export type HomeBlock = components["schemas"]["PreferencesOut"]["home_blocks"][number];

/** Every block that Home can show, in the default order. */
export const HOME_BLOCKS: HomeBlock[] = ["left", "spending", "due", "worth", "goals"];

export const homeQuery = queryOptions({
  queryKey: ["home", "blocks"],
  queryFn: () => unwrap(api.GET("/api/reports/home")),
});

export function monthQuery(month: string | undefined) {
  return queryOptions({
    queryKey: ["home", "month", month ?? "current"],
    queryFn: () => unwrap(api.GET("/api/reports/month", { params: { query: { month } } })),
    // Moving to another month keeps the previous one on screen until the new one arrives.
    placeholderData: keepPreviousData,
  });
}

export const worthQuery = queryOptions({
  queryKey: ["home", "worth"],
  queryFn: () => unwrap(api.GET("/api/reports/net-worth")),
});
