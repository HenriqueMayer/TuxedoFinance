/** English messages. This file defines the message keys; other languages must match it. */
export const en = {
  app: { name: "Tuxedo Finance" },
  nav: {
    main: "Main",
    home: "Home",
    transactions: "Transactions",
    wallet: "Wallet",
    plan: "Plan",
    settings: "Settings",
    signOut: "Sign out",
  },
  window: { close: "Close", expand: "Expand to full size", restore: "Restore size" },
  common: { comingSoon: "This area is being built." },
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
  settings: {
    title: "Settings",
    language: "Language",
    theme: "Theme",
    light: "Light",
    dark: "Dark",
    currency: "Currency of totals",
    currencyHelp: "Used for consolidated totals only. Each record keeps its own currency.",
    dateFormat: "Date order",
    signedInAs: "Signed in as",
    saveFailed: "The change was not saved. Try again.",
  },
};

export type Messages = typeof en;
