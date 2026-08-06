export function KpiCard({
  label,
  value,
  accent = "violet",
}: {
  label: string;
  value: string | number;
  accent?: "violet" | "cyan";
}) {
  return (
    <div className={`kpi-card kpi-${accent}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}
