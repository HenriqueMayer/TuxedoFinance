import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ApiError } from "./api/client";
import { currentLanguage, setLanguage } from "./i18n";
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

setLanguage(currentLanguage());

const router = createAppRouter(queryClient);

const root = document.getElementById("root");
if (!root) throw new Error("The entry document has no #root element.");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
