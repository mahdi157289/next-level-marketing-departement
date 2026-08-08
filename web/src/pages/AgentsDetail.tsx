import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  deleteProviderKey,
  fetchAgent,
  fetchProviders,
  finishScout,
  startScout,
  upsertProviderKey,
  updateAgent,
} from "../api/agents";
import type { ProviderInfo } from "../api/types";
import type { ScoutStatus } from "../api/types";
import { apiGet } from "../api/client";
import { AgentChat } from "../components/AgentChat";
import { AgentPromptEditor } from "../components/AgentPromptEditor";

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

      {!isDiscovery ? (
        <>
          <div className="panel">
            <h3>Chat with {agent.display_name}</h3>
            <AgentChat agentName={name} label={agent.display_name} />
          </div>
          <AgentPromptEditor agentName={name} />
        </>
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

      <ProviderKeys agentName={name} />
    </div>
  );
}

function ProviderKeys({ agentName }: { agentName: string }) {
  const qc = useQueryClient();
  const [flash, setFlash] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState({ kind: "openai", name: "OPENAI_API_KEY", value: "" });

  const { data: providers } = useQuery<ProviderInfo[]>({
    queryKey: ["providers", agentName],
    queryFn: () => fetchProviders(agentName),
  });

  const add = useMutation({
    mutationFn: (body: typeof form) => upsertProviderKey(agentName, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers", agentName] });
      setFlash("Key saved (encrypted at rest).");
      setErr(null);
      setForm({ kind: "openai", name: "OPENAI_API_KEY", value: "" });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const del = useMutation({
    mutationFn: (kind: string) => deleteProviderKey(agentName, kind),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers", agentName] });
      setFlash("Key removed.");
      setErr(null);
    },
    onError: (e: Error) => setErr(e.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    add.mutate(form);
  };

  return (
    <div className="panel">
      <h3>Provider API keys (hashed fingerprint shown)</h3>
      {flash ? <div className="flash">{flash}</div> : null}
      {err ? <div className="flash err">{err}</div> : null}

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <label htmlFor="kind">Provider (kind)</label>
          <select id="kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="openai">openai (LLM / embeddings)</option>
            <option value="serpapi">serpapi (search)</option>
            <option value="google_maps">google_maps (places)</option>
            <option value="meta_ads">meta_ads (ad library)</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="name">Key name (label)</label>
          <input id="name" type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </div>
        <div className="form-row">
          <label htmlFor="value">Secret value (stored encrypted — never shown again)</label>
          <input id="value" type="password" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} required minLength={4} />
        </div>
        <button className="btn" type="submit" disabled={add.isPending}>Set key</button>
      </form>

      <table className="data" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Key name</th>
            <th>Fingerprint (sha256)</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(providers ?? []).map((p) => (
            <tr key={p.kind}>
              <td>{p.kind}</td>
              <td>{p.name ?? "—"}</td>
              <td className="muted">{p.fingerprint ? `sha256:${p.fingerprint}` : "—"}</td>
              <td>{p.has_key ? "set" : "not set"}</td>
              <td>
                {p.has_key ? (
                  <button className="btn danger" style={{ fontSize: 12 }} onClick={() => del.mutate(p.kind)} disabled={del.isPending}>
                    Delete
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
