import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  apiFetch,
  milliToDisplay,
  bpToPercent,
  type MineOption,
  type BenchOption,
  type Report,
} from "../api/client";

const LEVELS = ["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUAL"];

export default function ReportsPage() {
  const { token } = useAuth();
  const [mines, setMines] = useState<MineOption[]>([]);
  const [benches, setBenches] = useState<BenchOption[]>([]);
  const [reports, setReports] = useState<Report[]>([]);

  const [mineId, setMineId] = useState<number>(0);
  const [benchId, setBenchId] = useState<number>(0);
  const [level, setLevel] = useState("DAILY");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    apiFetch<MineOption[]>("/masters/mines", { token }).then(setMines).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!token || !mineId) return;
    apiFetch<BenchOption[]>(`/masters/benches?mine_id=${mineId}`, { token }).then(setBenches).catch(() => {});
  }, [token, mineId]);

  const loadReports = () => {
    if (!token) return;
    const params = new URLSearchParams();
    if (mineId) params.set("mine_id", String(mineId));
    if (benchId) params.set("bench_id", String(benchId));
    if (level) params.set("level", level);
    apiFetch<Report[]>(`/reports?${params}`, { token }).then(setReports).catch(() => {});
  };

  useEffect(loadReports, [token, mineId, benchId, level]);

  const handleGenerate = async () => {
    if (!mineId || !periodStart || !periodEnd) {
      setMessage({ type: "error", text: "Mine, period start, and period end are required" });
      return;
    }
    setGenerating(true);
    setMessage(null);
    try {
      await apiFetch<Report>("/reports/generate", {
        method: "POST",
        token: token!,
        body: {
          level,
          mine_id: mineId,
          bench_id: benchId || null,
          period_start: periodStart,
          period_end: periodEnd,
        },
      });
      setMessage({ type: "success", text: `${level} report generated` });
      loadReports();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Failed" });
    } finally {
      setGenerating(false);
    }
  };

  const metricDisplay = (r: Report, code: string): string => {
    const m = r.metrics.find((x) => x.metric_code === code);
    if (!m) return "-";
    if (code.includes("milli_t") || code.includes("milli_m3")) return milliToDisplay(m.value_int);
    if (code.includes("_bp")) return bpToPercent(m.value_int);
    if (code.includes("x1000")) return (m.value_int / 1000).toFixed(2);
    return String(m.value_int);
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-900">Reports</h2>

      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-semibold text-gray-700">Generate Report</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
          <select
            value={mineId}
            onChange={(e) => { setMineId(Number(e.target.value)); setBenchId(0); }}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value={0}>Select mine</option>
            {mines.map((m) => (
              <option key={m.id} value={m.id}>{m.code}</option>
            ))}
          </select>
          <select
            value={benchId}
            onChange={(e) => setBenchId(Number(e.target.value))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value={0}>All benches</option>
            {benches.map((b) => (
              <option key={b.id} value={b.id}>{b.code}</option>
            ))}
          </select>
          <input
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            placeholder="Start"
          />
          <input
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            placeholder="End"
          />
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="bg-gray-900 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
        >
          {generating ? "Generating..." : "Generate"}
        </button>
        {message && (
          <p className={`text-sm ${message.type === "success" ? "text-green-600" : "text-red-600"}`}>
            {message.text}
          </p>
        )}
      </div>

      {reports.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-3 py-2 text-left">Level</th>
                <th className="px-3 py-2 text-left">Period</th>
                <th className="px-3 py-2 text-right">Prod (t)</th>
                <th className="px-3 py-2 text-right">OB (m3)</th>
                <th className="px-3 py-2 text-right">Avail%</th>
                <th className="px-3 py-2 text-center">Coverage</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {reports.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2">{r.level}</td>
                  <td className="px-3 py-2">
                    {r.period_start}
                    {r.period_start !== r.period_end && ` to ${r.period_end}`}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {metricDisplay(r, "production_milli_t")}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {metricDisplay(r, "ob_milli_m3")}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {metricDisplay(r, "availability_bp")}
                  </td>
                  <td className="px-3 py-2 text-center font-mono">
                    <span className={r.present_children < r.expected_children ? "text-amber-600" : "text-green-600"}>
                      {r.present_children}/{r.expected_children}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      r.status === "APPROVED" ? "bg-green-100 text-green-700" :
                      r.status === "DRAFT" ? "bg-gray-100 text-gray-700" :
                      "bg-blue-100 text-blue-700"
                    }`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      to={`/reports/${r.id}`}
                      className="text-xs text-blue-600 hover:text-blue-800"
                    >
                      Details
                    </Link>
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
