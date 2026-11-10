/** English messages. This file defines the message keys; other languages must match it. */
export const en = {
  app: { name: "Tuxedo Finance" },
  nav: { home: "Home", signOut: "Sign out" },
  login: {
    title: "Sign in",
    username: "Username",
    password: "Password",
    submit: "Sign in",
    noAccount: "No account yet?",
    signUp: "Create one",
  },
  signup: {
    title: "Create your account",
    email: "E-mail",
    submit: "Create account",
    haveAccount: "Already have an account?",
    closed: "Registration is closed on this installation.",
  },
  home: { empty: "Nothing here yet. The next parts add your finances." },
  errors: {
    network: "The server did not answer. Check the connection and try again.",
    unexpected: "Something went wrong. Try again.",
    tooMany: "Too many attempts. Wait a minute and try again.",
  },
  settings: { language: "Language", theme: "Theme", light: "Light", dark: "Dark" },
};

export type Messages = typeof en;
