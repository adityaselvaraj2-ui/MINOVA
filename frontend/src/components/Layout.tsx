import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

interface NavItem {
  to: string;
  label: string;
  section: string;
  requireEnter?: boolean;
  requireApprove?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", section: "Operations" },
  { to: "/shift-entry", label: "Shift Entry", section: "Operations", requireEnter: true },
  { to: "/approvals", label: "Approvals", section: "Operations", requireApprove: true },
  { to: "/reports", label: "Reports", section: "Intelligence" },
  { to: "/documents", label: "Documents & Ask", section: "Intelligence" },
  { to: "/review", label: "Extraction Review", section: "Intelligence" },
  { to: "/topics", label: "Topics & Cloud", section: "Intelligence" },
  { to: "/analytics", label: "Analytics", section: "Intelligence" },
  { to: "/planning", label: "Rain Forecast & Plans", section: "Intelligence" },
  { to: "/health", label: "System Health", section: "System" },
];

const SECTION_ORDER = ["Operations", "Intelligence", "System"];

export default function Layout() {
  const { user, logout } = useAuth();

  const visible = NAV_ITEMS.filter((item) => {
    if (item.requireEnter && !user?.can_enter) return false;
    if (item.requireApprove && !user?.can_approve) return false;
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-100 flex">
      <aside className="w-60 bg-gray-900 text-gray-300 flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center text-gray-900 font-black text-sm">
              MT
            </div>
            <div>
              <h1 className="text-white font-bold leading-tight tracking-tight">
                MineTrace
              </h1>
              <p className="text-[10px] text-gray-500 uppercase tracking-widest">
                CMPDI · CIL Platform
              </p>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-5 overflow-y-auto">
          {SECTION_ORDER.map((section) => {
            const items = visible.filter((i) => i.section === section);
            if (items.length === 0) return null;
            return (
              <div key={section}>
                <p className="px-2 mb-1.5 text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
                  {section}
                </p>
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `block px-3 py-2 rounded-lg text-sm transition-colors ${
                          isActive
                            ? "bg-white/10 text-white font-medium"
                            : "text-gray-400 hover:text-white hover:bg-white/5"
                        }`
                      }
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="px-5 py-4 border-t border-white/10 text-[11px] text-gray-500 leading-relaxed">
          <p className="text-gray-400 font-medium">SIH26023 · Ministry of Coal</p>
          <p>Offline · On-prem · Zero cloud</p>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            AI-Powered Geological, Mining &amp; Reporting Solution
          </div>
          <div className="flex items-center gap-3 text-sm">
            <div className="text-right">
              <p className="text-gray-900 font-medium leading-tight">{user?.full_name}</p>
              <p className="text-xs text-gray-400 leading-tight">{user?.role_code}</p>
            </div>
            <div className="w-8 h-8 rounded-full bg-gray-900 text-white flex items-center justify-center text-xs font-bold">
              {user?.full_name?.split(" ").map((p) => p[0]).slice(0, 2).join("")}
            </div>
            <button
              onClick={logout}
              className="text-gray-400 hover:text-gray-700 text-sm ml-1"
            >
              Logout
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>

        <footer className="text-center text-[11px] text-gray-400 py-2.5 border-t border-gray-200 bg-white">
          MineTrace v0.1.0 — every number traceable, every answer cited, zero data leaves the premises
        </footer>
      </div>
    </div>
  );
}
