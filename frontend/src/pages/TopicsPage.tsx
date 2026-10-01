import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, type TopicsResult } from "../api/client";

const CLOUD_COLORS = [
  "#1a1a2e", "#2d2d54", "#465096", "#6b74b8",
  "#9198c9", "#3f6c51", "#2e7d32", "#b58900",
];

/**
 * Deterministic DOM word cloud — sized by relative frequency, colored by term
 * length. No external layout dependency needed (keeps the app fully offline).
 */
function WordCloud({ words }: { words: { text: string; value: number }[] }) {
  if (words.length === 0) return null;
  const max = Math.max(...words.map((w) => w.value), 1);
  return (
    <div className="flex flex-wrap items-baseline justify-center gap-x-3 gap-y-1 py-4">
      {words.map((w) => {
        const rel = w.value / max;
        return (
          <span
            key={w.text}
            className="cursor-default leading-tight"
            style={{
              fontSize: `${Math.max(11, Math.round(11 + rel * 30))}px`,
              color: CLOUD_COLORS[w.text.length % CLOUD_COLORS.length],
              opacity: 0.55 + rel * 0.45,
            }}
            title={`${w.text}: ${w.value}`}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
}

export default function TopicsPage() {
  const { token } = useAuth();
  const [data, setData] = useState<TopicsResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiFetch<TopicsResult>("/documents/topics", { token })
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load topics"))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <p className="text-gray-500 py-8 text-center">Analyzing corpus...</p>;
  if (error) return <p className="text-red-600 py-8 text-center">{error}</p>;
  if (!data || data.document_count === 0) {
    return (
      <div className="py-8 text-center">
        <h2 className="text-xl font-semibold text-gray-900">Topics & Word Cloud</h2>
        <p className="text-gray-500 mt-2 text-sm">
          No documents in the corpus yet. Upload PDFs, spreadsheets or images on the Documents page first.
        </p>
      </div>
    );
  }

  const maxTrend = Math.max(
    1,
    ...data.trends.flatMap((t) => t.counts.map((c) => c.count)),
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Topics & Word Cloud</h2>
        <p className="text-sm text-gray-500 mt-1">
          Corpus-wide intelligence across {data.document_count} document{data.document_count !== 1 ? "s" : ""} · engine: {data.engine}
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">
          Word Cloud — dominant terms
        </h3>
        <WordCloud words={data.wordcloud} />
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          Identified topics ({data.topics.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.topics.map((t) => (
            <div key={t.id} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-start justify-between">
                <h4 className="font-semibold text-gray-900 text-sm capitalize">{t.label}</h4>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded whitespace-nowrap">
                  {t.document_count} doc{t.document_count !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="mt-3 space-y-1.5">
                {t.keywords.map((k) => (
                  <div key={k.term} className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 w-28 truncate">{k.term}</span>
                    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gray-800 rounded-full"
                        style={{
                          width: `${Math.round((k.weight / (t.keywords[0]?.weight || 1)) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {data.trends.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
            Topic trends by upload month
          </h3>
          <div className="space-y-3">
            {data.trends.map((point) => (
              <div key={point.period} className="flex items-center gap-3">
                <span className="text-xs font-mono text-gray-500 w-16">{point.period}</span>
                <div className="flex-1 space-y-1">
                  {point.counts.map((c) => (
                    <div key={c.topic} className="flex items-center gap-2">
                      <div
                        className="h-3 rounded-sm bg-gray-700"
                        style={{ width: `${(c.count / maxTrend) * 70}%` }}
                        title={`${c.topic}: ${c.count}`}
                      />
                      <span className="text-xs text-gray-500 truncate max-w-[300px]">{c.topic}</span>
                      <span className="text-xs font-mono text-gray-400">{c.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
