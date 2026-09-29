import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, milliToDisplay, type ShiftEntry } from "../api/client";

export default function ApprovalQueuePage() {
  const { token } = useAuth();
  const [queue, setQueue] = useState<ShiftEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [returnComment, setReturnComment] = useState<Record<number, string>>({});
  const [showReturn, setShowReturn] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  const loadQueue = () => {
    if (!token) return;
    setLoading(true);
    apiFetch<ShiftEntry[]>("/approvals/queue", { token })
      .then(setQueue)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(loadQueue, [token]);

  const handleApprove = async (id: number) => {
    try {
      await apiFetch(`/shift-entries/${id}/approve`, { method: "POST", token: token! });
      setMessage({ type: "success", text: `Entry #${id} approved` });
      loadQueue();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Failed" });
    }
  };

  const handleReturn = async (id: number) => {
    const comment = returnComment[id];
    if (!comment?.trim()) {
      setMessage({ type: "error", text: "Comment required for return" });
      return;
    }
    try {
      await apiFetch(`/shift-entries/${id}/return`, {
        method: "POST",
        token: token!,
        body: { comment },
      });
      setMessage({ type: "success", text: `Entry #${id} returned` });
      setShowReturn(null);
      loadQueue();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Failed" });
    }
  };

  if (loading) {
    return <p className="text-gray-500 py-8 text-center">Loading approval queue...</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-gray-900">Approval Queue</h2>

      {message && (
        <div className={`text-sm p-3 rounded-lg ${
          message.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
        }`}>
          {message.text}
        </div>
      )}

      {queue.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center">
          <p className="text-gray-500">No entries pending approval</p>
        </div>
      ) : (
        <div className="space-y-3">
          {queue.map((entry) => (
            <div key={entry.id} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-semibold text-gray-900">
                      {entry.work_date} — Shift {entry.shift_code}
                    </span>
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-medium">
                      {entry.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-4 gap-6 text-sm">
                    <div>
                      <span className="text-gray-500 text-xs">Production</span>
                      <p className="font-mono">{milliToDisplay(entry.production_milli_t)} t</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Overburden</span>
                      <p className="font-mono">{milliToDisplay(entry.ob_milli_m3)} m3</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Operating</span>
                      <p className="font-mono">{entry.operating_min} min</p>
                    </div>
                    <div>
                      <span className="text-gray-500 text-xs">Workers</span>
                      <p className="font-mono">{entry.workers_present}</p>
                    </div>
                  </div>
                  {entry.downtime_events.length > 0 && (
                    <div className="mt-2 text-xs text-gray-500">
                      Downtime: {entry.downtime_events.map((d) => `${d.category} (${d.duration_min}min)`).join(", ")}
                    </div>
                  )}
                  {entry.remarks && (
                    <p className="mt-1 text-xs text-gray-500 italic">{entry.remarks}</p>
                  )}
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => handleApprove(entry.id)}
                    className="px-4 py-1.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => setShowReturn(showReturn === entry.id ? null : entry.id)}
                    className="px-4 py-1.5 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600"
                  >
                    Return
                  </button>
                </div>
              </div>

              {showReturn === entry.id && (
                <div className="mt-3 flex gap-2">
                  <input
                    type="text"
                    placeholder="Reason for return (required)"
                    value={returnComment[entry.id] || ""}
                    onChange={(e) => setReturnComment({ ...returnComment, [entry.id]: e.target.value })}
                    className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                  />
                  <button
                    onClick={() => handleReturn(entry.id)}
                    className="px-4 py-1.5 bg-amber-600 text-white rounded-lg text-sm font-medium"
                  >
                    Confirm Return
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
