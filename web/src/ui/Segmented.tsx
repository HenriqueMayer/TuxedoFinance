import { useId } from "react";

/**
 * A choice among a few options, shown as one row. It is a native radio group:
 * arrow keys move the choice and Tab leaves the group.
 */
export function Segmented<T extends string>(props: {
  label: string;
  value: T;
  /** `short` is a label for a narrow screen, where the full one does not fit. */
  options: { value: T; label: string; short?: string }[];
  onChange: (value: T) => void;
  /** The label and the choice share one line, as a row of a list of settings. */
  inline?: boolean;
  /** With `inline`: the label is read and not shown. */
  hideLabel?: boolean;
}) {
  const name = useId();
  const choices = (
    <div className="inline-flex w-fit rounded-(--radius-control) border border-control p-0.5">
      {props.options.map((option) => (
        <label
          key={option.value}
          className={`cursor-pointer rounded-[calc(var(--radius-control)-2px)] px-3 text-sm transition-colors duration-150 hover:bg-ink/5 has-checked:bg-ink has-checked:text-sheet has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent ${
            props.inline ? "py-1" : "py-1.5"
          }`}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={props.value === option.value}
            onChange={() => props.onChange(option.value)}
            className="sr-only"
          />
          {option.short ? (
            <>
              <span className="sm:hidden">{option.short}</span>
              <span className="max-sm:hidden">{option.label}</span>
            </>
          ) : (
            option.label
          )}
        </label>
      ))}
    </div>
  );
  if (props.inline) {
    return (
      <div
        role="radiogroup"
        aria-labelledby={`${name}-label`}
        className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2"
      >
        <span id={`${name}-label`} className={props.hideLabel ? "sr-only" : "text-sm font-medium"}>
          {props.label}
        </span>
        {choices}
      </div>
    );
  }
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{props.label}</legend>
      {choices}
    </fieldset>
  );
}
