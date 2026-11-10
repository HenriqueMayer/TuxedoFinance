import { useSuspenseQuery } from "@tanstack/react-query";
import { type FormEvent, useId, useRef, useState } from "react";
import {
  type Category,
  categoriesQuery,
  useDeleteCategory,
  useExportCategories,
  useImportCategories,
  useSaveCategory,
} from "../data/ledger";
import { useMessages } from "../i18n";
import { fieldMessages, formMessage } from "../lib/errors";
import { DownloadIcon, PlusIcon, TrashIcon, UploadIcon } from "../ui/icons";
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
          <PlusIcon />
          {t.common.add}
        </button>
        {createMessage && (
          <p role="alert" className="w-full text-sm text-negative">
            {createMessage}
          </p>
        )}
      </form>
      <Transfer count={categories.length} />
      <ul className="divide-y divide-line border-y border-line">
        {categories.map((category) => (
          <CategoryRow key={category.id} category={category} />
        ))}
      </ul>
    </div>
  );
}

/** Take the categories to a file, or bring them from one: to another installation, or a list made elsewhere. */
function Transfer(props: { count: number }) {
  const t = useMessages();
  const file = useRef<HTMLInputElement>(null);
  const load = useImportCategories();
  const save = useExportCategories();
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{t.categories.count(props.count)}</p>
        <div className="flex flex-wrap gap-2">
          <input
            ref={file}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label={t.categories.importFile}
            tabIndex={-1}
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) load.mutate(chosen);
              event.target.value = ""; // The same file can be chosen again.
            }}
          />
          <button
            type="button"
            className="action"
            disabled={load.isPending}
            onClick={() => file.current?.click()}
          >
            <UploadIcon />
            {t.categories.import}
          </button>
          <button
            type="button"
            className="action"
            disabled={save.isPending || props.count === 0}
            onClick={() => save.mutate()}
          >
            <DownloadIcon />
            {t.categories.export}
          </button>
        </div>
      </div>
      {load.data && (
        <p role="status" className="text-sm text-muted">
          {t.categories.imported(load.data.created, load.data.existing)}
        </p>
      )}
      {(load.error || save.error) && (
        <p role="alert" className="text-sm text-negative">
          {fieldMessages(load.error, "content")[0] ??
            formMessage(load.error, t) ??
            formMessage(save.error, t)}
        </p>
      )}
      <p className="text-sm text-muted">{t.categories.fileHelp}</p>
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
      {/* On a phone the name takes the first line; the type and the button share the second. */}
      <form
        onSubmit={submit}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]"
        noValidate
      >
        <input
          aria-label={`${t.categories.name}: ${category.name}`}
          className="field col-span-2 sm:col-span-1"
          value={name}
          maxLength={100}
          onChange={(event) => setName(event.target.value)}
        />
        <KindSelect
          value={kind}
          onChange={setKind}
          label={`${t.entry.type}: ${category.name}`}
          hideLabel
          fill
        />
        {changed ? (
          <button type="submit" className="button-primary" disabled={save.isPending}>
            {t.common.save}
          </button>
        ) : (
          <button
            type="button"
            className="button-quiet px-3"
            disabled={remove.isPending}
            aria-label={`${t.common.delete}: ${category.name}`}
            title={t.common.delete}
            onClick={() => remove.mutate(category.id)}
          >
            <TrashIcon />
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
  /** The select takes the width of its cell on a phone. */
  fill?: boolean;
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
        className={props.fill ? "field w-full sm:w-auto" : "field w-auto"}
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
