import { MissionBoard } from "../components/MissionBoard";
import { ScoutChat } from "../components/ScoutChat";

export default function ScoutHQ() {
  return (
    <div className="scout-hq">
      <MissionBoard />
      <ScoutChat />
    </div>
  );
}
