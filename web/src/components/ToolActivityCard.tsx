import type { ScoutMessage } from "../api/types";

export function ToolActivityCard({ message }: { message: ScoutMessage }) {
  const result = message.tool_result as { result?: unknown; error?: string | null } | null;
  const error = result?.error ?? null;
  return (
    <div className={`tool-card ${error ? "tool-card-error" : ""}`}>
      <div className="tool-card-title">
        <span className="tool-card-icon">⚙</span> {message.tool_name ?? "tool"}
      </div>
      {message.tool_args ? <pre>{JSON.stringify(message.tool_args, null, 2)}</pre> : null}
      {error ? (
        <p className="tool-card-error-text"><span>Error: </span>{error}</p>
      ) : (
        <pre>{JSON.stringify(result?.result ?? null, null, 2)}</pre>
      )}
    </div>
  );
}
