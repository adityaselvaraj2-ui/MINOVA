import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../api/client";

interface ParetoCategory {
  category: string;
  hours: number;
  share_pct: number;
  cumulative_pct: number;
}
interface ParetoResult {
  total_hours: number;
  categories: ParetoCategory[];
}
interface UtilMachine {
  machine: string;
  name: string;
  downtime_h: number;
  availability_pct: number;
}
interface UtilResult {
  shift_length_min: number;
  machines: UtilMachine[];
}

const CAT_LABELS: Record<string, string> = {
  equipment_failure: "Equipment failure",
  maintenance: "Maintenance",
  weather: "Weather",
  fire: "Fire incident",
  labour: "Labour",
  supply: "Supply",
  other: "Other",
};

export default function AnalyticsPage() {
  const { token } = useAuth();
  const [pareto, setPareto] = useState<ParetoResult | null>(null);
  const [util, setUtil] = useState<UtilResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      apiFetch<ParetoResult>("/analytics/stoppage_pareto", { token }),
      apiFetch<UtilResult>("/analytics/machine_utilization", { token }),
    ])
      .then(([p, u]) => {
        setPareto(p);
        setUtil(u);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load analytics"));
  }, [token]);

  const maxHours = Math.max(1, ...(pareto?.categories.map((c) => c.hours) ?? [1]));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Operations Analytics</h2>
        <p className="text-sm text-gray-500 mt-1">
          Downtime and machine health across recorded shifts.
        </p>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Stoppage Pareto */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-baseline justify-between mb-1">
            <h3 className="font-semibold text-gray-900">Downtime Pareto</h3>
            <span className="text-xs text-gray-400">
              {pareto ? `${pareto.total_hours.toFixed(1)} h total` : "—"}
            </span>
          </div>
          <p className="text-xs text-gray-400 mb-4">
            Stoppage hours by cause — ordered by impact (80/20 view).
          </p>
          {!pareto || pareto.categories.length === 0 ? (
            <p className="text-sm text-gray-400 py-8 text-center">
              No downtime events recorded yet. Enter shift stoppages to see the Pareto.
            </p>
          ) : (
            <div className="space-y-2.5">
              {pareto.categories.map((c) => (
                <div key={c.category}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">{CAT_LABELS[c.category] ?? c.category}</span>
                    <span className="text-gray-400 font-mono">
                      {c.hours.toFixed(1)}h · {c.share_pct}% · cum {c.cumulative_pct}%
                    </span>
                  </div>
                  <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${c.cumulative_pct <= 80 ? "bg-amber-500" : "bg-gray-400"}`}
                      style={{ width: `${(c.hours / maxHours) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-gray-400 pt-1">
                Amber bars: the vital few causes driving ~80% of downtime.
              </p>
            </div>
          )}
        </div>

        {/* Machine utilization */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-900 mb-1">Machine Availability</h3>
          <p className="text-xs text-gray-400 mb-4">
            Share of shift time without recorded downtime, per machine.
          </p>
          {!util || util.machines.length === 0 ? (
            <p className="text-sm text-gray-400 py-8 text-center">
              No machines registered yet.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-400 uppercase border-b border-gray-100">
                  <th className="text-left py-2 font-medium">Machine</th>
                  <th className="text-right py-2 font-medium">Downtime</th>
                  <th className="text-right py-2 font-medium">Availability</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {util.machines.map((m) => (
                  <tr key={m.machine}>
                    <td className="py-2">
                      <p className="font-medium text-gray-800">{m.machine}</p>
                      <p className="text-xs text-gray-400">{m.name}</p>
                    </td>
                    <td className="py-2 text-right font-mono text-xs text-gray-600">
                      {m.downtime_h.toFixed(1)} h
                    </td>
                    <td className="py-2 text-right">
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded ${
                          m.availability_pct >= 95
                            ? "bg-green-100 text-green-700"
                            : m.availability_pct >= 85
                            ? "bg-amber-100 text-amber-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {m.availability_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="font-semibold text-gray-900 mb-2">About these metrics</h3>
        <p className="text-sm text-gray-600 leading-relaxed">
          Downtime Pareto aggregates every stoppage recorded in shift entries by
          cause category (equipment failure, maintenance, weather, fire, labour,
          supply, other) — the 80/20 view that tells planners which few causes to
          attack first. Machine availability compares recorded downtime against the
          planned shift window. All figures are computed deterministically from the
          approved operational database — no AI estimation is involved. The same
          taxonomy powers the NLC dataset in <code className="text-xs bg-gray-100 px-1 rounded">dataset/stoppage_log.csv</code>.
        </p>
      </div>
    </div>
  );
}
