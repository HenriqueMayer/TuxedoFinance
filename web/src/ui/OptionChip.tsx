import { useState } from "react";

/**
 * An option of a form that is on or off: a chip, dark while it is on. It
 * works with `on` and `onChange`, or inside a form with `name`, where an
 * option that is on has the value "on". `help` says what the option does.
 */
export function OptionChip(props: {
  label: string;
  name?: string;
  on?: boolean;
  defaultOn?: boolean;
  onChange?: (on: boolean) => void;
  help?: string;
}) {
  const [own, setOwn] = useState(props.defaultOn ?? false);
  const on = props.on ?? own;
  return (
    <div className="grid justify-items-start gap-1.5">
      <button
        type="button"
        className="chip"
        aria-pressed={on}
        onClick={() => {
          setOwn(!on);
          props.onChange?.(!on);
        }}
      >
        {props.label}
      </button>
      {props.name && on && <input type="hidden" name={props.name} value="on" />}
      {props.help && <p className="text-sm text-muted">{props.help}</p>}
    </div>
  );
}
