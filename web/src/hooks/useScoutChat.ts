import { useCallback, useState } from "react";
import { streamScoutTurn } from "../api/scout";

export function useScoutChat(threadId: string | null, onTurnDone?: () => void) {
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
        await streamScoutTurn(threadId, content, {
          onStart: () => setStreaming(true),
          onDelta: (delta) => setAssistantText((prev) => prev + delta),
          onDone: (payload) => {
            setToolCalls(payload.tool_calls);
            onTurnDone?.();
          },
          onError: (detail) => setError(detail),
        });
      } finally {
        setStreaming(false);
      }
    },
    [threadId, onTurnDone],
  );

  return { streaming, assistantText, error, toolCalls, send };
}
