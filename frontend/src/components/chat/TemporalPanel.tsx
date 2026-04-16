import type { TemporalPayload } from "../../lib/api/types";

function formatDateLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function TemporalPanel({ temporal }: { temporal?: TemporalPayload }) {
  if (!temporal) {
    return null;
  }

  const temporalState = temporal.fallback
    ? "Fallback"
    : temporal.intent_detected
      ? "Detected"
      : "Standard";

  return (
    <details className="meta-disclosure temporal-disclosure" aria-label="Temporal metadata">
      <summary>
        <span>Temporal details</span>
        <span className="meta-disclosure__tag">{temporalState}</span>
      </summary>

      <dl className="meta-grid">
        <div>
          <dt>Mode</dt>
          <dd>{temporal.intent_detected ? "Temporal comparison" : "Standard QA"}</dd>
        </div>

        <div>
          <dt>Execution</dt>
          <dd>{temporal.executed ? "Executed" : "Not executed"}</dd>
        </div>

        {temporal.single_version ? (
          <div>
            <dt>Version span</dt>
            <dd>Single version indexed</dd>
          </div>
        ) : null}

        {temporal.document_title ? (
          <div>
            <dt>Document</dt>
            <dd>{temporal.document_title}</dd>
          </div>
        ) : null}

        {temporal.current_date ? (
          <div>
            <dt>Current version</dt>
            <dd>{formatDateLabel(temporal.current_date)}</dd>
          </div>
        ) : null}

        {temporal.previous_date ? (
          <div>
            <dt>Previous version</dt>
            <dd>{formatDateLabel(temporal.previous_date)}</dd>
          </div>
        ) : null}

        {temporal.fallback ? (
          <div>
            <dt>Fallback reason</dt>
            <dd>{temporal.fallback_reason ?? "Unspecified"}</dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}
