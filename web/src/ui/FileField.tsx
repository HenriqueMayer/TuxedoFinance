import { useRef, useState } from "react";
import { useMessages } from "../i18n";
import { UploadIcon } from "./icons";

/**
 * A file of the owner's computer, for a form. The browser's own control is
 * kept for the keyboard and for the form, and is not shown: its words follow
 * the language of the browser, not of the interface.
 */
export function FileField(props: {
  id?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  name: string;
  /** The kinds of file that can be chosen, as the `accept` of an input. */
  accept: string;
}) {
  const t = useMessages();
  const input = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  return (
    <div className="field flex items-center gap-3 py-1.5 pl-1.5 has-focus-visible:outline-2 has-focus-visible:outline-accent has-focus-visible:outline-offset-2">
      <input
        ref={input}
        id={props.id}
        aria-invalid={props["aria-invalid"]}
        aria-describedby={props["aria-describedby"]}
        type="file"
        name={props.name}
        accept={props.accept}
        className="sr-only"
        onChange={(event) => setName(event.target.files?.[0]?.name ?? "")}
      />
      {/* The input above answers the keyboard; this button is for the pointer. */}
      <button
        type="button"
        tabIndex={-1}
        className="action shrink-0"
        onClick={() => input.current?.click()}
      >
        <UploadIcon />
        {t.common.chooseFile}
      </button>
      <span className={`min-w-0 truncate text-sm ${name ? "" : "text-muted"}`}>
        {name || t.common.noFile}
      </span>
    </div>
  );
}
