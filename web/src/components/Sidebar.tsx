import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Dashboard" },
  { to: "/scout-hq", label: "Scout HQ" },
  { to: "/head-hq", label: "Head HQ" },
  { to: "/leads", label: "Leads" },
  { to: "/runs", label: "Runs" },
  { to: "/agents", label: "Agents" },
  { to: "/tools", label: "Tools catalog" },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">NextLevel</div>
      <nav>
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.to === "/"}>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
