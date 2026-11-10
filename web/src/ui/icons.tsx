import type { ReactNode } from "react";

/** Line icons drawn for this product. Decorative: the control supplies the name. */
function Icon(props: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {props.children}
    </svg>
  );
}

export const HomeIcon = () => (
  <Icon>
    <path d="M4 11.5 12 4l8 7.5" />
    <path d="M6.5 10v9.5h11V10" />
  </Icon>
);

export const TransactionsIcon = () => (
  <Icon>
    <path d="M5 7h14M5 12h14M5 17h9" />
  </Icon>
);

export const WalletIcon = () => (
  <Icon>
    <rect x="3.5" y="6" width="17" height="13" rx="2.5" />
    <path d="M3.5 10.5h17M15.5 15h2" />
  </Icon>
);

export const PlanIcon = () => (
  <Icon>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3.5" />
  </Icon>
);

export const SettingsIcon = () => (
  <Icon>
    <path d="M5 8h9M18 8h1M5 16h1M10 16h9" />
    <circle cx="16" cy="8" r="2" />
    <circle cx="8" cy="16" r="2" />
  </Icon>
);

/** The bow tie of the brand, as a mark for the navigation frame. */
export function Mark() {
  return (
    <svg viewBox="0 0 32 20" width="32" height="20" aria-hidden="true">
      <path d="M2 3.5 13 8v4L2 16.5zM30 3.5 19 8v4l11 4.5z" fill="var(--color-accent)" />
      <rect x="13" y="6.5" width="6" height="7" rx="1.5" fill="currentColor" />
    </svg>
  );
}
