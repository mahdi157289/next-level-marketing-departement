import { useCallback, useState } from "react";
import { streamAgentTurn } from "../api/agent-chat";

export function useAgentChat(
  agentName: string,
  threadId: string | null,
  onTurnDone?: () => void,
  onTurnError?: () => void,
) {
  const [streaming, setStreaming] = useState(false);
  const [assistantText, setAssistantText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toolCalls, setToolCalls] = useState(0);

  const send = useCallback(
    async (content: string) => {
      if (!threadId) return;
      setStreaming(true);
      setError(null);
      setAssistantText("");
      setToolCalls(0);
      try {
        await streamAgentTurn(agentName, threadId, content, {
          onStart: () => setStreaming(true),
          onDelta: (delta) => setAssistantText((prev) => prev + delta),
          onDone: (payload) => {
            setToolCalls(payload.tool_calls);
            onTurnDone?.();
          },
          onError: (detail) => {
            setError(detail);
            onTurnError?.();
          },
        });
      } finally {
        setStreaming(false);
      }
    },
    [agentName, threadId, onTurnDone, onTurnError],
  );

  return { streaming, assistantText, error, toolCalls, send };
}
