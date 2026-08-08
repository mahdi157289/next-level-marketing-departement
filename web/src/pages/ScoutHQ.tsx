import { MissionBoard } from "../components/MissionBoard";
import { ScoutChat } from "../components/ScoutChat";
import { AgentPromptEditor } from "../components/AgentPromptEditor";

export default function ScoutHQ() {
  return (
    <div className="scout-hq">
      <MissionBoard />
      <ScoutChat />
      <AgentPromptEditor agentName="discovery" />
    </div>
  );
}
