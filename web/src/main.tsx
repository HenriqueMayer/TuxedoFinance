import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ApiError } from "./api/client";
import { currentLanguage, setLanguage, useLanguage } from "./i18n";
import { createAppRouter } from "./router";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // A refused or invalid request does not succeed on a second attempt.
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400) && count < 2,
    },
  },
});

if (import.meta.env.MODE === "demo") {
  // The data must be there before the first render: it also names the day shown as today.
  await (await import("./demo/fetch")).prepareDemo();
}

setLanguage(currentLanguage());

const router = createAppRouter(queryClient);

/** The demonstration has one data file for each language: another language reads again. */
function DemoLanguage() {
  const language = useLanguage();
  const client = useQueryClient();
  // biome-ignore lint/correctness/useExhaustiveDependencies: the language is the trigger.
  useEffect(() => {
    client.invalidateQueries();
  }, [language, client]);
  return null;
}

const root = document.getElementById("root");
if (!root) throw new Error("The entry document has no #root element.");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {import.meta.env.MODE === "demo" && <DemoLanguage />}
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
