import type { SourceItem } from "../../lib/api/types";

function sourceLabel(source: SourceItem): string {
  if (source.document_name) {
    return source.document_name;
  }
  const rawSource = source.metadata?.source;
  if (typeof rawSource === "string" && rawSource.trim().length > 0) {
    const segments = rawSource.replace(/\\/g, "/").split("/");
    return segments[segments.length - 1];
  }
  return "Source";
}

export function SourceList({ sources, compact = false }: { sources: SourceItem[]; compact?: boolean }) {
  if (sources.length === 0) {
    return null;
  }

  return <SourceListView sources={sources} compact={compact} />;
}

interface SourceListViewProps {
  sources: SourceItem[];
  compact: boolean;
}

export function SourceListView({ sources, compact }: SourceListViewProps) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <details className="meta-disclosure source-list">
      <summary>
        <span>Sources</span>
        <span className="meta-disclosure__tag">{sources.length}</span>
      </summary>

      <ol className="source-items">
        {sources.map((source, index) => {
          const label = sourceLabel(source);
          const page = source.page ?? source.metadata?.page;
          const snippet = source.snippet ?? source.content;

          return (
            <li key={`${label}-${index}`} className="source-item">
              <div className="source-item__main">
                {source.document_link ? (
                  <a className="source-link" href={source.document_link} target="_blank" rel="noreferrer">
                    {label}
                  </a>
                ) : (
                  <span className="source-link source-link--muted">{label}</span>
                )}

                {typeof page === "number" ? <span className="source-page">p. {page}</span> : null}
              </div>

              {snippet && !compact ? (
                <details className="source-snippet">
                  <summary>Preview excerpt</summary>
                  <p>{snippet.slice(0, 520)}</p>
                </details>
              ) : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
