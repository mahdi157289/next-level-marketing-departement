import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchMissions } from "../api/scout";
import { finishScout, startScout } from "../api/agents";
import { StatusBadge } from "./StatusBadge";

export function MissionBoard() {
  const qc = useQueryClient();
  const [seed, setSeed] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);

  const { data: missions } = useQuery({
    queryKey: ["missions"],
    queryFn: fetchMissions,
    refetchInterval: 10000,
  });

  const start = useMutation({
    mutationFn: () => startScout(seed, 5),
    onSuccess: () => {
      setSeed("");
      setFlash("Scout started.");
      setFlashErr(false);
      qc.invalidateQueries({ queryKey: ["missions"] });
      qc.invalidateQueries({ queryKey: ["scout-status"] });
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const finish = useMutation({
    mutationFn: () => finishScout(),
    onSuccess: () => {
      setFlash("Finish requested.");
      setFlashErr(false);
      qc.invalidateQueries({ queryKey: ["missions"] });
      qc.invalidateQueries({ queryKey: ["scout-status"] });
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  return (
    <div className="mission-board">
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}

      <div className="panel">
        <h3>Start Scout</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <div className="form-row">
            <input
              type="text"
              placeholder="Seed query (e.g. agencies Tunisia)"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              required
              minLength={2}
            />
          </div>
          <button className="btn" type="submit" disabled={start.isPending}>Start</button>
          <button className="btn danger" type="button" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish</button>
        </form>
      </div>

      <div className="panel">
        <h3>Missions</h3>
        {!missions?.length ? (
          <p className="muted">No missions yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Seed</th>
                <th>Status</th>
                <th>Runs</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => (
                <tr key={m.id}>
                  <td>{m.seed_query ?? "—"}</td>
                  <td><StatusBadge status={m.status} /></td>
                  <td>{m.agent_run_count ?? 0}</td>
                  <td className="muted">{m.started_at ? new Date(m.started_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
