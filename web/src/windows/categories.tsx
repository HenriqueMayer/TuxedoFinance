import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useId, useState } from "react";
import { type Category, categoriesQuery, useDeleteCategory, useSaveCategory } from "../data/ledger";
import { useMessages } from "../i18n";
import { fieldMessages, formMessage } from "../lib/errors";
import { autofocus } from "../ui/Window";

type Kind = "" | "EXPENSE" | "INCOME";

/** The list of categories, with a form to add one and a form in each row to change it. */
export function CategoriesWindow() {
  const t = useMessages();
  const { data: categories } = useSuspenseQuery(categoriesQuery);
  const create = useSaveCategory();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("EXPENSE");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { name, transaction_type: kind || null, parent_id: null },
      { onSuccess: () => setName("") },
    );
  }

  const createMessage = formMessage(create.error, t) ?? fieldMessages(create.error, "name")[0];
  return (
    <div className="grid gap-5">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3" noValidate>
        <label className="grid min-w-40 flex-1 gap-1.5 text-sm font-medium">
          {t.categories.newName}
          <input
            {...autofocus}
            className="field font-normal"
            value={name}
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <KindSelect value={kind} onChange={setKind} label={t.entry.type} />
        <button type="submit" className="button-primary" disabled={create.isPending}>
          {t.common.add}
        </button>
        {createMessage && (
          <p role="alert" className="w-full text-sm text-negative">
            {createMessage}
          </p>
        )}
      </form>
      <ul className="divide-y divide-line border-y border-line">
        {categories.map((category) => (
          <CategoryRow key={category.id} category={category} />
        ))}
      </ul>
    </div>
  );
}

function CategoryRow(props: { category: Category }) {
  const t = useMessages();
  const { category } = props;
  const save = useSaveCategory(category.id);
  const remove = useDeleteCategory();
  const [name, setName] = useState(category.name);
  const [kind, setKind] = useState<Kind>(category.transaction_type ?? "");
  const changed = name.trim() !== category.name || kind !== (category.transaction_type ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ name, transaction_type: kind || null, parent_id: category.parent_id });
  }

  const message =
    formMessage(save.error, t) ??
    fieldMessages(save.error, "name")[0] ??
    fieldMessages(save.error, "transaction_type")[0] ??
    formMessage(remove.error, t);
  return (
    <li className="py-2">
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2" noValidate>
        <input
          aria-label={`${t.categories.name}: ${category.name}`}
          className="field min-w-32 flex-1"
          value={name}
          maxLength={100}
          onChange={(event) => setName(event.target.value)}
        />
        <KindSelect
          value={kind}
          onChange={setKind}
          label={`${t.entry.type}: ${category.name}`}
          hideLabel
        />
        {changed ? (
          <button type="submit" className="button-primary" disabled={save.isPending}>
            {t.common.save}
          </button>
        ) : (
          <button
            type="button"
            className="button-quiet"
            disabled={remove.isPending}
            aria-label={`${t.common.delete}: ${category.name}`}
            onClick={() => remove.mutate(category.id)}
          >
            {t.common.delete}
          </button>
        )}
      </form>
      {message && (
        <p role="alert" className="mt-1 text-sm text-negative">
          {message}
        </p>
      )}
    </li>
  );
}

function KindSelect(props: {
  value: Kind;
  onChange: (kind: Kind) => void;
  label: string;
  hideLabel?: boolean;
}) {
  const t = useMessages();
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className={props.hideLabel ? "sr-only" : "text-sm font-medium"}>
        {props.label}
      </label>
      <select
        id={id}
        className="field w-auto"
        value={props.value}
        onChange={(event) => props.onChange(event.target.value as Kind)}
      >
        <option value="EXPENSE">{t.entry.expense}</option>
        <option value="INCOME">{t.entry.income}</option>
        <option value="">{t.categories.any}</option>
      </select>
    </div>
  );
}
