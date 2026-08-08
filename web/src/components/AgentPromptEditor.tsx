import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAgentPrompt, saveAgentPrompt } from "../api/agent-chat";

export function AgentPromptEditor({ agentName }: { agentName: string }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);

  const { data: prompt } = useQuery({
    queryKey: ["agent-prompt", agentName],
    queryFn: () => fetchAgentPrompt(agentName),
  });

  const save = useMutation({
    mutationFn: () => saveAgentPrompt(agentName, draft ?? ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-prompt", agentName] });
      setFlash("Prompt saved.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  if (!prompt) return <p className="muted">Loading prompt…</p>;

  return (
    <div className="panel">
      <h3>System prompt (agent.md)</h3>
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="form-row">
          <textarea
            rows={12}
            value={draft ?? prompt.content}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="# System Prompt — Agent"
          />
        </div>
        <button className="btn" type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save prompt"}
        </button>
      </form>
      <p className="muted" style={{ marginTop: 8 }}>
        This edits <code>prompts/{agentName}.md</code> in the repo. If a DB profile
        override exists, it takes precedence; edit the Mission prompt above to clear it.
      </p>
    </div>
  );
}
