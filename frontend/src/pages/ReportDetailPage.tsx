import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  apiFetch,
  milliToDisplay,
  bpToPercent,
  type Report,
  type LineageDetail,
} from "../api/client";

function formatMetric(code: string, value: number): string {
  if (code.includes("milli_t")) return milliToDisplay(value) + " t";
  if (code.includes("milli_m3")) return milliToDisplay(value) + " m3";
  if (code.includes("_bp")) return bpToPercent(value);
  if (code.includes("x1000")) return (value / 1000).toFixed(2);
  if (code.includes("_min")) return value + " min";
  return String(value);
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [report, setReport] = useState<Report | null>(null);
  const [lineage, setLineage] = useState<LineageDetail | null>(null);
  const [reconciliation, setReconciliation] = useState<{
    valid: boolean;
    issues: string[];
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !id) return;
    setLoading(true);

    Promise.all([
      apiFetch<Report>(`/reports/${id}`, { token }),
      apiFetch<LineageDetail>(`/reports/${id}/lineage`, { token }),
      apiFetch<{ valid: boolean; issues: string[] }>(`/reports/${id}/reconcile`, { token }),
    ])
      .then(([r, l, c]) => {
        setReport(r);
        setLineage(l);
        setReconciliation(c);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, id]);

  if (loading) {
    return <p className="text-gray-500 py-8 text-center">Loading report...</p>;
  }

  if (!report) {
    return <p className="text-red-600 py-8 text-center">Report not found</p>;
  }

  const additive = report.metrics.filter((m) => m.is_additive);
  const derived = report.metrics.filter((m) => !m.is_additive);

  const contributionsByEdge = new Map<number, { child_kind: string; child_id: number; metrics: Record<string, number> }>();
  if (lineage) {
    for (const c of lineage.contributions) {
      let entry = contributionsByEdge.get(c.edge_id);
      if (!entry) {
        entry = { child_kind: c.child_kind, child_id: c.child_id, metrics: {} };
        contributionsByEdge.set(c.edge_id, entry);
      }
      entry.metrics[c.metric_code] = c.contributed_value_int;
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/reports" className="text-sm text-blue-600 hover:text-blue-800">
            Reports
          </Link>
          <h2 className="text-xl font-semibold text-gray-900 mt-1">
            {report.level} Report — {report.period_start}
            {report.period_start !== report.period_end && ` to ${report.period_end}`}
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2 py-1 rounded font-medium ${
            report.status === "APPROVED" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"
          }`}>
            {report.status}
          </span>
          <span className="text-xs text-gray-500">v{report.version}</span>
        </div>
      </div>

      {reconciliation && (
        <div className={`p-4 rounded-xl border ${
          reconciliation.valid
            ? "bg-green-50 border-green-200"
            : "bg-red-50 border-red-200"
        }`}>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-medium ${reconciliation.valid ? "text-green-700" : "text-red-700"}`}>
              Reconciliation: {reconciliation.valid ? "VALID" : "ISSUES FOUND"}
            </span>
          </div>
          {reconciliation.issues.length > 0 && (
            <ul className="mt-2 text-sm text-red-600 list-disc list-inside">
              {reconciliation.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
            Additive Metrics
          </h3>
          <div className="space-y-2">
            {additive.map((m) => (
              <div key={m.metric_code} className="flex justify-between text-sm">
                <span className="text-gray-500">{m.metric_code.replace(/_/g, " ")}</span>
                <span className="font-mono text-gray-900">{formatMetric(m.metric_code, m.value_int)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
            Derived Metrics
          </h3>
          <div className="space-y-2">
            {derived.map((m) => (
              <div key={m.metric_code} className="flex justify-between text-sm">
                <span className="text-gray-500">{m.metric_code.replace(/_/g, " ")}</span>
                <span className="font-mono text-gray-900">{formatMetric(m.metric_code, m.value_int)}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100 flex justify-between text-sm">
            <span className="text-gray-500">Data coverage</span>
            <span className={`font-mono ${
              report.present_children < report.expected_children ? "text-amber-600" : "text-green-600"
            }`}>
              {report.present_children}/{report.expected_children}
            </span>
          </div>
        </div>
      </div>

      {contributionsByEdge.size > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">
            Lineage — Source Contributions
          </h3>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Source</th>
                  <th className="px-3 py-2 text-right">Production (t)</th>
                  <th className="px-3 py-2 text-right">OB (m3)</th>
                  <th className="px-3 py-2 text-right">Planned (min)</th>
                  <th className="px-3 py-2 text-right">Operating (min)</th>
                  <th className="px-3 py-2 text-right">Workers</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {Array.from(contributionsByEdge.entries()).map(([edgeId, entry]) => (
                  <tr key={edgeId}>
                    <td className="px-3 py-2">
                      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                        {entry.child_kind === "SHIFT_ENTRY" ? "Shift" : "Report"} #{entry.child_id}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {milliToDisplay(entry.metrics.production_milli_t || 0)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {milliToDisplay(entry.metrics.ob_milli_m3 || 0)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {entry.metrics.planned_min || 0}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {entry.metrics.operating_min || 0}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {entry.metrics.workers_present || 0}
                    </td>
                  </tr>
                ))}
                <tr className="bg-gray-50 font-semibold">
                  <td className="px-3 py-2">Total</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {milliToDisplay(additive.find((m) => m.metric_code === "production_milli_t")?.value_int || 0)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {milliToDisplay(additive.find((m) => m.metric_code === "ob_milli_m3")?.value_int || 0)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {additive.find((m) => m.metric_code === "planned_min")?.value_int || 0}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {additive.find((m) => m.metric_code === "operating_min")?.value_int || 0}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {additive.find((m) => m.metric_code === "workers_present")?.value_int || 0}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
