import { useAgentChat } from "./useAgentChat";

export function useScoutChat(threadId: string | null, onTurnDone?: () => void, onTurnError?: () => void) {
  return useAgentChat("discovery", threadId, onTurnDone, onTurnError);
}
