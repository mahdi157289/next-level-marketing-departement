import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createThread, fetchMessages, fetchThreads } from "../api/scout";
import { useScoutChat } from "../hooks/useScoutChat";
import { ToolActivityCard } from "./ToolActivityCard";

export function ScoutChat() {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: threads } = useQuery({ queryKey: ["threads"], queryFn: fetchThreads });
  const { data: messages } = useQuery({
    queryKey: ["messages", threadId],
    queryFn: () => (threadId ? fetchMessages(threadId) : Promise.resolve([])),
    enabled: Boolean(threadId),
  });

  const create = useMutation({
    mutationFn: () => createThread("New chat"),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      setThreadId(t.id);
    },
  });

  const invalidateMessages = () => {
    qc.invalidateQueries({ queryKey: ["messages", threadId] });
  };

  const { streaming, assistantText, error, toolCalls, send } = useScoutChat(
    threadId,
    invalidateMessages,
    invalidateMessages,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
          <p className="muted">Select or create a thread to start chatting with the Scout.</p>
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
            {streaming ? <div className="muted">Scout is thinking{toolCalls > 0 ? ` · ${toolCalls} tool call(s)` : ""}…</div> : null}
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
          placeholder={threadId ? "Message the Scout…" : "Create a thread first"}
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
