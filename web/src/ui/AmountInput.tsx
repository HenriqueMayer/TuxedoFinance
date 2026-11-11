import {
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
  type Ref,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { amountSeparators, finishedAmount, pastedAmount, typedAmount } from "../lib/money";

type Native = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "defaultValue" | "onChange" | "type" | "inputMode"
>;

/**
 * A field for an amount of money. It writes the amount the way the
 * application shows it, while the owner types: "2000" becomes "2.000", and
 * "2.000,00" when the owner leaves the field.
 *
 * - The two separator keys are different, as the owner chose in Settings:
 *   one groups the thousands and the other starts the decimals. A typed
 *   thousands separator shows at once and stays while its group is typed.
 * - Backspace on a thousands separator that the field wrote deletes the
 *   digit before it. A typed separator and the decimal separator are deleted
 *   alone.
 * - A pasted amount is read with either separator.
 *
 * It works with a value and `onChange`, or inside a form with `name`. A
 * quantity, a unit price, a rate and points are not amounts of money: they
 * keep a plain field.
 */
export function AmountInput(
  props: Native & {
    /** The currency of the amount: it gives the separators. */
    currency: string;
    value?: string;
    defaultValue?: string;
    onChange?: (text: string) => void;
    /** A balance: it can start with a minus sign. */
    signed?: boolean;
    ref?: Ref<HTMLInputElement>;
  },
) {
  const { currency, value, defaultValue, onChange, signed, ref, onBlur, ...native } = props;
  const [own, setOwn] = useState(defaultValue ?? "");
  const text = value ?? own;
  const input = useRef<HTMLInputElement | null>(null);
  // Where the caret goes after the text is written again.
  const caret = useRef<number | null>(null);
  // True while the owner types a thousands separator by hand.
  const byHand = useRef(false);

  // One function for both refs, and the same one on every render: a ref that
  // changes would run the focus of a marked field again.
  const attach = useCallback(
    (element: HTMLInputElement | null) => {
      input.current = element;
      if (typeof ref === "function") ref(element);
      else if (ref) ref.current = element;
    },
    [ref],
  );

  useLayoutEffect(() => {
    const element = input.current;
    if (caret.current !== null && element && document.activeElement === element) {
      element.setSelectionRange(caret.current, caret.current);
    }
    caret.current = null;
  });

  function update(next: string) {
    setOwn(next);
    onChange?.(next);
  }

  function change(event: ChangeEvent<HTMLInputElement>) {
    const { group } = amountSeparators(currency);
    let raw = event.target.value;
    let at = event.target.selectionStart ?? raw.length;
    const native = event.nativeEvent as InputEvent;
    const kind = native.inputType ?? "";
    const typed = kind === "insertText" || kind === "insertCompositionText";
    const digits = (value: string) => value.replace(/\D/g, "");
    const groups = (value: string) => value.split(group).length - 1;

    if (kind.startsWith("delete")) {
      // A thousands separator that the field wrote does not go alone: the key
      // deletes the digit beside it. The decimal separator, and a thousands
      // separator that the owner typed, are deleted as any character.
      const wrote = !byHand.current && groups(raw) < groups(text) && digits(raw) === digits(text);
      if (wrote) {
        const back = kind !== "deleteContentForward";
        const index = back
          ? raw.slice(0, at).search(/\d(?=\D*$)/)
          : at + raw.slice(at).search(/\d/);
        if (index >= 0 && /\d/.test(raw[index] ?? "")) {
          raw = raw.slice(0, index) + raw.slice(index + 1);
          at = index;
        }
      }
    } else if (!typed) {
      // Pasted, dropped or set by a script: the whole text is one amount.
      const read = pastedAmount(raw, currency, signed);
      if (read !== "") {
        byHand.current = false;
        caret.current = read.length;
        update(read);
        return;
      }
    }
    // The two separator keys keep their meaning, as the owner chose in
    // Settings. A thousands separator that the owner types stays where it was
    // typed, until the digits after it complete their group.
    const manual = byHand.current || (typed && native.data === group);
    const next = typedAmount(raw, at, currency, signed, manual);
    byHand.current = next.manual;
    caret.current = next.caret;
    update(next.text);
  }

  function blur(event: FocusEvent<HTMLInputElement>) {
    // The form reads the field first, then the field writes the amount in full.
    onBlur?.(event);
    byHand.current = false;
    const done = finishedAmount(text, currency, signed);
    if (done !== text) update(done);
  }

  return (
    <input
      {...native}
      ref={attach}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={text}
      onChange={change}
      onBlur={blur}
    />
  );
}
