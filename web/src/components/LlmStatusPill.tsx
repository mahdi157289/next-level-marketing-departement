import { useQuery } from "@tanstack/react-query";
import { fetchLlmStatus } from "../api/llm";

function dotClass(status: { reachable?: boolean; isLoading: boolean; isError: boolean }): string {
  if (status.isLoading || status.isError) return "llm-dot pending";
  return status.reachable ? "llm-dot ok" : "llm-dot err";
}

export function LlmStatusPill({ active, onClick }: { active: boolean; onClick: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["llm-status"],
    queryFn: fetchLlmStatus,
    refetchInterval: 30_000,
    retry: 1,
  });

  const label = data?.provider ?? "LLM";

  return (
    <button
      type="button"
      className={`btn llm-pill ${active ? "active" : ""}`}
      onClick={onClick}
      title={data ? `${data.provider} — ${data.reachable ? "reachable" : "unreachable"}` : "LLM status"}
    >
      <span className={dotClass({ reachable: data?.reachable, isLoading, isError })} />
      {label}
    </button>
  );
}
