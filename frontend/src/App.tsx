import { useEffect, useState } from "react";
import "./App.css";
import { fetchHealth, type HealthResponse } from "./api/client";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ok: "bg-green-100 text-green-800 border-green-300",
    degraded: "bg-yellow-100 text-yellow-800 border-yellow-300",
    error: "bg-red-100 text-red-800 border-red-300",
    unavailable: "bg-gray-100 text-gray-600 border-gray-300",
    loading: "bg-blue-100 text-blue-800 border-blue-300",
  };
  const cls = colors[status] || colors.error;
  return (
    <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium border ${cls}`}>
      {status.toUpperCase()}
    </span>
  );
}

function HealthCard({
  title,
  status,
  details,
}: {
  title: string;
  status: string;
  details: Record<string, string | boolean | undefined>;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <StatusBadge status={status} />
      </div>
      <div className="space-y-2">
        {Object.entries(details).map(([key, val]) =>
          val !== undefined ? (
            <div key={key} className="flex justify-between text-sm">
              <span className="text-gray-500">{key}</span>
              <span className="text-gray-900 font-mono">
                {typeof val === "boolean" ? (val ? "Yes" : "No") : String(val)}
              </span>
            </div>
          ) : null
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetchHealth()
        .then((h) => {
          if (!cancelled) {
            setHealth(h);
            setError(null);
            setLoading(false);
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setError(e.message);
            setLoading(false);
          }
        });
    };
    check();
    const interval = setInterval(check, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-gray-900 text-white px-8 py-6">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-bold tracking-tight">MineTrace</h1>
          <p className="text-gray-400 text-sm mt-1">
            Offline Source-to-Report Intelligence Platform
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-900">System Health</h2>
          {health && <StatusBadge status={health.status} />}
          {loading && <StatusBadge status="loading" />}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-6">
            <h3 className="text-red-800 font-semibold mb-1">Backend Unavailable</h3>
            <p className="text-red-600 text-sm">{error}</p>
            <p className="text-red-500 text-xs mt-2">
              Make sure the FastAPI backend is running on 127.0.0.1:19823
            </p>
          </div>
        )}

        {health && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <HealthCard
              title="Application"
              status={health.status}
              details={{
                Version: health.version,
                "Netguard Active": health.netguard_active,
              }}
            />
            <HealthCard
              title="Database"
              status={health.database.status}
              details={{
                Path: health.database.path,
                ...(health.database.detail ? { Detail: health.database.detail } : {}),
              }}
            />
            <HealthCard
              title="Ollama (AI Engine)"
              status={health.ollama.status}
              details={{
                "Primary Model": health.ollama.primary_available ? "Available" : "Missing",
                "Secondary Model": health.ollama.secondary_available ? "Available" : "Missing",
                ...(health.ollama.detail ? { Detail: health.ollama.detail } : {}),
              }}
            />
            <HealthCard
              title="Security"
              status={health.netguard_active ? "ok" : "degraded"}
              details={{
                "Network Guard": health.netguard_active ? "Active" : "Inactive",
                "Data Sovereignty": "Local Only",
                "Cloud Calls": "Blocked",
              }}
            />
          </div>
        )}

        {!health && !error && loading && (
          <div className="text-center py-16">
            <div className="inline-block w-8 h-8 border-4 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
            <p className="mt-4 text-gray-500">Connecting to backend...</p>
          </div>
        )}
      </main>

      <footer className="max-w-4xl mx-auto px-8 py-4 text-center text-xs text-gray-400">
        MineTrace v0.1.0 — SIH26023 — Ministry of Coal
      </footer>
    </div>
  );
}
