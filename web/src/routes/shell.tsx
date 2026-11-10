import { Outlet, useNavigate } from "@tanstack/react-router";
import { useMessages } from "../i18n";
import { useSignOut } from "../session";

/** The frame of every signed-in page. Part 1 replaces this placeholder layout. */
export function Shell() {
  const t = useMessages();
  const navigate = useNavigate();
  const signOut = useSignOut();
  return (
    <div className="min-h-dvh">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <p className="font-semibold">{t.app.name}</p>
        <button
          type="button"
          className="link text-sm"
          onClick={() => signOut.mutate(undefined, { onSuccess: () => navigate({ to: "/login" }) })}
        >
          {t.nav.signOut}
        </button>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  );
}

export function HomePage() {
  const t = useMessages();
  return (
    <>
      <h1 className="text-2xl font-semibold">{t.nav.home}</h1>
      <p className="mt-2 text-muted">{t.home.empty}</p>
    </>
  );
}
