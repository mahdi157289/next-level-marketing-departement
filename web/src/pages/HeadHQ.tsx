import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { dispatchAgent } from "../api/agents";
import { fetchAgentRuns, fetchPipelineRun, fetchPipelineRuns } from "../api/runs";
import type { AgentRun } from "../api/types";
import { AgentChat } from "../components/AgentChat";
import { AgentPromptEditor } from "../components/AgentPromptEditor";
import { StatusBadge } from "../components/StatusBadge";
import { LlmStatusPill } from "../components/LlmStatusPill";
import { LlmStatusPanel } from "../components/LlmStatusPanel";

interface PlanJson {
  seed_query?: string | null;
  max_search_results?: number | null;
  tools?: unknown;
  skill_gaps?: unknown;
  tool_reasons?: Record<string, string> | null;
  insights?: string | null;
  rationale?: string | null;
}

function planOf(run: AgentRun | undefined): PlanJson | null {
  if (!run?.output_json) return null;
  return run.output_json as PlanJson;
}

function listLabel(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "string" && v.trim()) return v;
  return "—";
}

function reasonsLabel(reasons: Record<string, string> | null | undefined): string {
  if (!reasons || !Object.keys(reasons).length) return "—";
  return Object.entries(reasons)
    .map(([tool, why]) => `${tool}: ${why}`)
    .join("\n");
}

type OpenPanel = "plan" | "prompt" | "runs" | "llm" | null;

export default function HeadHQ() {
  const qc = useQueryClient();
  const [goal, setGoal] = useState("");
  const [dispatchRunId, setDispatchRunId] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);
  const [open, setOpen] = useState<OpenPanel>(null);

  const headRuns = useQuery({
    queryKey: ["head-runs"],
    queryFn: () => fetchAgentRuns("head", undefined, 20),
    refetchInterval: 10000,
  });

  const pipelineRuns = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => fetchPipelineRuns(20),
    refetchInterval: 10000,
  });

  const pipelineRun = useQuery({
    queryKey: ["head-plan", dispatchRunId],
    queryFn: () => fetchPipelineRun(dispatchRunId!),
    enabled: !!dispatchRunId,
    refetchInterval: 2000,
  });

  const plan = planOf(
    headRuns.data?.find((r) => r.pipeline_run_id === dispatchRunId),
  );

  const dispatch = useMutation({
    mutationFn: (seed: string) => dispatchAgent("head", { seed_query: seed }),
    onSuccess: (run) => {
      setGoal("");
      setDispatchRunId(run.id);
      setFlash(`Head dispatched (${run.id.slice(0, 8)}…).`);
      setFlashErr(false);
      qc.invalidateQueries({ queryKey: ["head-runs"] });
      qc.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (goal.trim()) dispatch.mutate(goal.trim());
  };

  const toggle = (p: OpenPanel) => setOpen(open === p ? null : p);

  return (
    <div className="scout-hq head-hq">
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}

      <div className="scout-toolbar">
        <button
          type="button"
          className={`btn ${open === "plan" ? "active" : ""}`}
          onClick={() => toggle("plan")}
        >
          Plan console
        </button>
        <button
          type="button"
          className={`btn ${open === "prompt" ? "active" : ""}`}
          onClick={() => toggle("prompt")}
        >
          Edit prompt
        </button>
        <button
          type="button"
          className={`btn ${open === "runs" ? "active" : ""}`}
          onClick={() => toggle("runs")}
        >
          Recent runs
        </button>
        <LlmStatusPill active={open === "llm"} onClick={() => toggle("llm")} />
      </div>

      <AgentChat agentName="head" label="Head" />

      {open === "llm" ? <LlmStatusPanel onClose={() => setOpen(null)} /> : null}

      {open === "plan" ? (
        <aside className="scout-drawer">
          <button
            type="button"
            className="scout-drawer-close"
            aria-label="Close plan console"
            onClick={() => setOpen(null)}
          >
            ✕
          </button>
          <h3>Plan console</h3>
          <form onSubmit={onSubmit}>
            <div className="form-row">
              <input
                type="text"
                placeholder="Goal (e.g. find web agencies in Tunisia)"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                minLength={2}
              />
            </div>
            <button className="btn" type="submit" disabled={dispatch.isPending}>
              {dispatch.isPending ? "Dispatching…" : "Make plan"}
            </button>
          </form>

          {dispatchRunId ? (
            <div className="plan-card">
              {pipelineRun.isPending && dispatchRunId ? (
                <p className="muted">Dispatching head agent…</p>
              ) : null}
              {pipelineRun.data?.status === "failed" ? (
                <p className="flash err">Dispatch failed.</p>
              ) : null}
              {plan ? (
                <div>
                  <p>
                    <strong>Seed query:</strong> {plan.seed_query ?? "—"}
                  </p>
                  <p>
                    <strong>Search budget:</strong> {plan.max_search_results != null ? plan.max_search_results : "—"}
                  </p>
                  <p>
                    <strong>Tools:</strong> {listLabel(plan.tools)}
                  </p>
                  <p>
                    <strong>Tool reasons:</strong>
                  </p>
                  <pre className="plan-pre">{reasonsLabel(plan.tool_reasons)}</pre>
                  <p>
                    <strong>Skill gaps:</strong> {listLabel(plan.skill_gaps)}
                  </p>
                  {plan.insights ? (
                    <div>
                      <p><strong>Insights</strong></p>
                      <p className="muted">{plan.insights}</p>
                    </div>
                  ) : null}
                  <p>
                    <strong>Rationale:</strong> {plan.rationale ?? "—"}
                  </p>
                </div>
              ) : (
                <p className="muted">
                  Plan will appear here once the head agent finishes ({pipelineRun.data?.status ?? "running"}).
                </p>
              )}
            </div>
          ) : (
            <p className="muted">Dispatch a goal to see its plan here.</p>
          )}
        </aside>
      ) : null}

      {open === "prompt" ? (
        <aside className="scout-drawer">
          <button
            type="button"
            className="scout-drawer-close"
            aria-label="Close prompt editor"
            onClick={() => setOpen(null)}
          >
            ✕
          </button>
          <AgentPromptEditor agentName="head" />
        </aside>
      ) : null}

      {open === "runs" ? (
        <aside className="scout-drawer scout-drawer-wide">
          <button
            type="button"
            className="scout-drawer-close"
            aria-label="Close recent runs"
            onClick={() => setOpen(null)}
          >
            ✕
          </button>
          <h3>Recent head plans</h3>
          {!headRuns.data?.length ? (
            <p className="muted">No head runs yet.</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Seed</th>
                  <th>Status</th>
                  <th>Tools</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {headRuns.data.map((r) => {
                  const p = planOf(r);
                  return (
                    <tr key={r.id}>
                      <td>{r.input_summary ?? p?.seed_query ?? "—"}</td>
                      <td><StatusBadge status={r.status} /></td>
                      <td>{listLabel(p?.tools)}</td>
                      <td className="muted">{p?.rationale ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <h3>Recent runs</h3>
          {!pipelineRuns.data?.length ? (
            <p className="muted">No pipeline runs yet.</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Trigger</th>
                  <th>Seed</th>
                  <th>Status</th>
                  <th>Runs</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {pipelineRuns.data.map((r) => (
                  <tr key={r.id}>
                    <td>{r.trigger ?? "—"}</td>
                    <td>{r.seed_query ?? "—"}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>{r.agent_run_count ?? 0}</td>
                    <td className="muted">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </aside>
      ) : null}
    </div>
  );
}
