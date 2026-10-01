import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, type ReviewQueueItem } from "../api/client";

const STATUS_PILL: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-800 border-amber-200",
  VERIFIED: "bg-emerald-100 text-emerald-800 border-emerald-200",
  FLAGGED: "bg-red-100 text-red-800 border-red-200",
};

const FILTERS = ["PENDING", "VERIFIED", "FLAGGED", "ALL"] as const;

export default function ReviewPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [filter, setFilter] = useState<string>("PENDING");
  const [tagInput, setTagInput] = useState<Record<number, string>>({});
  const [noteInput, setNoteInput] = useState<Record<number, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    const qs = filter === "ALL" ? "" : `?status=${filter}`;
    apiFetch<ReviewQueueItem[]>(`/documents/review/queue${qs}`, { token })
      .then(setItems)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load queue"),
      );
    apiFetch<Record<string, number>>("/documents/review/counts", { token })
      .then(setCounts)
      .catch(() => {});
  }, [token, filter]);

  useEffect(load, [load]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await fn();
      setMessage(`${label} — done`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${label} failed`);
    } finally {
      setBusy(false);
    }
  };

  const decide = (id: number, decision: "VERIFIED" | "FLAGGED") =>
    run(`Document ${decision.toLowerCase()}`, () =>
      apiFetch(`/documents/review/${id}`, {
        method: "POST",
        body: { decision, note: noteInput[id]?.trim() || undefined },
        token: token!,
      }),
    );

  const addTag = (id: number) => {
    const tag = tagInput[id]?.trim();
    if (!tag) return;
    return run(`Tag "${tag}" added`, () =>
      apiFetch(`/documents/${id}/tags`, {
        method: "POST",
        body: { tag },
        token: token!,
      }),
    );
  };

  const removeTag = (id: number, tag: string) =>
    run(`Tag "${tag}" removed`, () =>
      apiFetch(`/documents/${id}/tags/${encodeURIComponent(tag)}`, {
        method: "DELETE",
        token: token!,
      }),
    );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Extraction Review</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Verify AI-extracted values before they can ground RAG answers —
          FLAGGED documents are excluded from retrieval entirely.
        </p>
      </div>

      {message && (
        <div className="text-sm bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-3 py-2">
          {message}
        </div>
      )}
      {error && (
        <div className="text-sm bg-red-50 border border-red-200 text-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              filter === f
                ? "bg-gray-900 text-white border-gray-900"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
            }`}
          >
            {f}
            {counts && f !== "ALL" ? ` (${counts[f] ?? 0})` : ""}
          </button>
        ))}
        {counts && (
          <span className="text-xs text-gray-400 ml-2">
            {counts.PENDING ?? 0} pending · {counts.VERIFIED ?? 0} verified ·{" "}
            {counts.FLAGGED ?? 0} flagged
          </span>
        )}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {items.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-gray-400">
            No documents with status {filter}.
          </div>
        )}
        {items.map((d) => (
          <div key={d.id} className="px-4 py-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                  STATUS_PILL[d.review_status] ??
                  "bg-gray-100 text-gray-600 border-gray-200"
                }`}
              >
                {d.review_status}
              </span>
              <span className="font-medium text-gray-900 text-sm">
                {d.filename}
              </span>
              <span className="text-xs text-gray-400">
                {d.file_type} · {d.chunk_count} chunks
                {d.reviewed_at
                  ? ` · reviewed ${new Date(d.reviewed_at).toLocaleString()}`
                  : ""}
              </span>
            </div>

            {d.review_note && (
              <p className="text-xs text-gray-500 mt-1">Note: {d.review_note}</p>
            )}

            <div className="flex items-center gap-1.5 flex-wrap mt-2">
              {d.doc_tags.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 bg-gray-100 text-gray-700 rounded-full px-2 py-0.5 text-[11px]"
                >
                  {t}
                  <button
                    onClick={() => removeTag(d.id, t)}
                    disabled={busy}
                    className="text-gray-400 hover:text-red-600"
                    title="Remove tag"
                  >
                    ×
                  </button>
                </span>
              ))}
              <input
                value={tagInput[d.id] ?? ""}
                onChange={(e) =>
                  setTagInput((m) => ({ ...m, [d.id]: e.target.value }))
                }
                onKeyDown={(e) => e.key === "Enter" && addTag(d.id)}
                placeholder="add tag…"
                className="text-[11px] border border-gray-200 rounded-full px-2 py-0.5 w-28 focus:outline-none focus:border-gray-400"
              />
            </div>

            <div className="flex items-center gap-2 mt-2.5 flex-wrap">
              <input
                value={noteInput[d.id] ?? ""}
                onChange={(e) =>
                  setNoteInput((m) => ({ ...m, [d.id]: e.target.value }))
                }
                placeholder="review note (optional)"
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 w-56 focus:outline-none focus:border-gray-400"
              />
              <button
                onClick={() => decide(d.id, "VERIFIED")}
                disabled={busy}
                className="text-xs font-medium bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg px-3 py-1.5"
              >
                Verify
              </button>
              <button
                onClick={() => decide(d.id, "FLAGGED")}
                disabled={busy}
                className="text-xs font-medium bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white rounded-lg px-3 py-1.5"
              >
                Flag
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
