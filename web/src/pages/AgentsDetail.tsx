import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchAgent, finishScout, startScout, updateAgent } from "../api/agents";
import type { ScoutStatus } from "../api/types";
import { apiGet } from "../api/client";

export default function AgentsDetail() {
  const { name = "" } = useParams();
  const qc = useQueryClient();
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);
  const [seed, setSeed] = useState("");
  const [maxResults, setMaxResults] = useState(5);

  const { data: agent } = useQuery({
    queryKey: ["agent", name],
    queryFn: () => fetchAgent(name),
  });

  const { data: status } = useQuery({
    queryKey: ["scout-status"],
    queryFn: () => apiGet<ScoutStatus>("/api/scout/status"),
    refetchInterval: 8000,
    retry: 0,
  });

  const isDiscovery = name === "discovery";

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateAgent(name, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent", name] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      setFlash("Profile saved.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const start = useMutation({
    mutationFn: () => startScout(seed, maxResults),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scout-status"] });
      setFlash("Scout started.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const finish = useMutation({
    mutationFn: () => finishScout(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scout-status"] });
      setFlash("Finish requested.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  if (!agent) return <p className="muted">Loading…</p>;

  return (
    <div>
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}
      <h2>{agent.display_name}</h2>
      <p className="muted"><Link to="/agents">← Agents</Link></p>

      {isDiscovery ? (
        <div className="panel">
          <h3>Scout controls</h3>
          <p><span className={`scout-pill ${status?.scout_active ? "on" : "off"}`}>{status?.scout_active ? "Scout active" : "Scout idle"}</span></p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate();
            }}
          >
            <div className="form-row">
              <label htmlFor="seed_query">Goal / seed hint (Start scout)</label>
              <input
                id="seed_query"
                type="text"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder={agent.default_seed_query ?? ""}
                required
                minLength={2}
              />
            </div>
            <div className="form-row" style={{ maxWidth: 200 }}>
              <label htmlFor="max_search_results">Max search results</label>
              <input
                id="max_search_results"
                type="number"
                value={maxResults}
                min={1}
                onChange={(e) => setMaxResults(Number(e.target.value))}
              />
            </div>
            <button className="btn" type="submit" disabled={start.isPending}>Start scout</button>
            <button className="btn danger" type="button" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish (cancel)</button>
          </form>
        </div>
      ) : null}

      <div className="panel">
        <h3>Profile</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const tools = Array.from(fd.getAll("enabled_tools")).map(String);
            save.mutate({
              display_name: String(fd.get("display_name") ?? "").trim(),
              mission_prompt: String(fd.get("mission_prompt") ?? "").trim(),
              enabled_tools: tools,
              model: String(fd.get("model") ?? "").trim() || null,
              ...(isDiscovery ? { default_seed_query: String(fd.get("default_seed_query") ?? "").trim() || null } : {}),
            });
          }}
        >
          <div className="form-row">
            <label htmlFor="display_name">Display name</label>
            <input id="display_name" name="display_name" type="text" defaultValue={agent.display_name} />
          </div>
          <div className="form-row">
            <label htmlFor="mission_prompt">Mission prompt</label>
            <textarea id="mission_prompt" name="mission_prompt" rows={8} defaultValue={agent.mission_prompt} />
          </div>
          <div className="form-row">
            <label htmlFor="model">Model override (blank = settings default)</label>
            <input id="model" name="model" type="text" defaultValue={agent.model ?? ""} placeholder="e.g. discovery-model" />
          </div>
          {isDiscovery ? (
            <div className="form-row">
              <label htmlFor="default_seed_query">Default seed query</label>
              <input id="default_seed_query" name="default_seed_query" type="text" defaultValue={agent.default_seed_query ?? ""} />
            </div>
          ) : null}
          <div className="form-row">
            <label>Enabled tools</label>
            {agent.available_tools.map((t) => (
              <label key={t.id} style={{ fontWeight: 400, margin: "0.25rem 0" }}>
                <input
                  type="checkbox"
                  name="enabled_tools"
                  value={t.id}
                  defaultChecked={agent.enabled_tools.includes(t.id)}
                />{" "}
                <strong>{t.id}</strong> — {t.label}
              </label>
            ))}
          </div>
          <button className="btn" type="submit" disabled={save.isPending}>Save profile</button>
        </form>
      </div>
    </div>
  );
}
