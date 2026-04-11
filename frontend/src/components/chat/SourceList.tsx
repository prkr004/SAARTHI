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
    <details className="source-list">
      <summary>View sources ({sources.length})</summary>
      <ol>
        {sources.map((source, index) => {
          const label = sourceLabel(source);
          const page = source.page ?? source.metadata?.page;
          const pageSuffix = typeof page === "number" ? `, page ${page}` : "";
          const snippet = source.snippet ?? source.content;

          return (
            <li key={`${label}-${index}`}>
              {source.document_link ? (
                <a href={source.document_link} target="_blank" rel="noreferrer">
                  {label}
                  {pageSuffix}
                </a>
              ) : (
                <span>
                  {label}
                  {pageSuffix}
                </span>
              )}

              {snippet && !compact ? (
                <details className="source-snippet">
                  <summary>Preview excerpt</summary>
                  <p>{snippet.slice(0, 600)}</p>
                </details>
              ) : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
