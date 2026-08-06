export function ScoutActiveBadge({ active }: { active: boolean }) {
  return (
    <span className={`scout-pill ${active ? "on" : "off"}`}>
      {active ? "Scout active" : "Scout idle"}
    </span>
  );
}
