import type { TemporalPayload } from "../../lib/api/types";

export function TemporalPanel({ temporal }: { temporal?: TemporalPayload }) {
  if (!temporal) {
    return null;
  }

  return (
    <section className="temporal-panel" aria-label="Temporal metadata">
      <div>
        <strong>Temporal mode</strong>
        <span>{temporal.intent_detected ? "Intent detected" : "Standard QA"}</span>
      </div>
      {temporal.document_title ? (
        <div>
          <strong>Document</strong>
          <span>{temporal.document_title}</span>
        </div>
      ) : null}
      {temporal.current_date ? (
        <div>
          <strong>Current</strong>
          <span>{temporal.current_date}</span>
        </div>
      ) : null}
      {temporal.previous_date ? (
        <div>
          <strong>Previous</strong>
          <span>{temporal.previous_date}</span>
        </div>
      ) : null}
      {temporal.fallback ? (
        <div>
          <strong>Fallback reason</strong>
          <span>{temporal.fallback_reason ?? "unspecified"}</span>
        </div>
      ) : null}
    </section>
  );
}
