import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  apiFetch,
  milliToDisplay,
  type MineOption,
  type BenchOption,
  type ShiftEntry,
  type DowntimeEvent,
} from "../api/client";

const WEATHER_CODES = ["CLEAR", "CLOUDY", "RAIN", "HEAVY_RAIN", "FOG", "STORM"];
const DOWNTIME_CATEGORIES = [
  "EQUIPMENT_FAILURE",
  "SCHEDULED_MAINTENANCE",
  "WEATHER",
  "FIRE_INCIDENT",
  "LABOUR",
  "SUPPLY",
  "OTHER",
];
const CAUSE_REQUIRED = new Set(["EQUIPMENT_FAILURE", "FIRE_INCIDENT", "LABOUR"]);

export default function ShiftEntryPage() {
  const { token, user } = useAuth();
  const [mines, setMines] = useState<MineOption[]>([]);
  const [benches, setBenches] = useState<BenchOption[]>([]);
  const [entries, setEntries] = useState<ShiftEntry[]>([]);

  const [mineId, setMineId] = useState<number>(user?.mine_id || 0);
  const [benchId, setBenchId] = useState<number>(0);
  const [workDate, setWorkDate] = useState(new Date().toISOString().slice(0, 10));
  const [shiftCode, setShiftCode] = useState("A");
  const [plannedMin, setPlannedMin] = useState(480);
  const [workers, setWorkers] = useState(0);
  const [productionT, setProductionT] = useState("");
  const [obM3, setObM3] = useState("");
  const [weatherCode, setWeatherCode] = useState("");
  const [rainfallMm, setRainfallMm] = useState("");
  const [tempC, setTempC] = useState("");
  const [remarks, setRemarks] = useState("");
  const [downtimeEvents, setDowntimeEvents] = useState<Partial<DowntimeEvent>[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    apiFetch<MineOption[]>("/masters/mines", { token }).then(setMines).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!token || !mineId) return;
    apiFetch<BenchOption[]>(`/masters/benches?mine_id=${mineId}`, { token })
      .then(setBenches)
      .catch(() => {});
  }, [token, mineId]);

  const loadEntries = () => {
    if (!token || !mineId) return;
    const params = new URLSearchParams({ limit: "20" });
    if (mineId) params.set("mine_id", String(mineId));
    if (benchId) params.set("bench_id", String(benchId));
    apiFetch<ShiftEntry[]>(`/shift-entries?${params}`, { token })
      .then(setEntries)
      .catch(() => {});
  };

  useEffect(loadEntries, [token, mineId, benchId]);

  const addDowntime = () => {
    setDowntimeEvents([...downtimeEvents, { category: "OTHER", start_min: 0, end_min: 0 }]);
  };

  const removeDowntime = (i: number) => {
    setDowntimeEvents(downtimeEvents.filter((_, idx) => idx !== i));
  };

  const updateDowntime = (i: number, field: string, value: string | number) => {
    const updated = [...downtimeEvents];
    updated[i] = { ...updated[i], [field]: value };
    setDowntimeEvents(updated);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    try {
      const body = {
        mine_id: mineId,
        bench_id: benchId,
        work_date: workDate,
        shift_code: shiftCode,
        planned_min: plannedMin,
        workers_present: workers,
        production_milli_t: Math.round(parseFloat(productionT || "0") * 1000),
        ob_milli_m3: Math.round(parseFloat(obM3 || "0") * 1000),
        weather_code: weatherCode || null,
        rainfall_mm_x10: rainfallMm ? Math.round(parseFloat(rainfallMm) * 10) : null,
        temperature_c_x10: tempC ? Math.round(parseFloat(tempC) * 10) : null,
        remarks: remarks || null,
        downtime_events: downtimeEvents.map((d) => ({
          category: d.category,
          start_min: Number(d.start_min),
          end_min: Number(d.end_min),
          cause_text: d.cause_text || null,
          equipment_id: d.equipment_id || null,
          evidence_path: null,
        })),
      };

      await apiFetch<ShiftEntry>("/shift-entries", {
        method: "POST",
        body,
        token: token!,
      });

      setMessage({ type: "success", text: "Shift entry saved as DRAFT" });
      setProductionT("");
      setObM3("");
      setWorkers(0);
      setRemarks("");
      setDowntimeEvents([]);
      loadEntries();
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to save",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleAction = async (entryId: number, action: string, comment?: string) => {
    try {
      const opts: { method: string; token: string; body?: unknown } = {
        method: "POST",
        token: token!,
      };
      if (action === "return") {
        opts.body = { comment: comment || "Returned" };
      }
      await apiFetch(`/shift-entries/${entryId}/${action}`, opts);
      loadEntries();
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Action failed" });
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-900">Shift Entry</h2>

      <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Mine</label>
            <select
              value={mineId}
              onChange={(e) => { setMineId(Number(e.target.value)); setBenchId(0); }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              required
            >
              <option value={0}>Select mine</option>
              {mines.map((m) => (
                <option key={m.id} value={m.id}>{m.code} - {m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Bench</label>
            <select
              value={benchId}
              onChange={(e) => setBenchId(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              required
            >
              <option value={0}>Select bench</option>
              {benches.map((b) => (
                <option key={b.id} value={b.id}>{b.code} - {b.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Work Date</label>
            <input
              type="date"
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Shift</label>
            <select
              value={shiftCode}
              onChange={(e) => setShiftCode(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              <option value="A">A (Morning)</option>
              <option value="B">B (Afternoon)</option>
              <option value="C">C (Night)</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Planned (min)</label>
            <input
              type="number"
              value={plannedMin}
              onChange={(e) => setPlannedMin(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              min={0}
              max={480}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Workers</label>
            <input
              type="number"
              value={workers}
              onChange={(e) => setWorkers(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              min={0}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Production (tonnes)</label>
            <input
              type="number"
              step="0.001"
              value={productionT}
              onChange={(e) => setProductionT(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              min={0}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Overburden (m3)</label>
            <input
              type="number"
              step="0.001"
              value={obM3}
              onChange={(e) => setObM3(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              min={0}
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Weather</label>
            <select
              value={weatherCode}
              onChange={(e) => setWeatherCode(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              <option value="">None</option>
              {WEATHER_CODES.map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Rainfall (mm)</label>
            <input
              type="number"
              step="0.1"
              value={rainfallMm}
              onChange={(e) => setRainfallMm(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Temperature (C)</label>
            <input
              type="number"
              step="0.1"
              value={tempC}
              onChange={(e) => setTempC(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Remarks</label>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-600">Downtime Events</label>
            <button type="button" onClick={addDowntime} className="text-xs text-blue-600 hover:text-blue-800">
              + Add Downtime
            </button>
          </div>
          {downtimeEvents.map((d, i) => (
            <div key={i} className="flex gap-2 items-end mb-2">
              <select
                value={d.category || "OTHER"}
                onChange={(e) => updateDowntime(i, "category", e.target.value)}
                className="px-2 py-1.5 border border-gray-300 rounded text-xs flex-1"
              >
                {DOWNTIME_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <input
                type="number"
                placeholder="Start min"
                value={d.start_min || ""}
                onChange={(e) => updateDowntime(i, "start_min", Number(e.target.value))}
                className="w-20 px-2 py-1.5 border border-gray-300 rounded text-xs"
              />
              <input
                type="number"
                placeholder="End min"
                value={d.end_min || ""}
                onChange={(e) => updateDowntime(i, "end_min", Number(e.target.value))}
                className="w-20 px-2 py-1.5 border border-gray-300 rounded text-xs"
              />
              {CAUSE_REQUIRED.has(d.category || "") && (
                <input
                  type="text"
                  placeholder="Cause"
                  value={d.cause_text || ""}
                  onChange={(e) => updateDowntime(i, "cause_text", e.target.value)}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs"
                />
              )}
              <button type="button" onClick={() => removeDowntime(i)} className="text-red-500 text-xs px-2">
                X
              </button>
            </div>
          ))}
        </div>

        {message && (
          <div className={`text-sm p-3 rounded-lg ${
            message.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
          }`}>
            {message.text}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !mineId || !benchId}
          className="bg-gray-900 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
        >
          {submitting ? "Saving..." : "Save Draft"}
        </button>
      </form>

      {entries.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">
            My Entries
          </h3>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2">Shift</th>
                  <th className="px-3 py-2 text-right">Prod (t)</th>
                  <th className="px-3 py-2 text-right">OB (m3)</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className="px-3 py-2">{e.work_date}</td>
                    <td className="px-3 py-2 text-center">{e.shift_code}</td>
                    <td className="px-3 py-2 text-right font-mono">{milliToDisplay(e.production_milli_t)}</td>
                    <td className="px-3 py-2 text-right font-mono">{milliToDisplay(e.ob_milli_m3)}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                        e.status === "APPROVED" ? "bg-green-100 text-green-700" :
                        e.status === "SUBMITTED" ? "bg-blue-100 text-blue-700" :
                        e.status === "RETURNED" ? "bg-amber-100 text-amber-700" :
                        "bg-gray-100 text-gray-700"
                      }`}>
                        {e.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      {e.status === "DRAFT" && (
                        <button
                          onClick={() => handleAction(e.id, "submit")}
                          className="text-xs text-blue-600 hover:text-blue-800"
                        >
                          Submit
                        </button>
                      )}
                      {e.status === "RETURNED" && (
                        <button
                          onClick={() => handleAction(e.id, "submit")}
                          className="text-xs text-blue-600 hover:text-blue-800"
                        >
                          Resubmit
                        </button>
                      )}
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
