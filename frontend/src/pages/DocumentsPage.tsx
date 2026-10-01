import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  apiFetch,
  type DocumentInfo,
  type QueryResult,
} from "../api/client";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.xlsx,.xls,.csv";

export default function DocumentsPage() {
  const { token } = useAuth();
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);
  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadDocs = () => {
    if (!token) return;
    apiFetch<DocumentInfo[]>("/documents", { token }).then(setDocs).catch(() => {});
  };

  useEffect(loadDocs, [token]);

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0 || !token) return;
    setUploading(true);
    setMessage(null);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        const res = await apiFetch<DocumentInfo>("/documents/upload", {
          method: "POST",
          body: form,
          token,
        });
        setMessage({
          type: res.status === "READY" ? "success" : "warning",
          text: `${res.filename}: ${res.status}${res.status === "READY" ? ` (${res.chunk_count} chunks indexed)` : " — processing failed"}`,
        });
      }
      loadDocs();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (id: number) => {
    if (!token) return;
    try {
      await apiFetch(`/documents/${id}`, { method: "DELETE", token });
      loadDocs();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Delete failed" });
    }
  };

  const handleAsk = async () => {
    if (!query.trim() || !token) return;
    setAsking(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiFetch<QueryResult>("/documents/query", {
        method: "POST",
        body: { query: query.trim() },
        token,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setAsking(false);
    }
  };

  const statusColor = (s: string) =>
    s === "READY" ? "bg-green-100 text-green-700"
    : s === "ERROR" ? "bg-red-100 text-red-700"
    : s === "PROCESSING" ? "bg-blue-100 text-blue-700"
    : "bg-gray-100 text-gray-700";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Documents & Ask</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload scanned PDFs, spreadsheets and images — then ask questions with cited answers.
          Everything is processed offline.
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Upload documents</h3>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleUpload(e.dataTransfer.files);
          }}
          className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-gray-400 transition-colors cursor-pointer"
          onClick={() => fileRef.current?.click()}
        >
          <p className="text-gray-600 text-sm">
            {uploading ? "Processing (OCR + indexing)..." : "Drag & drop files here, or click to browse"}
          </p>
          <p className="text-xs text-gray-400 mt-1">PDF, images (OCR), Excel/CSV — processed locally</p>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
        </div>
        {message && (
          <p className={`text-sm ${message.type === "success" ? "text-green-600" : message.type === "error" ? "text-red-600" : "text-amber-600"}`}>
            {message.text}
          </p>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Ask the corpus</h3>
        <p className="text-xs text-gray-400">
          Natural-language question → answer with citations back to document and page.
        </p>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="e.g. What was coal production in the northern sector?"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
          <button
            onClick={handleAsk}
            disabled={asking || !query.trim()}
            className="bg-gray-900 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
          >
            {asking ? "Searching..." : "Ask"}
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {result && (
          <div className="space-y-3 pt-2">
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">
                Answer {result.model ? `· model: ${result.model}` : "· excerpts only (AI offline)"}
              </p>
              <p className="text-sm whitespace-pre-wrap text-gray-800">{result.answer}</p>
            </div>
            {result.citations.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">
                  Citations ({result.citations.length})
                </p>
                <div className="space-y-2">
                  {result.citations.map((c) => (
                    <div key={c.ref} className="border border-gray-200 rounded-lg p-3 text-sm">
                      <span className="text-xs font-mono bg-gray-900 text-white px-1.5 py-0.5 rounded mr-2">
                        {c.ref}
                      </span>
                      <span className="font-medium text-gray-800">{c.filename}</span>
                      {c.page_number != null && (
                        <span className="text-gray-400"> · page {c.page_number}</span>
                      )}
                      <p className="text-gray-600 mt-1 text-xs leading-relaxed">{c.excerpt}...</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {docs.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">
              Document library ({docs.length})
            </h3>
            <Link to="/topics" className="text-xs text-blue-600 hover:text-blue-800">
              View topics & word cloud →
            </Link>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">File</th>
                <th className="px-4 py-2 text-left">Type</th>
                <th className="px-4 py-2 text-right">Pages</th>
                <th className="px-4 py-2 text-right">Chunks</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {docs.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 max-w-[240px] truncate" title={d.filename}>{d.filename}</td>
                  <td className="px-4 py-2 text-gray-500">{d.file_type}</td>
                  <td className="px-4 py-2 text-right font-mono">{d.page_count}</td>
                  <td className="px-4 py-2 text-right font-mono">{d.chunk_count}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${statusColor(d.status)}`}>
                      {d.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
