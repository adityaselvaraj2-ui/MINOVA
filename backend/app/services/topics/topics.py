from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk

logger = logging.getLogger("minetrace.topics")

MAX_CHUNKS = 2000
MAX_CLOUD_TERMS = 80
MAX_TOPICS = 8
MIN_CHUNK_LEN = 40

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")

STOPWORDS = frozenset([
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further", "had",
    "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now",
    "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself",
    "yourselves", "also", "may", "many", "used", "using", "use", "one", "two",
    "three", "however", "therefore", "thus", "within", "without", "upon", "among",
    "across", "per", "etc", "page", "pages", "report", "reports", "section",
    "table", "figure", "annex", "annexure", "nil", "total",
    # CSV/ledger noise (NLC machine-utilization booleans etc.)
    "false", "true", "yes", "no", "none", "unknown", "nan",
])


def _corpus_chunks(db: Session) -> list[tuple[int, str]]:
    rows = (
        db.query(DocumentChunk.document_id, DocumentChunk.text)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.status == "READY")
        .limit(MAX_CHUNKS)
        .all()
    )
    return [(doc_id, text) for doc_id, text in rows if text and len(text.strip()) >= MIN_CHUNK_LEN]


def _tokens(text: str) -> list[str]:
    return [
        t.lower().strip("-")
        for t in TOKEN_RE.findall(text)
        if t.lower().strip("-") not in STOPWORDS and len(t.strip("-")) >= 3
    ]


def _tfidf_matrix(docs_tokens: list[list[str]]) -> tuple[dict[str, float], list[dict[str, float]]]:
    """Returns (global_weights {term: weight}, per-doc weights [{term: weight}])."""
    n_docs = len(docs_tokens)
    tf: list[Counter] = [Counter(toks) for toks in docs_tokens]
    df: Counter = Counter()
    for counts in tf:
        df.update(counts.keys())

    global_weights: dict[str, float] = {}
    doc_weights: list[dict[str, float]] = []
    for counts in tf:
        weights: dict[str, float] = {}
        for term, freq in counts.items():
            idf = 1.0 + (n_docs / (1 + df[term])) if n_docs else 1.0
            w = (1.0 + freq ** 0.5) * idf
            weights[term] = w
            global_weights[term] = global_weights.get(term, 0.0) + w
        doc_weights.append(weights)
    return global_weights, doc_weights


def _top_terms(weights: dict[str, float], k: int) -> list[tuple[str, float]]:
    return sorted(weights.items(), key=lambda x: (-x[1], x[0]))[:k]


def _wordcloud(chunks: list[tuple[int, str]]) -> list[dict]:
    freq: Counter = Counter()
    for _, text in chunks:
        freq.update(_tokens(text))
    return [
        {"text": term, "value": count}
        for term, count in freq.most_common(MAX_CLOUD_TERMS)
    ]


def word_cloud_svg(db: Session, max_terms: int = 60) -> dict:
    """Pure-Python SVG word cloud (no native `wordcloud` dependency).
    Terms are laid out in wrapped rows; font size and opacity scale with
    frequency rank. Tokens match [a-zA-Z][a-zA-Z-]{2,}, so the SVG is
    injection-safe."""
    chunks = _corpus_chunks(db)
    freq: Counter = Counter()
    for _, text in chunks:
        freq.update(_tokens(text))
    terms = freq.most_common(max_terms)
    if not terms:
        return {"svg": "", "terms": [], "chunk_count": len(chunks)}

    max_v, min_v = terms[0][1], terms[-1][1]
    span = max(max_v - min_v, 1)

    x, y, row_h = 12.0, 40.0, 0.0
    parts: list[str] = []
    for term, count in terms:
        share = (count - min_v) / span
        size = 12 + round(28 * share)
        opacity = round(0.45 + 0.55 * share, 2)
        width = len(term) * size * 0.62
        if x + width > 780:
            x = 12.0
            y += row_h + 14
            row_h = 0.0
        parts.append(
            f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" '
            f'fill="#1e3a5f" fill-opacity="{opacity}" '
            f'font-family="Segoe UI, sans-serif">{term}</text>'
        )
        x += width + 14
        row_h = max(row_h, size)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 {y + 30:.0f}" '
        f'role="img" aria-label="corpus word cloud">{"".join(parts)}</svg>'
    )
    return {
        "svg": svg,
        "terms": [{"text": t, "value": v} for t, v in terms],
        "chunk_count": len(chunks),
    }


def _cluster_kmeans(doc_weights: list[dict[str, float]], n_topics: int) -> list[int] | None:
    try:
        import numpy as np
        from sklearn.cluster import KMeans
    except ImportError:
        logger.info("sklearn/numpy unavailable; using single-topic fallback")
        return None

    if len(doc_weights) < n_topics:
        return None

    vocab = sorted({t for w in doc_weights for t in w})
    if not vocab or len(vocab) < n_topics * 2:
        return None

    index = {t: i for i, t in enumerate(vocab)}
    matrix = np.zeros((len(doc_weights), len(vocab)), dtype=np.float32)
    for i, weights in enumerate(doc_weights):
        for term, w in weights.items():
            matrix[i, index[term]] = w

    n_clusters = min(n_topics, len(doc_weights))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    return km.fit_predict(matrix).tolist()


def _labels_for_clusters(
    assignments: list[int], doc_weights: list[dict[str, float]], vocab_top: int = 6,
) -> dict[int, list[tuple[str, float]]]:
    cluster_terms: dict[int, Counter] = defaultdict(Counter)
    for cluster_id, weights in zip(assignments, doc_weights, strict=True):
        for term, w in weights.items():
            cluster_terms[cluster_id][term] += w
    return {
        cid: _top_terms(dict(counter), vocab_top)
        for cid, counter in cluster_terms.items()
    }


def compute_topics(db: Session, n_topics: int = MAX_TOPICS) -> dict:
    chunks = _corpus_chunks(db)
    cloud = _wordcloud(chunks)

    docs = (
        db.query(Document)
        .filter(Document.status == "READY")
        .order_by(Document.uploaded_at)
        .all()
    )
    doc_meta = {d.id: d for d in docs}

    topics_out: list[dict] = []
    trends: list[dict] = []

    if not chunks:
        return {"wordcloud": [], "topics": [], "trends": [], "document_count": 0}

    # Aggregate per-document text so clusters map to documents
    doc_ids: list[int] = []
    doc_tokens: list[list[str]] = []
    per_doc_chunks: dict[int, list[str]] = defaultdict(list)
    for doc_id, text in chunks:
        per_doc_chunks[doc_id].append(text)
    for doc_id in sorted(per_doc_chunks):
        doc_ids.append(doc_id)
        doc_tokens.append(_tokens(" ".join(per_doc_chunks[doc_id])))

    global_weights, doc_weights = _tfidf_matrix(doc_tokens)

    assignments = _cluster_kmeans(doc_weights, n_topics)
    engine = "kmeans-tfidf"
    if assignments is None:
        assignments = [0] * len(doc_ids)
        engine = "single-topic"

    cluster_labels = _labels_for_clusters(assignments, doc_weights)

    seen: set[int] = set()
    for cid in sorted(set(assignments)):
        keywords = cluster_labels.get(cid, [])
        if not keywords:
            continue
        label = ", ".join(t for t, _ in keywords[:3])
        members = [doc_ids[i] for i, a in enumerate(assignments) if a == cid]
        topics_out.append({
            "id": cid,
            "label": label,
            "keywords": [{"term": t, "weight": round(w, 3)} for t, w in keywords],
            "document_count": len(set(members)),
            "document_ids": sorted(set(members)),
        })
        seen.add(cid)

    # Trends: dominant topic per document, bucketed by upload month
    topic_label = {t["id"]: t["label"] for t in topics_out}
    bucket_counts: dict[str, Counter] = defaultdict(Counter)
    for i, doc_id in enumerate(doc_ids):
        doc = doc_meta.get(doc_id)
        if doc is None or not doc.uploaded_at:
            continue
        period = doc.uploaded_at.strftime("%Y-%m")
        bucket_counts[period][assignments[i]] += 1

    top_cluster_ids = [
        cid for cid, _ in sorted(
            Counter(assignments).items(), key=lambda x: -x[1],
        )[:6]
    ]
    for period in sorted(bucket_counts):
        counts = bucket_counts[period]
        trends.append({
            "period": period,
            "counts": [
                {"topic": topic_label.get(cid, f"Topic {cid}"), "count": counts[cid]}
                for cid in top_cluster_ids if cid in counts
            ],
        })

    return {
        "wordcloud": cloud,
        "topics": topics_out,
        "trends": trends,
        "document_count": len(doc_ids),
        "engine": engine,
    }
