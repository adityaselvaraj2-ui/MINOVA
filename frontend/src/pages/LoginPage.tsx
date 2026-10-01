import { useState } from "react";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex">
      {/* Left brand panel */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] p-10 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900" />
        <div className="absolute -bottom-32 -right-32 w-96 h-96 rounded-full bg-amber-500/10 blur-3xl" />
        <div className="absolute -top-24 -left-24 w-72 h-72 rounded-full bg-blue-500/10 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500 flex items-center justify-center text-gray-900 font-black">
            MT
          </div>
          <div>
            <h1 className="text-white font-bold text-lg tracking-tight">MineTrace</h1>
            <p className="text-gray-400 text-xs uppercase tracking-widest">
              CMPDI · CIL Subsidiaries
            </p>
          </div>
        </div>

        <div className="relative">
          <h2 className="text-3xl font-bold text-white leading-tight">
            Every number traceable.
            <br />
            Every answer cited.
          </h2>
          <p className="text-gray-400 mt-4 max-w-md text-sm leading-relaxed">
            AI-powered geological, mining and reporting platform for the
            Ministry of Coal. Deterministic aggregation, local AI models and
            full data lineage — deployed entirely on-premise.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-4 max-w-md">
            {[
              ["3", "SIH modules"],
              ["100%", "On-premise"],
              ["Traceable", "Every figure"],
            ].map(([v, l]) => (
              <div key={l} className="border border-white/10 rounded-xl p-3 bg-white/5">
                <p className="text-amber-400 font-bold text-lg">{v}</p>
                <p className="text-gray-400 text-xs mt-0.5">{l}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-gray-600 text-xs">
          Smart India Hackathon 2026 · Problem SIH26023 · Ministry of Coal
        </p>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center bg-gray-50 p-8">
        <div className="w-full max-w-sm">
          <div className="lg:hidden text-center mb-8">
            <div className="w-12 h-12 mx-auto rounded-xl bg-amber-500 flex items-center justify-center text-gray-900 font-black text-lg">
              MT
            </div>
            <h1 className="text-2xl font-bold text-gray-900 mt-3">MineTrace</h1>
          </div>

          <h2 className="text-xl font-semibold text-gray-900">Sign in</h2>
          <p className="text-sm text-gray-500 mt-1">
            Access the reporting platform
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500 outline-none transition"
                autoFocus
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500 outline-none transition"
                required
              />
            </div>

            {error && (
              <p className="text-red-600 text-sm bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gray-900 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition-colors"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>

            <p className="text-xs text-gray-400 text-center pt-2">
              Demo credentials: admin / demo123
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
