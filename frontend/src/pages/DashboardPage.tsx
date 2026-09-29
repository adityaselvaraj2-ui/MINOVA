import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, milliToDisplay, type ShiftEntry, type Report } from "../api/client";

export default function DashboardPage() {
  const { user, token } = useAuth();
  const [recentEntries, setRecentEntries] = useState<ShiftEntry[]>([]);
  const [recentReports, setRecentReports] = useState<Report[]>([]);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    if (!token) return;

    apiFetch<ShiftEntry[]>("/shift-entries?limit=5", { token }).then(setRecentEntries).catch(() => {});

    apiFetch<Report[]>("/reports?limit=5", { token }).then(setRecentReports).catch(() => {});

    if (user?.can_approve) {
      apiFetch<ShiftEntry[]>("/approvals/queue", { token }).then((q) => setPendingCount(q.length)).catch(() => {});
    }
  }, [token, user?.can_approve]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          Welcome, {user?.full_name}
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          {user?.role_code} — Mine {user?.mine_id ? `#${user.mine_id}` : "HQ"}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {user?.can_enter && (
          <Link
            to="/shift-entry"
            className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-400 transition-colors"
          >
            <h3 className="font-semibold text-gray-900">New Shift Entry</h3>
            <p className="text-sm text-gray-500 mt-1">Record production data</p>
          </Link>
        )}
        {user?.can_approve && (
          <Link
            to="/approvals"
            className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-400 transition-colors"
          >
            <h3 className="font-semibold text-gray-900">Approval Queue</h3>
            <p className="text-sm text-gray-500 mt-1">
              {pendingCount} pending review
            </p>
          </Link>
        )}
        <Link
          to="/reports"
          className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-400 transition-colors"
        >
          <h3 className="font-semibold text-gray-900">Reports</h3>
          <p className="text-sm text-gray-500 mt-1">View and generate reports</p>
        </Link>
      </div>

      {recentEntries.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">
            Recent Shift Entries
          </h3>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Date</th>
                  <th className="px-4 py-2 text-left">Shift</th>
                  <th className="px-4 py-2 text-right">Production (t)</th>
                  <th className="px-4 py-2 text-right">OB (m3)</th>
                  <th className="px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentEntries.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-2">{e.work_date}</td>
                    <td className="px-4 py-2">{e.shift_code}</td>
                    <td className="px-4 py-2 text-right font-mono">
                      {milliToDisplay(e.production_milli_t)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {milliToDisplay(e.ob_milli_m3)}
                    </td>
                    <td className="px-4 py-2">
                      <StatusPill status={e.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {recentReports.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">
            Recent Reports
          </h3>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Level</th>
                  <th className="px-4 py-2 text-left">Period</th>
                  <th className="px-4 py-2 text-left">Coverage</th>
                  <th className="px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentReports.map((r) => (
                  <tr key={r.id}>
                    <td className="px-4 py-2">{r.level}</td>
                    <td className="px-4 py-2">
                      {r.period_start}
                      {r.period_start !== r.period_end && ` to ${r.period_end}`}
                    </td>
                    <td className="px-4 py-2 font-mono">
                      {r.present_children}/{r.expected_children}
                    </td>
                    <td className="px-4 py-2">
                      <StatusPill status={r.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    DRAFT: "bg-gray-100 text-gray-700",
    SUBMITTED: "bg-blue-100 text-blue-700",
    APPROVED: "bg-green-100 text-green-700",
    RETURNED: "bg-amber-100 text-amber-700",
    SUPERSEDED: "bg-gray-100 text-gray-400",
    STALE: "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${colors[status] || "bg-gray-100"}`}>
      {status}
    </span>
  );
}
