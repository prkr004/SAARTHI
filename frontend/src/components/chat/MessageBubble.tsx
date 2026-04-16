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
  const isUser = message.role === "user";
  const roleLabel = message.role === "user" ? "You" : "SAARTHI";
  const modeLabel = message.mode ? (MODE_LABELS[message.mode] ?? message.mode) : null;
  const hasSources = message.sources.length > 0;

  return (
    <article className={`message ${isUser ? "message--user" : "message--assistant"}`}>
      <header className="message-head">
        <div className="message-head__identity">
          <strong className="message-author">{roleLabel}</strong>
          {message.pending ? <span className="pending-tag">Sending</span> : null}
        </div>
        {modeLabel ? <span className="mode-tag">{modeLabel}</span> : null}
      </header>

      <div className="message-body">
        <p className="message-text">{message.content}</p>
      </div>

      {showTemporal || hasSources ? (
        <div className="message-meta">
          {showTemporal ? <TemporalPanel temporal={message.temporal} /> : null}
          <SourceList sources={message.sources} compact={compactSources} />
        </div>
      ) : null}
    </article>
  );
}
