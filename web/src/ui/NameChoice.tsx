import { useState } from "react";
import { useMessages } from "../i18n";
import { Select } from "./Select";
import { autofocus } from "./Window";

const NEW = "\u0000new";

/**
 * A name that is one of the owner's existing names or a new one: the bank
 * of an account, the institution of an investment. The existing names are
 * the choices of a select, and its last choice opens a field for a new
 * name. Without an existing name there is only the field. The form reads
 * the name from `name`.
 */
export function NameChoice(props: {
  /** The attributes that `Field` gives to its control. */
  control: { id: string; "aria-invalid": boolean; "aria-describedby": string | undefined };
  name: string;
  options: string[];
  defaultValue?: string;
  /** The words of the last choice: "Another bank…". */
  other: string;
  /** What the field of a new name is called for a screen reader. */
  otherLabel: string;
  placeholder?: string;
  /** The window focuses this control when it opens. */
  focus?: boolean;
}) {
  const t = useMessages();
  const { options } = props;
  const given = props.defaultValue ?? "";
  const [choice, setChoice] = useState(
    options.includes(given) ? given : given ? NEW : options.length === 1 ? (options[0] ?? "") : "",
  );
  const [typed, setTyped] = useState(options.includes(given) ? "" : given);

  if (options.length === 0) {
    return (
      <input
        {...props.control}
        {...(props.focus ? autofocus : {})}
        name={props.name}
        className="field"
        defaultValue={given}
        placeholder={props.placeholder}
        autoComplete="off"
      />
    );
  }
  return (
    <>
      <Select
        {...props.control}
        value={choice}
        onChange={setChoice}
        placeholder={t.common.choose}
        options={[
          ...options.map((name) => ({ value: name, label: name })),
          { value: NEW, label: props.other },
        ]}
      />
      {choice === NEW && (
        <input
          {...autofocus}
          aria-label={props.otherLabel}
          className="field"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          placeholder={props.placeholder}
          autoComplete="off"
        />
      )}
      <input type="hidden" name={props.name} value={choice === NEW ? typed : choice} />
    </>
  );
}
