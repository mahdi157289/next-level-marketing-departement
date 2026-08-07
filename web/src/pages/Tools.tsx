import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchToolCatalog } from "../api/agents";
import type { ToolCatalogItem } from "../api/agents";

export default function Tools() {
  const { data: tools } = useQuery<ToolCatalogItem[]>({ queryKey: ["tools"], queryFn: fetchToolCatalog });

  if (!tools?.length) return <p className="muted">No tools registered.</p>;

  return (
    <div>
      <h2>Tools / APIs / MCPs catalog</h2>
      <p className="muted">
        <Link to="/agents">← Agents</Link>
      </p>
      <table className="data">
        <thead>
          <tr>
            <th>Tool</th>
            <th>Label</th>
            <th>Agents</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((t) => (
            <tr key={t.id}>
              <td>
                <code>{t.id}</code>
              </td>
              <td>{t.label}</td>
              <td>{t.agents.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
