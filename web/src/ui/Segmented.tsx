import { useId } from "react";

/**
 * A choice among a few options, shown as one row. It is a native radio group:
 * arrow keys move the choice and Tab leaves the group.
 */
export function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{props.label}</legend>
      <div className="inline-flex w-fit rounded-(--radius-control) border border-control p-0.5">
        {props.options.map((option) => (
          <label
            key={option.value}
            className="cursor-pointer rounded-[calc(var(--radius-control)-2px)] px-3 py-1.5 text-sm has-checked:bg-ink has-checked:text-sheet has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={props.value === option.value}
              onChange={() => props.onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
