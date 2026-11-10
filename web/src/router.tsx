import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { localPath } from "./lib/paths";
import { LoginPage, SignupPage } from "./routes/auth";
import { HomePage, Shell } from "./routes/shell";
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
  component: Shell,
});

const homeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: HomePage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([homeRoute]),
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
