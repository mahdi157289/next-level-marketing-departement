import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router-dom";
import { apiGet } from "../api/client";
import type { ScoutStatus } from "../api/types";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/scout-hq": "Scout HQ",
  "/leads": "Leads",
  "/runs": "Runs",
  "/agents": "Agents",
};

export function Layout() {
  const { pathname } = useLocation();
  const { data: status } = useQuery({
    queryKey: ["scout-status"],
    queryFn: () => apiGet<ScoutStatus>("/api/scout/status"),
    refetchInterval: 10000,
    retry: 0,
  });
  const title = TITLES[pathname] ?? "NextLevel";
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main">
        <Topbar
          title={title}
          scoutActive={Boolean(status?.scout_active)}
          statusOk={Boolean(status)}
        />
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
