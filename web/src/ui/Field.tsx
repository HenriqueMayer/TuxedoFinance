import { type ReactNode, useId } from "react";

/**
 * A labelled control with its errors. `children` receives the attributes that
 * connect the control to the label and to the error text.
 */
export function Field(props: {
  label: string;
  errors?: string[];
  help?: string;
  className?: string;
  children: (control: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby": string | undefined;
  }) => ReactNode;
}) {
  const id = useId();
  const errors = props.errors ?? [];
  const described = [errors.length > 0 && `${id}-error`, props.help && `${id}-help`]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={`grid gap-1.5 ${props.className ?? ""}`}>
      <label htmlFor={id} className="text-sm font-medium">
        {props.label}
      </label>
      {props.children({
        id,
        "aria-invalid": errors.length > 0,
        "aria-describedby": described || undefined,
      })}
      {props.help && (
        <p id={`${id}-help`} className="text-sm text-muted">
          {props.help}
        </p>
      )}
      {errors.length > 0 && (
        <p id={`${id}-error`} className="text-sm text-negative">
          {errors.join(" ")}
        </p>
      )}
    </div>
  );
}
