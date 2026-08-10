import { useQuery } from "@tanstack/react-query";
import { fetchLlmStatus } from "../api/llm";

export function LlmStatusPanel({ onClose }: { onClose: () => void }) {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["llm-status"],
    queryFn: fetchLlmStatus,
    refetchInterval: 30_000,
    retry: 1,
  });

  return (
    <aside className="scout-drawer">
      <button type="button" className="scout-drawer-close" aria-label="Close LLM status" onClick={onClose}>
        ✕
      </button>
      <h3>LLM provider</h3>

      {isLoading ? <p className="muted">Checking LLM status…</p> : null}

      {isError ? (
        <div className="llm-status-row">
          <p className="flash err">Could not reach the LLM status endpoint.</p>
        </div>
      ) : null}

      {data ? (
        <div className="llm-status">
          <div className="llm-status-row">
            <span className="muted">Provider</span>
            <span className="llm-status-value">
              <span className={`llm-dot ${data.reachable ? "ok" : "err"}`} />
              {data.provider}
            </span>
          </div>
          <div className="llm-status-row">
            <span className="muted">API base URL</span>
            <span className="llm-status-value">{data.base_url || "—"}</span>
          </div>
          <div className="llm-status-row">
            <span className="muted">API key</span>
            <span className="llm-status-value">{data.api_key_set ? "Set" : "Not set"}</span>
          </div>
          <div className="llm-status-row">
            <span className="muted">Reachable</span>
            <span className="llm-status-value">{data.reachable ? "Yes" : "No"}</span>
          </div>
          {data.detail ? (
            <div className="llm-status-row">
              <span className="muted">Detail</span>
              <span className="llm-status-value">{data.detail}</span>
            </div>
          ) : null}
          <div className="llm-status-row">
            <span className="muted">Checked</span>
            <span className="llm-status-value">
              {data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : "—"}
            </span>
          </div>
        </div>
      ) : null}

      <h3>Models</h3>
      {data?.models.length ? (
        <table className="data">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {data.models.map((m) => (
              <tr key={m.agent}>
                <td>{m.agent}</td>
                <td className="muted">{m.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No model aliases configured.</p>
      )}

      <button className="btn" type="button" onClick={() => refetch()} disabled={isFetching}>
        {isFetching ? "Checking…" : "Refresh"}
      </button>
    </aside>
  );
}
