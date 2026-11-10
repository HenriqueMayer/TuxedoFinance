/**
 * A bar that compares an amount with its limit or its target. The length only
 * compares; the text beside the bar carries the values.
 */
export function Meter(props: { value: string; total: string }) {
  const total = Number(props.total);
  const share = total > 0 ? Math.min(100, Math.max(0, (Number(props.value) / total) * 100)) : 0;
  return (
    <span aria-hidden="true" className="block h-2 rounded-full bg-line">
      <span className="block h-full rounded-full bg-ink" style={{ width: `${share}%` }} />
    </span>
  );
}
