import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/shift-entry", label: "Shift Entry", requireEnter: true },
  { to: "/approvals", label: "Approvals", requireApprove: true },
  { to: "/reports", label: "Reports" },
  { to: "/health", label: "System" },
];

export default function Layout() {
  const { user, logout } = useAuth();

  const visibleNav = NAV_ITEMS.filter((item) => {
    if (item.requireEnter && !user?.can_enter) return false;
    if (item.requireApprove && !user?.can_approve) return false;
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-bold tracking-tight">MineTrace</h1>
          <nav className="flex gap-1">
            {visibleNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${
                    isActive
                      ? "bg-white/15 text-white font-medium"
                      : "text-gray-400 hover:text-white hover:bg-white/5"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-400">
            {user?.full_name}
            <span className="ml-2 text-xs bg-gray-700 px-2 py-0.5 rounded">
              {user?.role_code}
            </span>
          </span>
          <button
            onClick={logout}
            className="text-gray-400 hover:text-white text-sm"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-6">
        <Outlet />
      </main>

      <footer className="text-center text-xs text-gray-400 py-3 border-t border-gray-200">
        MineTrace v0.1.0 — SIH26023 — Ministry of Coal
      </footer>
    </div>
  );
}
