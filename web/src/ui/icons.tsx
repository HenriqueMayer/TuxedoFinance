import type { ReactNode } from "react";

/** Line icons drawn for this product. Decorative: the control supplies the name. */
function Icon(props: { children: ReactNode; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={props.size ?? 22}
      height={props.size ?? 22}
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

// Marks inside a small button. They are 16px and take the color of the text.

export const PlusIcon = () => (
  <Icon size={16}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const ChevronRightIcon = () => (
  <Icon size={16}>
    <path d="m9 6 6 6-6 6" />
  </Icon>
);

export const ChevronLeftIcon = () => (
  <Icon size={16}>
    <path d="m15 6-6 6 6 6" />
  </Icon>
);

export const ChevronDownIcon = () => (
  <Icon size={16}>
    <path d="m6 9 6 6 6-6" />
  </Icon>
);

export const ChartIcon = () => (
  <Icon size={16}>
    <path d="M4 20h16M7 16.5v-5M12 16.5v-10M17 16.5v-7" />
  </Icon>
);

export const CloseIcon = () => (
  <Icon size={16}>
    <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
  </Icon>
);

export const MoreIcon = () => (
  <Icon size={16}>
    <path d="M5.5 12h.01M12 12h.01M18.5 12h.01" strokeWidth="2.75" />
  </Icon>
);

export const UploadIcon = () => (
  <Icon size={16}>
    <path d="M12 16V4M7.5 8.5 12 4l4.5 4.5M5 19.5h14" />
  </Icon>
);

export const DownloadIcon = () => (
  <Icon size={16}>
    <path d="M12 4v12M7.5 11.5 12 16l4.5-4.5M5 19.5h14" />
  </Icon>
);

export const UndoIcon = () => (
  <Icon size={16}>
    <path d="M8.5 5 4.5 9l4 4" />
    <path d="M4.5 9h9a5.5 5.5 0 0 1 0 11H10" />
  </Icon>
);

export const TrashIcon = () => (
  <Icon size={16}>
    <path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5" />
  </Icon>
);

export const PencilIcon = () => (
  <Icon size={16}>
    <path d="m5 19 1-4L16.5 4.5l3 3L9 18z" />
  </Icon>
);

export const CheckIcon = () => (
  <Icon size={16}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
);

export const ExchangeIcon = () => (
  <Icon size={16}>
    <path d="M4.5 8.5h14M15 5l3.5 3.5L15 12M19.5 15.5h-14M9 12l-3.5 3.5L9 19" />
  </Icon>
);

export const TagIcon = () => (
  <Icon size={16}>
    <path d="M4.5 12.5V5.5a1 1 0 0 1 1-1h7l7 7.5-7.5 7.5z" />
    <circle cx="9" cy="9" r="1.25" />
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
