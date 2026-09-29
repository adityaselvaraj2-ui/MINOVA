import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";

export default function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetchHealth()
        .then((h) => { if (!cancelled) { setHealth(h); setError(null); } })
        .catch((e) => { if (!cancelled) setError(e.message); });
    };
    check();
    const interval = setInterval(check, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-900">System Health</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <p className="text-red-700 font-medium">Backend Unavailable</p>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      )}

      {health && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card title="Application" status={health.status}>
            <Row label="Version" value={health.version} />
            <Row label="Netguard" value={health.netguard_active ? "Active" : "Inactive"} />
          </Card>
          <Card title="Database" status={health.database.status}>
            <Row label="Path" value={health.database.path || "N/A"} />
          </Card>
          <Card title="Ollama (AI)" status={health.ollama.status}>
            <Row label="Primary" value={health.ollama.primary_available ? "Ready" : "Missing"} />
            <Row label="Secondary" value={health.ollama.secondary_available ? "Ready" : "Missing"} />
          </Card>
          <Card title="Security" status={health.netguard_active ? "ok" : "degraded"}>
            <Row label="Network Guard" value={health.netguard_active ? "Active" : "Inactive"} />
            <Row label="Data Sovereignty" value="Local Only" />
          </Card>
        </div>
      )}
    </div>
  );
}

function Card({ title, status, children }: { title: string; status: string; children: React.ReactNode }) {
  const colors: Record<string, string> = {
    ok: "border-green-200",
    degraded: "border-amber-200",
    error: "border-red-200",
  };
  return (
    <div className={`bg-white rounded-xl border p-5 ${colors[status] || "border-gray-200"}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900">{title}</h3>
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
          status === "ok" ? "bg-green-100 text-green-700" :
          status === "degraded" ? "bg-amber-100 text-amber-700" :
          "bg-red-100 text-red-700"
        }`}>
          {status.toUpperCase()}
        </span>
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-900 font-mono text-xs">{value}</span>
    </div>
  );
}
