import { useState } from "react";
import { MissionBoard } from "../components/MissionBoard";
import { ScoutChat } from "../components/ScoutChat";
import { AgentPromptEditor } from "../components/AgentPromptEditor";
import { LlmStatusPill } from "../components/LlmStatusPill";
import { LlmStatusPanel } from "../components/LlmStatusPanel";

type OpenPanel = "controls" | "prompt" | "llm" | null;

export default function ScoutHQ() {
  const [open, setOpen] = useState<OpenPanel>(null);

  const toggle = (p: OpenPanel) => setOpen(open === p ? null : p);

  return (
    <div className="scout-hq">
      <div className="scout-toolbar">
        <button
          type="button"
          className={`btn ${open === "controls" ? "active" : ""}`}
          onClick={() => toggle("controls")}
        >
          Scout controls
        </button>
        <button
          type="button"
          className={`btn ${open === "prompt" ? "active" : ""}`}
          onClick={() => toggle("prompt")}
        >
          Edit prompt
        </button>
        <LlmStatusPill active={open === "llm"} onClick={() => toggle("llm")} />
      </div>

      <ScoutChat />

      {open === "llm" ? <LlmStatusPanel onClose={() => setOpen(null)} /> : null}

      {open === "controls" ? (
        <aside className="scout-drawer">
          <button
            type="button"
            className="scout-drawer-close"
            aria-label="Close scout controls"
            onClick={() => setOpen(null)}
          >
            ✕
          </button>
          <MissionBoard />
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
          <AgentPromptEditor agentName="discovery" />
        </aside>
      ) : null}
    </div>
  );
}
