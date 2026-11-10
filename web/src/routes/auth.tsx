import { Link, useNavigate } from "@tanstack/react-router";
import { type FormEvent, type ReactNode, useId } from "react";
import { useMessages } from "../i18n";
import { fieldMessages, formMessage } from "../lib/errors";
import { type Session, useSignIn, useSignUp } from "../session";

function Field(props: {
  label: string;
  name: string;
  type?: string;
  autoComplete: string;
  errors?: string[];
}) {
  const id = useId();
  const errors = props.errors ?? [];
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {props.label}
      </label>
      <input
        id={id}
        name={props.name}
        type={props.type ?? "text"}
        autoComplete={props.autoComplete}
        required
        aria-invalid={errors.length > 0}
        aria-describedby={errors.length > 0 ? `${id}-error` : undefined}
        className="field"
      />
      {errors.length > 0 && (
        <p id={`${id}-error`} className="text-sm text-danger">
          {errors.join(" ")}
        </p>
      )}
    </div>
  );
}

function AuthPage(props: { title: string; children: ReactNode }) {
  const t = useMessages();
  return (
    <main className="grid min-h-dvh place-items-center p-4">
      <div className="w-full max-w-sm grid gap-6">
        <p className="text-sm font-semibold tracking-wide text-muted">{t.app.name}</p>
        <h1 className="text-2xl font-semibold">{props.title}</h1>
        {props.children}
      </div>
    </main>
  );
}

function values(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
}

export function LoginPage(props: { redirect?: string; session: Session }) {
  const t = useMessages();
  const navigate = useNavigate();
  const signIn = useSignIn();

  function submit(event: FormEvent<HTMLFormElement>) {
    const { username = "", password = "" } = values(event);
    signIn.mutate(
      { username, password },
      { onSuccess: () => navigate({ to: props.redirect ?? "/", replace: true }) },
    );
  }

  const message = formMessage(signIn.error, t);
  return (
    <AuthPage title={t.login.title}>
      <form onSubmit={submit} className="grid gap-4" noValidate>
        <Field label={t.login.username} name="username" autoComplete="username" />
        <Field
          label={t.login.password}
          name="password"
          type="password"
          autoComplete="current-password"
        />
        {message && (
          <p role="alert" className="text-sm text-danger">
            {message}
          </p>
        )}
        <button type="submit" className="button-primary" disabled={signIn.isPending}>
          {t.login.submit}
        </button>
      </form>
      {props.session.allow_signups && (
        <p className="text-sm text-muted">
          {t.login.noAccount}{" "}
          <Link to="/signup" className="link">
            {t.login.signUp}
          </Link>
        </p>
      )}
    </AuthPage>
  );
}

export function SignupPage(props: { session: Session }) {
  const t = useMessages();
  const navigate = useNavigate();
  const signUp = useSignUp();

  function submit(event: FormEvent<HTMLFormElement>) {
    const { username = "", email = "", password = "" } = values(event);
    signUp.mutate(
      { username, email, password },
      { onSuccess: () => navigate({ to: "/", replace: true }) },
    );
  }

  const message = formMessage(signUp.error, t);
  return (
    <AuthPage title={t.signup.title}>
      {props.session.allow_signups ? (
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <Field
            label={t.login.username}
            name="username"
            autoComplete="username"
            errors={fieldMessages(signUp.error, "username")}
          />
          <Field
            label={t.signup.email}
            name="email"
            type="email"
            autoComplete="email"
            errors={fieldMessages(signUp.error, "email")}
          />
          <Field
            label={t.login.password}
            name="password"
            type="password"
            autoComplete="new-password"
            errors={fieldMessages(signUp.error, "password")}
          />
          {message && (
            <p role="alert" className="text-sm text-danger">
              {message}
            </p>
          )}
          <button type="submit" className="button-primary" disabled={signUp.isPending}>
            {t.signup.submit}
          </button>
        </form>
      ) : (
        <p className="text-muted">{t.signup.closed}</p>
      )}
      <p className="text-sm text-muted">
        {t.signup.haveAccount}{" "}
        <Link to="/login" className="link">
          {t.login.submit}
        </Link>
      </p>
    </AuthPage>
  );
}
