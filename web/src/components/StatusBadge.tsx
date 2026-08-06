export function StatusBadge({ status }: { status: string | null }) {
  return <span className={`badge ${status ?? ""}`}>{status ?? "—"}</span>;
}
