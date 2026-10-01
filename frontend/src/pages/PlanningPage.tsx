import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../api/client";

interface MineOption {
  id: number;
  code: string;
  name: string;
}

interface ForecastRow {
  date: string;
  rain_mm: number;
  temp_max_c: number | null;
  source: string;
}
interface ForecastResult {
  mine_id: number;
  stale: boolean;
  rows: ForecastRow[];
}

interface BinStat {
  n: number;
  p25: number;
  p50: number;
  p75: number;
}
interface ImpactResult {
  sufficient: boolean;
  n?: number;
  message?: string;
  baseline_dry_t?: number;
  bins?: Record<string, Record<string, BinStat>>;
}

interface PlanRow {
  date: string;
  rain_mm: number;
  bin: string;
  ratio_p50: number;
  expected_output_t: number;
  plan_t: number;
  expected_loss_t: number;
  proposed_extra_t?: number;
}
interface PlanResult {
  ok: boolean;
  reason?: string;
  suggestion_id?: number;
  baseline_dry_t?: number;
  capacity_cap_t?: number;
  monthly_target_t?: number;
  achieved_to_date_t?: number;
  remaining_days?: number;
  rows?: PlanRow[];
  total_expected_loss_t?: number;
  recoverable_t?: number;
  unrecoverable_shortfall_t?: number;
}

interface SuggestionItem {
  id: number;
  horizon: string;
  status: string;
  reason: string | null;
  decided_by: number | null;
  created_at: string;
}

interface BacktestResult {
  ok: boolean;
  reason?: string;
  mae_t?: number;
  mape_pct?: number;
  days?: number;
}

const fmt = (v: number | null | undefined, suffix = "") =>
  v == null ? "—" : `${v.toLocaleString("en-IN")}${suffix}`;

export default function PlanningPage() {
  const { token } = useAuth();
  const [mines, setMines] = useState<MineOption[]>([]);
  const [mineId, setMineId] = useState<number | null>(null);
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [impact, setImpact] = useState<ImpactResult | null>(null);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [btStart, setBtStart] = useState("");
  const [btEnd, setBtEnd] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    apiFetch<MineOption[]>("/masters/mines", { token })
      .then((ms) => {
        setMines(ms);
        if (ms.length > 0) setMineId((cur) => cur ?? ms[0].id);
      })
      .catch(() => {});
  }, [token]);

  const loadForecast = useCallback(
    async (id: number) => {
      try {
        const [f, i] = await Promise.all([
          apiFetch<ForecastResult>(`/planning/weather/forecast?mine_id=${id}`, { token: token! }),
          apiFetch<ImpactResult>(`/planning/rain-impact?mine_id=${id}`, { token: token! }),
        ]);
        setForecast(f);
        setImpact(i);
      } catch {
        setForecast(null);
        setImpact(null);
      }
    },
    [token],
  );

  const loadSuggestions = useCallback(async (id: number) => {
    try {
      setSuggestions(
        await apiFetch<SuggestionItem[]>(`/planning/suggestions?mine_id=${id}`, { token: token! }),
      );
    } catch {
      setSuggestions([]);
    }
  }, [token]);

  useEffect(() => {
    if (mineId != null) {
      loadForecast(mineId);
      loadSuggestions(mineId);
      setPlan(null);
      setBacktest(null);
    }
  }, [mineId, loadForecast, loadSuggestions]);

  const importWeather = async () => {
    if (!token) return;
    setBusy("import");
    setMsg(null);
    try {
      const r = await apiFetch<{ ok: boolean; rows_by_mine: Record<string, number> }>(
        "/planning/weather/import",
        { method: "POST", token },
      );
      setMsg({
        kind: "ok",
        text: `Weather CSVs imported: ${Object.entries(r.rows_by_mine)
          .map(([m, n]) => `${m}: ${n} rows`)
          .join(", ")}`,
      });
      if (mineId != null) await loadForecast(mineId);
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Import failed" });
    } finally {
      setBusy(null);
    }
  };

  const generatePlan = async () => {
    if (mineId == null || !token) return;
    setBusy("plan");
    setMsg(null);
    try {
      const r = await apiFetch<PlanResult>("/planning/suggest", {
        method: "POST",
        body: { mine_id: mineId },
        token,
      });
      setPlan(r);
      await loadSuggestions(mineId);
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Plan generation failed" });
    } finally {
      setBusy(null);
    }
  };

  const decide = async (id: number, decision: "ACCEPTED" | "REJECTED") => {
    const reason = window.prompt(`Reason for ${decision.toLowerCase()} (required, audited):`);
    if (!reason || !reason.trim()) return;
    try {
      await apiFetch(`/planning/suggestions/${id}/decide`, {
        method: "POST",
        body: { decision, reason: reason.trim() },
        token: token!,
      });
      setMsg({ kind: "ok", text: `Plan ${id} ${decision.toLowerCase()} — decision recorded in the audit log.` });
      if (mineId != null) await loadSuggestions(mineId);
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Decision failed" });
    }
  };

  const runBacktest = async () => {
    if (mineId == null || !btStart || !btEnd || !token) return;
    setBusy("backtest");
    setMsg(null);
    try {
      setBacktest(
        await apiFetch<BacktestResult>(
          `/planning/backtest?mine_id=${mineId}&start=${btStart}&end=${btEnd}`,
          { token },
        ),
      );
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Backtest failed" });
    } finally {
      setBusy(null);
    }
  };

  const rainTone = (mm: number) =>
    mm >= 50 ? "bg-red-100 text-red-700"
    : mm >= 20 ? "bg-orange-100 text-orange-700"
    : mm >= 5 ? "bg-amber-100 text-amber-700"
    : mm >= 1 ? "bg-sky-100 text-sky-700"
    : "bg-green-100 text-green-700";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Rain Forecast &amp; Recovery Planner</h2>
        <p className="text-sm text-gray-500 mt-1">
          Weather-aware production recovery: deterministic impact model learned from this mine's own
          history, P25–P75 ranges, capacity caps — suggestions are never applied automatically.
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5 flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Mine</label>
          <select
            value={mineId ?? ""}
            onChange={(e) => setMineId(Number(e.target.value))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm min-w-[200px]"
          >
            {mines.map((m) => (
              <option key={m.id} value={m.id}>{m.code} — {m.name}</option>
            ))}
          </select>
        </div>
        <button
          onClick={importWeather}
          disabled={busy === "import"}
          className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
        >
          {busy === "import" ? "Importing..." : "Import weather CSVs"}
        </button>
        <button
          onClick={generatePlan}
          disabled={busy === "plan" || mineId == null}
          className="bg-amber-500 text-gray-900 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-amber-400 disabled:opacity-50"
        >
          {busy === "plan" ? "Building..." : "Generate 7-day recovery plan"}
        </button>
      </div>

      {msg && (
        <p className={`text-sm rounded-lg px-4 py-3 border ${
          msg.kind === "ok"
            ? "text-green-700 bg-green-50 border-green-100"
            : "text-red-600 bg-red-50 border-red-100"
        }`}>
          {msg.text}
        </p>
      )}

      {/* Forecast */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">Forecast (next 7 days)</h3>
          {forecast?.stale && (
            <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">
              STALE — older than 3 days, re-import CSV
            </span>
          )}
        </div>
        {forecast && forecast.rows.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Date</th>
                <th className="px-4 py-2 text-left">Rain</th>
                <th className="px-4 py-2 text-right">Max temp</th>
                <th className="px-4 py-2 text-left">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {forecast.rows.map((r) => (
                <tr key={r.date}>
                  <td className="px-4 py-2 font-medium text-gray-800">{r.date}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${rainTone(r.rain_mm)}`}>
                      {r.rain_mm} mm
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right font-mono">{r.temp_max_c ?? "—"}°C</td>
                  <td className="px-4 py-2 text-gray-500 text-xs">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="px-5 py-6 text-sm text-gray-500">
            No forecast rows — click <em>Import weather CSVs</em> (files:{" "}
            <code className="text-xs bg-gray-100 px-1 rounded">forecast_&lt;MINE&gt;.csv</code> in the
            weather folder).
          </p>
        )}
      </div>

      {/* Rain impact model */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Rain-impact model (learned from history)</h3>
        </div>
        {impact == null ? (
          <p className="px-5 py-6 text-sm text-gray-500">Select a mine.</p>
        ) : !impact.sufficient ? (
          <p className="px-5 py-6 text-sm text-amber-700 bg-amber-50">
            Insufficient evidence ({impact.n ?? 0} overlapping weather+output days, need ≥ 15).
            Import more history or record more shifts.
          </p>
        ) : (
          <div className="p-5 pt-3 space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Dry-day baseline</p>
                <p className="text-lg font-semibold text-gray-900">{fmt(impact.baseline_dry_t, " t")}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Evidence days</p>
                <p className="text-lg font-semibold text-gray-900">{fmt(impact.n)}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Model</p>
                <p className="text-sm font-semibold text-gray-900 mt-1">P25 / P50 / P75 + next-day lag</p>
              </div>
            </div>
            <table className="w-full text-sm">
              <thead className="text-gray-500 text-xs uppercase">
                <tr>
                  <th className="py-2 text-left">Season</th>
                  <th className="py-2 text-left">Rain bin</th>
                  <th className="py-2 text-right">n</th>
                  <th className="py-2 text-right">P25</th>
                  <th className="py-2 text-right">P50</th>
                  <th className="py-2 text-right">P75</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {Object.entries(impact.bins ?? {}).flatMap(([season, bins]) =>
                  Object.entries(bins).map(([bin, s]) => (
                    <tr key={`${season}-${bin}`}>
                      <td className="py-2 capitalize">{season}</td>
                      <td className="py-2 font-medium">{bin === "lag-next-day" ? "day after 20mm+" : `${bin} mm`}</td>
                      <td className="py-2 text-right font-mono">{s.n}</td>
                      <td className="py-2 text-right font-mono">{(s.p25 * 100).toFixed(0)}%</td>
                      <td className="py-2 text-right font-mono font-semibold">{(s.p50 * 100).toFixed(0)}%</td>
                      <td className="py-2 text-right font-mono">{(s.p75 * 100).toFixed(0)}%</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
            <p className="text-xs text-gray-400">
              Percentages are expected output as a share of the dry-day baseline. The engine never
              exceeds the P95 capacity cap, and plans never auto-apply — a human accepts or rejects.
            </p>
          </div>
        )}
      </div>

      {/* Plan suggestion */}
      {plan && (plan.ok ? (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">
              Recovery plan{plan.suggestion_id ? ` — suggestion #${plan.suggestion_id}` : ""}
            </h3>
            {plan.suggestion_id && (
              <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">PENDING</span>
            )}
          </div>
          <div className="p-5 pt-3 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                ["Monthly target", fmt(plan.monthly_target_t, " t")],
                ["Achieved MTD", fmt(plan.achieved_to_date_t, " t")],
                ["Remaining days", fmt(plan.remaining_days)],
                ["Capacity cap (P95)", fmt(plan.capacity_cap_t, " t")],
                ["Dry baseline", fmt(plan.baseline_dry_t, " t")],
              ].map(([k, v]) => (
                <div key={k} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 uppercase">{k}</p>
                  <p className="text-base font-semibold text-gray-900">{v}</p>
                </div>
              ))}
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-left">Rain</th>
                  <th className="px-3 py-2 text-left">Bin</th>
                  <th className="px-3 py-2 text-right">Expected</th>
                  <th className="px-3 py-2 text-right">Plan/day</th>
                  <th className="px-3 py-2 text-right">Loss</th>
                  <th className="px-3 py-2 text-right">Recover</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(plan.rows ?? []).map((r) => (
                  <tr key={r.date} className={r.expected_loss_t > 0 ? "bg-red-50/50" : ""}>
                    <td className="px-3 py-2 font-medium">{r.date}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${rainTone(r.rain_mm)}`}>
                        {r.rain_mm} mm
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-500">{r.bin}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(r.expected_output_t, " t")}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(r.plan_t, " t")}</td>
                    <td className="px-3 py-2 text-right font-mono text-red-600">
                      {r.expected_loss_t > 0 ? `-${fmt(r.expected_loss_t, " t")}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-green-700">
                      {r.proposed_extra_t ? `+${fmt(r.proposed_extra_t, " t")}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-red-50 rounded-lg p-3">
                <p className="text-xs text-red-500 uppercase">Total expected loss</p>
                <p className="text-lg font-semibold text-red-700">{fmt(plan.total_expected_loss_t, " t")}</p>
              </div>
              <div className="bg-green-50 rounded-lg p-3">
                <p className="text-xs text-green-600 uppercase">Recoverable (redistribute)</p>
                <p className="text-lg font-semibold text-green-700">{fmt(plan.recoverable_t, " t")}</p>
              </div>
              <div className="bg-amber-50 rounded-lg p-3">
                <p className="text-xs text-amber-600 uppercase">Unrecoverable shortfall</p>
                <p className="text-lg font-semibold text-amber-700">{fmt(plan.unrecoverable_shortfall_t, " t")}</p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <p className="text-sm text-amber-700">
            Cannot build a plan: {plan.reason ?? "insufficient data"}.
          </p>
        </div>
      ))}

      {/* Decision history */}
      {suggestions.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">Plan suggestions &amp; decisions</h3>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">#</th>
                <th className="px-4 py-2 text-left">Horizon</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Reason</th>
                <th className="px-4 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suggestions.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2 font-mono">{s.id}</td>
                  <td className="px-4 py-2">{s.horizon}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      s.status === "PENDING" ? "bg-blue-100 text-blue-700"
                      : s.status === "ACCEPTED" ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-600"
                    }`}>{s.status}</span>
                  </td>
                  <td className="px-4 py-2 text-gray-500 max-w-[280px] truncate" title={s.reason ?? ""}>
                    {s.reason ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-right space-x-2">
                    {s.status === "PENDING" && (
                      <>
                        <button
                          onClick={() => decide(s.id, "ACCEPTED")}
                          className="text-xs text-green-700 hover:text-green-900 font-medium"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => decide(s.id, "REJECTED")}
                          className="text-xs text-red-500 hover:text-red-700 font-medium"
                        >
                          Reject
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Backtest */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Trust calibration (backtest)</h3>
        <p className="text-xs text-gray-400">
          Replays past rain as if it were the forecast and compares predicted vs actual loss —
          this is how much you should trust the plan.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">From</label>
            <input type="date" value={btStart} onChange={(e) => setBtStart(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">To</label>
            <input type="date" value={btEnd} onChange={(e) => setBtEnd(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm" />
          </div>
          <button
            onClick={runBacktest}
            disabled={busy === "backtest" || !btStart || !btEnd}
            className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
          >
            {busy === "backtest" ? "Running..." : "Run backtest"}
          </button>
        </div>
        {backtest && (backtest.ok ? (
          <div className="grid grid-cols-3 gap-3 pt-1">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 uppercase">Days evaluated</p>
              <p className="text-lg font-semibold text-gray-900">{fmt(backtest.days)}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 uppercase">Mean abs. error</p>
              <p className="text-lg font-semibold text-gray-900">{fmt(backtest.mae_t, " t")}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 uppercase">MAPE</p>
              <p className="text-lg font-semibold text-gray-900">{fmt(backtest.mape_pct, "%")}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-amber-700">{backtest.reason ?? "No data for this period."}</p>
        ))}
      </div>
    </div>
  );
}
