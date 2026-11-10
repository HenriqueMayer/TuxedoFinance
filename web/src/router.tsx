import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { useCallback } from "react";
import { isMonth } from "./lib/dates";
import { localPath } from "./lib/paths";
import { LoginPage, SignupPage } from "./routes/auth";
import { HomePage } from "./routes/home";
import { PlanPage } from "./routes/plan";
import { Shell } from "./routes/shell";
import {
  type TransactionSearch,
  TransactionsPage,
  validateTransactionSearch,
} from "./routes/transactions";
import { WalletPage } from "./routes/wallet";
import { sessionQuery } from "./session";

type RouterContext = { queryClient: QueryClient };

const rootRoute = createRootRouteWithContext<RouterContext>()({ component: Outlet });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search): { redirect?: string } => ({ redirect: localPath(search.redirect) }),
  beforeLoad: async ({ context, search }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery);
    if (session.user) throw redirect({ to: search.redirect ?? "/" });
  },
  loader: ({ context }) => context.queryClient.ensureQueryData(sessionQuery),
  component: function Login() {
    return (
      <LoginPage redirect={loginRoute.useSearch().redirect} session={loginRoute.useLoaderData()} />
    );
  },
});

const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  beforeLoad: async ({ context }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery);
    if (session.user) throw redirect({ to: "/" });
  },
  loader: ({ context }) => context.queryClient.ensureQueryData(sessionQuery),
  component: function Signup() {
    return <SignupPage session={signupRoute.useLoaderData()} />;
  },
});

/** Parent of every page that needs a session. It has no path of its own. */
const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery);
    if (!session.user) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
  },
  // `w` names the open window. It is valid on every signed-in page; see windows/host.tsx.
  validateSearch: (search): { w?: string; wm?: string } => ({
    w: typeof search.w === "string" ? search.w : undefined,
    wm: isMonth(search.wm) ? search.wm : undefined,
  }),
  component: Shell,
});

const homeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: HomePage,
});

const transactionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/transactions",
  validateSearch: validateTransactionSearch,
  component: function Transactions() {
    const search = transactionsRoute.useSearch();
    const navigate = transactionsRoute.useNavigate();
    // A filter change replaces the address and never moves the page.
    const onChange = useCallback(
      (changes: TransactionSearch) =>
        navigate({
          search: (previous) => ({ ...previous, ...changes }),
          replace: true,
          resetScroll: false,
        }),
      [navigate],
    );
    return <TransactionsPage search={search} onChange={onChange} />;
  },
});

const walletRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/wallet",
  component: WalletPage,
});

const planRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/plan",
  component: PlanPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([homeRoute, transactionsRoute, walletRoute, planRoute]),
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
