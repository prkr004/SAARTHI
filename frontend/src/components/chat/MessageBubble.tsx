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

interface MessageBubbleProps {
  message: FrontendMessage;
  showTemporal?: boolean;
  compactSources?: boolean;
}

export function MessageBubble({ message, showTemporal = true, compactSources = false }: MessageBubbleProps) {
  const roleLabel = message.role === "user" ? "You" : "SAARTHI";

  return (
    <article className={`message ${message.role === "user" ? "message--user" : "message--assistant"}`}>
      <header className="message-head">
        <strong>{roleLabel}</strong>
        {message.pending ? <span className="pending-tag">Sending...</span> : null}
        {message.mode ? <span className="mode-tag">{MODE_LABELS[message.mode] ?? message.mode}</span> : null}
      </header>
      <p className="message-text">{message.content}</p>
      {showTemporal ? <TemporalPanel temporal={message.temporal} /> : null}
      <SourceList sources={message.sources} compact={compactSources} />
    </article>
  );
}
