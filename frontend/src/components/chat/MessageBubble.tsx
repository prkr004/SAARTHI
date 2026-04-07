import type { FrontendMessage } from "../../lib/api/types";
import { SourceList } from "./SourceList";
import { TemporalPanel } from "./TemporalPanel";

const MODE_LABELS: Record<string, string> = {
  predefined: "Predefined",
  qa: "RAG Answer",
  qa_fallback_non_temporal: "QA Fallback",
  temporal_comparison: "Temporal Compare",
  temporal_fallback: "Temporal Fallback",
  temporal_single_version: "Single Version",
};

export function MessageBubble({ message }: { message: FrontendMessage }) {
  const roleLabel = message.role === "user" ? "You" : "SAARTHI";

  return (
    <article className={`message ${message.role === "user" ? "message--user" : "message--assistant"}`}>
      <header className="message-head">
        <strong>{roleLabel}</strong>
        {message.mode ? <span className="mode-tag">{MODE_LABELS[message.mode] ?? message.mode}</span> : null}
      </header>
      <p className="message-text">{message.content}</p>
      <TemporalPanel temporal={message.temporal} />
      <SourceList sources={message.sources} />
    </article>
  );
}
