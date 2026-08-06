import { ScoutActiveBadge } from "./ScoutActiveBadge";
import { StatusDot } from "./StatusDot";

export function Topbar({
  title,
  scoutActive,
  statusOk,
}: {
  title: string;
  scoutActive: boolean;
  statusOk: boolean;
}) {
  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right">
        <ScoutActiveBadge active={scoutActive} />
        <StatusDot ok={statusOk} />
      </div>
    </header>
  );
}
