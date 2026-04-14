"""Circular-linking resolver built on metadata graph relations.

This module builds an in-memory relation graph from indexed document metadata
and returns explainable related circulars/clauses for a set of focus chunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from langchain_core.documents import Document


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "guidelines",
    "guideline",
    "direction",
    "master",
    "on",
    "of",
    "by",
    "to",
}


@dataclass
class CircularNode:
    node_id: str
    source: str
    source_ref: str
    document_title: str
    title_norm: str
    regulator: str | None
    version_date: str | None
    effective_date: str | None
    amends: str | None
    snippet: str


@dataclass
class CircularEdge:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    rationale: str


def _empty_output() -> dict:
    return {"related_circulars": [], "related_clauses": []}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _source_ref(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    return Path(raw).name.lower()


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if len(token) > 2 and token.lower() not in _STOPWORDS
    }


def _title_overlap_score(a: str, b: str) -> float:
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    inter = len(tokens_a.intersection(tokens_b))
    denom = max(1, min(len(tokens_a), len(tokens_b)))
    return inter / denom


def _iter_index_docs(vectorstore: Any) -> list[Document]:
    docstore = getattr(vectorstore, "docstore", None)
    mapping = getattr(vectorstore, "index_to_docstore_id", {})
    if docstore is None:
        return []

    docs: list[Document] = []
    for doc_id in mapping.values():
        doc = docstore.search(doc_id)
        if doc is not None:
            docs.append(doc)
    return docs


def _node_id(source_ref: str, title_norm: str, version_date: str | None) -> str:
    date_part = version_date or "unknown"
    return f"{source_ref}|{title_norm}|{date_part}"


def _build_nodes(vectorstore: Any) -> dict[str, CircularNode]:
    nodes: dict[str, CircularNode] = {}

    for doc in _iter_index_docs(vectorstore):
        metadata = getattr(doc, "metadata", {}) or {}
        source = str(metadata.get("source", "")).strip()
        if not source:
            continue

        source_ref = _source_ref(source)
        title = str(metadata.get("document_title") or Path(source).stem).strip()
        title_norm = _normalize_text(title)
        regulator = str(metadata.get("regulator")).strip() if metadata.get("regulator") else None
        version_date = str(metadata.get("version_date")).strip() if metadata.get("version_date") else None
        effective_date = str(metadata.get("effective_date")).strip() if metadata.get("effective_date") else None
        amends = str(metadata.get("amends")).strip() if metadata.get("amends") else None
        snippet = (getattr(doc, "page_content", "") or "").strip()[:600]

        node_key = _node_id(source_ref, title_norm, version_date)
        existing = nodes.get(node_key)
        if existing is None:
            nodes[node_key] = CircularNode(
                node_id=node_key,
                source=source,
                source_ref=source_ref,
                document_title=title,
                title_norm=title_norm,
                regulator=regulator,
                version_date=version_date,
                effective_date=effective_date,
                amends=amends,
                snippet=snippet,
            )
        elif not existing.snippet and snippet:
            existing.snippet = snippet

    return nodes


def _insert_edge(edge_map: dict[tuple[str, str, str], CircularEdge], edge: CircularEdge) -> None:
    key = (edge.source_id, edge.target_id, edge.relation_type)
    current = edge_map.get(key)
    if current is None or edge.confidence > current.confidence:
        edge_map[key] = edge


def _find_amendment_target(node: CircularNode, all_nodes: list[CircularNode]) -> tuple[CircularNode, float, str] | None:
    if not node.amends:
        return None

    amends_raw = node.amends
    amends_ref = _source_ref(amends_raw)
    amends_norm = _normalize_text(amends_raw)

    source_matches = [n for n in all_nodes if n.node_id != node.node_id and n.source_ref == amends_ref]
    if source_matches:
        return source_matches[0], 0.96, "Metadata field 'amends' directly references this source document."

    date_match = _DATE_RE.search(amends_raw)
    if date_match:
        target_date = date_match.group(0)
        date_candidates = [
            n
            for n in all_nodes
            if n.node_id != node.node_id
            and n.version_date == target_date
            and n.title_norm == node.title_norm
        ]
        if date_candidates:
            return (
                date_candidates[0],
                0.9,
                "Metadata field 'amends' references this document version date within the same circular family.",
            )

    ranked: list[tuple[float, CircularNode]] = []
    for candidate in all_nodes:
        if candidate.node_id == node.node_id:
            continue
        if candidate.regulator and node.regulator and candidate.regulator != node.regulator:
            continue
        overlap = _title_overlap_score(candidate.document_title, amends_norm)
        if overlap > 0:
            ranked.append((overlap, candidate))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] >= 0.5:
        score, target = ranked[0]
        return (
            target,
            min(0.85, 0.6 + (0.4 * score)),
            "Metadata field 'amends' text overlaps strongly with this circular title.",
        )

    return None


def _build_edges(nodes: dict[str, CircularNode]) -> dict[str, list[CircularEdge]]:
    edge_map: dict[tuple[str, str, str], CircularEdge] = {}
    node_list = list(nodes.values())

    for node in node_list:
        resolved = _find_amendment_target(node, node_list)
        if resolved is None:
            continue
        target, confidence, rationale = resolved
        _insert_edge(
            edge_map,
            CircularEdge(
                source_id=node.node_id,
                target_id=target.node_id,
                relation_type="amends",
                confidence=confidence,
                rationale=rationale,
            ),
        )
        _insert_edge(
            edge_map,
            CircularEdge(
                source_id=target.node_id,
                target_id=node.node_id,
                relation_type="amended_by",
                confidence=max(0.5, confidence - 0.05),
                rationale="This circular appears to be amended by the related document.",
            ),
        )

    for idx, left in enumerate(node_list):
        if not left.document_title:
            continue
        for right in node_list[idx + 1 :]:
            if not right.document_title:
                continue
            if left.regulator and right.regulator and left.regulator != right.regulator:
                continue

            left_in_right = left.title_norm and left.title_norm in right.title_norm
            right_in_left = right.title_norm and right.title_norm in left.title_norm
            if not left_in_right and not right_in_left:
                continue

            overlap = _title_overlap_score(left.document_title, right.document_title)
            if overlap < 0.45:
                continue

            if len(left.document_title) <= len(right.document_title):
                parent, child = left, right
            else:
                parent, child = right, left

            confidence = min(0.92, 0.58 + (0.34 * overlap))
            rationale = (
                "Title containment and token overlap indicate a parent-child circular hierarchy."
            )

            _insert_edge(
                edge_map,
                CircularEdge(
                    source_id=parent.node_id,
                    target_id=child.node_id,
                    relation_type="parent_child",
                    confidence=confidence,
                    rationale=rationale,
                ),
            )
            _insert_edge(
                edge_map,
                CircularEdge(
                    source_id=child.node_id,
                    target_id=parent.node_id,
                    relation_type="parent_child",
                    confidence=max(0.5, confidence - 0.03),
                    rationale=rationale,
                ),
            )

    adjacency: dict[str, list[CircularEdge]] = {}
    for edge in edge_map.values():
        adjacency.setdefault(edge.source_id, []).append(edge)

    for source_id in adjacency:
        adjacency[source_id].sort(key=lambda edge: edge.confidence, reverse=True)

    return adjacency


def _resolve_focus_ids(focus_docs: list[Document], nodes: dict[str, CircularNode]) -> set[str]:
    by_source: dict[str, set[str]] = {}
    by_title: dict[str, set[str]] = {}
    for node_id, node in nodes.items():
        by_source.setdefault(node.source_ref, set()).add(node_id)
        by_title.setdefault(node.title_norm, set()).add(node_id)

    focus_ids: set[str] = set()
    for doc in focus_docs:
        metadata = getattr(doc, "metadata", {}) or {}
        source_ref = _source_ref(metadata.get("source"))
        title_norm = _normalize_text(metadata.get("document_title"))

        if source_ref and source_ref in by_source:
            focus_ids.update(by_source[source_ref])
        if title_norm and title_norm in by_title:
            focus_ids.update(by_title[title_norm])

    return focus_ids


def resolve_circular_links(
    vectorstore: Any,
    focus_docs: list[Document],
    max_related: int = 5,
) -> dict:
    """Resolve related circulars and clauses using metadata graph relations."""
    if not focus_docs:
        return _empty_output()

    nodes = _build_nodes(vectorstore)
    if not nodes:
        return _empty_output()

    adjacency = _build_edges(nodes)
    if not adjacency:
        return _empty_output()

    focus_ids = _resolve_focus_ids(focus_docs, nodes)
    if not focus_ids:
        return _empty_output()

    ranked_edges: list[CircularEdge] = []
    for source_id in focus_ids:
        ranked_edges.extend(adjacency.get(source_id, []))

    if not ranked_edges:
        return _empty_output()

    best_by_target_relation: dict[tuple[str, str], CircularEdge] = {}
    for edge in ranked_edges:
        key = (edge.target_id, edge.relation_type)
        current = best_by_target_relation.get(key)
        if current is None or edge.confidence > current.confidence:
            best_by_target_relation[key] = edge

    selected = sorted(
        best_by_target_relation.values(),
        key=lambda edge: edge.confidence,
        reverse=True,
    )[: max(1, max_related)]

    related_circulars: list[dict] = []
    related_clauses: list[dict] = []

    for edge in selected:
        target = nodes.get(edge.target_id)
        if target is None:
            continue

        related_circulars.append(
            {
                "relation_type": edge.relation_type,
                "source": target.source,
                "document_title": target.document_title,
                "regulator": target.regulator,
                "version_date": target.version_date,
                "effective_date": target.effective_date,
                "confidence": round(float(edge.confidence), 3),
                "rationale": edge.rationale,
            }
        )

        if target.snippet:
            related_clauses.append(
                {
                    "relation_type": edge.relation_type,
                    "source": target.source,
                    "document_title": target.document_title,
                    "snippet": target.snippet,
                    "confidence": round(float(edge.confidence), 3),
                    "rationale": edge.rationale,
                }
            )

    return {
        "related_circulars": related_circulars,
        "related_clauses": related_clauses,
    }
