import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  createAgentThread,
  fetchAgentMessages,
  fetchAgentThreads,
} from "../api/agent-chat";
import { useAgentChat } from "../hooks/useAgentChat";
import { ToolActivityCard } from "./ToolActivityCard";

export function AgentChat({ agentName, label }: { agentName: string; label: string }) {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: threads } = useQuery({
    queryKey: ["agent-threads", agentName],
    queryFn: () => fetchAgentThreads(agentName),
  });
  const { data: messages } = useQuery({
    queryKey: ["agent-messages", agentName, threadId],
    queryFn: () => (threadId ? fetchAgentMessages(agentName, threadId) : Promise.resolve([])),
    enabled: Boolean(threadId),
  });

  const create = useMutation({
    mutationFn: () => createAgentThread(agentName, "New chat"),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["agent-threads", agentName] });
      setThreadId(t.id);
    },
  });

  const invalidateMessages = () => {
    qc.invalidateQueries({ queryKey: ["agent-messages", agentName, threadId] });
  };

  const { streaming, assistantText, error, toolCalls, send } = useAgentChat(
    agentName,
    threadId,
    invalidateMessages,
    invalidateMessages,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, assistantText]);

  return (
    <div className="scout-chat">
      <div className="scout-chat-threads">
        <button className="btn" type="button" onClick={() => create.mutate()} disabled={create.isPending}>
          + New thread
        </button>
        {threads?.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`thread-pill ${t.id === threadId ? "active" : ""}`}
            onClick={() => setThreadId(t.id)}
          >
            {t.title ?? "Untitled"}
          </button>
        ))}
      </div>

      <div className="scout-chat-messages">
        {!threadId ? (
          <p className="muted">Select or create a thread to start chatting with the {label}.</p>
        ) : (
          <>
            {messages?.map((m) => {
              if (m.role === "tool") {
                return <ToolActivityCard key={m.id} message={m} />;
              }
              return (
                <div key={m.id} className={`chat-bubble ${m.role}`}>
                  {m.content ?? ""}
                </div>
              );
            })}
            {streaming && assistantText ? <div className="chat-bubble assistant">{assistantText}</div> : null}
            {streaming ? <div className="muted">{label} is thinking{toolCalls > 0 ? ` · ${toolCalls} tool call(s)` : ""}…</div> : null}
            {error ? <div className="flash err">{error}</div> : null}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="scout-chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (!text || !threadId) return;
          setDraft("");
          void send(text);
        }}
      >
        <input
          type="text"
          placeholder={threadId ? `Message the ${label}…` : "Create a thread first"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!threadId || streaming}
        />
        <button className="btn" type="submit" disabled={!threadId || streaming || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
