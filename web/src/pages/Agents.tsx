import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAgents } from "../api/agents";

export default function Agents() {
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: fetchAgents });

  if (!agents?.length) return <p className="muted">No agent profiles.</p>;

  return (
    <table className="data">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Model</th>
          <th>Tools</th>
          <th>Default seed</th>
        </tr>
      </thead>
      <tbody>
        {agents.map((a) => (
          <tr key={a.agent_name}>
            <td>
              <Link to={`/agents/${a.agent_name}`}>{a.display_name}</Link>
              <div className="muted">{a.agent_name}</div>
            </td>
            <td>{a.model || "settings default"}</td>
            <td>{a.enabled_tools.join(", ")}</td>
            <td className="muted">{a.default_seed_query || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
