import { useEffect, useState } from "react";

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
  onEdit?: (messageId: string, newContent: string) => void;
}

export function MessageBubble({ message, showTemporal = true, compactSources = false, onEdit }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const roleLabel = message.role === "user" ? "You" : "SAARTHI";
  const modeLabel = message.mode ? (MODE_LABELS[message.mode] ?? message.mode) : null;
  const hasSources = message.sources.length > 0;
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(message.content);

  useEffect(() => {
    setEditValue(message.content);
  }, [message.content]);

  return (
    <article className={`message ${isUser ? "message--user" : "message--assistant"}`}>
      <header className="message-head">
        <div className="message-head__identity">
          <strong className="message-author">{roleLabel}</strong>
          {message.pending ? <span className="pending-tag">Sending</span> : null}
          {isUser && onEdit ? (
            <button
              type="button"
              className="message-edit-btn"
              onClick={() => setEditing(true)}
              title="Edit message"
            >
              Edit
            </button>
          ) : null}
        </div>
        {modeLabel ? <span className="mode-tag">{modeLabel}</span> : null}
      </header>

      {editing ? (
        <div className="message-edit-area">
          <textarea
            className="message-edit-textarea"
            value={editValue}
            onChange={(event) => setEditValue(event.target.value)}
            rows={3}
          />
          <div className="message-edit-actions">
            <button
              type="button"
              className="button button--primary button--compact"
              onClick={() => {
                const nextContent = editValue.trim();
                if (!nextContent) {
                  return;
                }

                setEditing(false);
                onEdit?.(message.id, nextContent);
              }}
            >
              Send
            </button>
            <button
              type="button"
              className="button button--ghost button--compact"
              onClick={() => {
                setEditing(false);
                setEditValue(message.content);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="message-body">
          <p className="message-text">{message.content}</p>
        </div>
      )}

      {showTemporal || hasSources ? (
        <div className="message-meta">
          {showTemporal ? <TemporalPanel temporal={message.temporal} /> : null}
          <SourceList sources={message.sources} compact={compactSources} />
        </div>
      ) : null}
    </article>
  );
}
