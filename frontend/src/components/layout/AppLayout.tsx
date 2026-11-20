import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { useAuth } from "../../lib/auth";
import { Icon, type IconName } from "../ui/icons";
import Logo from "./Logo";

type Item = { to: string; label: string; icon: IconName; end?: boolean };
const MAIN: Item[] = [
  { to: "/app", label: "Dashboard", icon: "home", end: true },
  { to: "/app/diagnose", label: "Diagnose", icon: "scan" },
  { to: "/app/diagnoses", label: "History & reports", icon: "history" },
  { to: "/app/plants", label: "My plants", icon: "sprout" },
  { to: "/app/assistant", label: "Assistant", icon: "chat" },
  { to: "/app/knowledge", label: "Disease library", icon: "book" },
  { to: "/app/weather", label: "Weather & risk", icon: "cloud" },
];
const ADMIN: Item[] = [
  { to: "/admin", label: "Overview", icon: "chart", end: true },
  { to: "/admin/users", label: "Users", icon: "users" },
  { to: "/admin/models", label: "Models", icon: "cpu" },
  { to: "/admin/review", label: "Review queue", icon: "flag" },
  { to: "/admin/datasets", label: "Datasets", icon: "database" },
  { to: "/admin/system", label: "System & audit", icon: "shield" },
];

function NavItem({ it, onClick }: { it: Item; onClick?: () => void }) {
  return (
    <NavLink to={it.to} end={it.end} onClick={onClick}
      className={({ isActive }) => clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors focus-ring",
        isActive ? "bg-forest-800 text-white" : "text-ink-2 hover:bg-paper-2 hover:text-ink")}>
      <Icon name={it.icon} size={19} />{it.label}
    </NavLink>
  );
}

export default function AppLayout({ admin }: { admin?: boolean }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [more, setMore] = useState(false);
  const items = admin ? ADMIN : MAIN;
  const doLogout = async () => { await logout(); nav("/"); };
  return (
    <div className="min-h-screen lg:pl-64">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-line bg-white lg:flex" aria-label="Sidebar">
        <div className="flex h-16 items-center px-5"><Logo to="/app" /></div>
        <nav aria-label={admin ? "Admin" : "App"} className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
          {admin && <p className="px-3 pb-2 pt-1 text-2xs font-semibold uppercase tracking-wider text-ink-4">Administration</p>}
          {items.map((it) => <NavItem key={it.to} it={it} />)}
          <div className="my-3 border-t border-line" />
          {admin ? <NavItem it={{ to: "/app", label: "Back to app", icon: "arrowLeft" }} />
            : user?.role === "admin" && <NavItem it={{ to: "/admin", label: "Admin", icon: "shield" }} />}
          <NavItem it={{ to: "/app/settings", label: "Settings", icon: "settings" }} />
        </nav>
        <div className="border-t border-line p-3">
          <div className="flex items-center gap-3 rounded-xl px-2 py-2">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-forest-100 text-sm font-semibold text-forest-800">{user?.name.slice(0, 1).toUpperCase()}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{user?.name}</p>
              <p className="truncate text-xs text-ink-3">{user?.email}</p>
            </div>
            <button onClick={doLogout} className="rounded-lg p-2 text-ink-3 hover:bg-paper-2 hover:text-ink focus-ring" aria-label="Sign out" title="Sign out"><Icon name="logout" size={18} /></button>
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur lg:hidden">
        <Logo to="/app" />
        <Link to="/app/settings" className="grid h-9 w-9 place-items-center rounded-full bg-forest-100 text-sm font-semibold text-forest-800 focus-ring" aria-label="Settings">
          {user?.name.slice(0, 1).toUpperCase()}
        </Link>
      </header>

      <main id="main" className="mx-auto max-w-page px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-12 lg:pt-10"><Outlet /></main>

      {/* Mobile bottom nav */}
      <nav aria-label="App" className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/95 backdrop-blur lg:hidden">
        <div className="grid grid-cols-5 items-end px-2 pt-1.5">
          {[items[0], items[2], null, items[4], undefined].map((it) => {
            if (it === null) return (
              <Link key="scan" to={admin ? "/app/diagnose" : "/app/diagnose"} className="-mt-6 flex flex-col items-center gap-1 focus-ring rounded-xl" aria-label="Diagnose a plant">
                <span className="grid h-14 w-14 place-items-center rounded-2xl bg-forest-800 text-white shadow-lift"><Icon name="camera" size={24} /></span>
                <span className="text-2xs font-medium text-ink-2">Diagnose</span>
              </Link>);
            if (it === undefined) return (
              <button key="more" onClick={() => setMore(true)} className="flex flex-col items-center gap-1 py-1.5 text-ink-3 focus-ring rounded-xl" aria-haspopup="dialog">
                <Icon name="menu" size={22} /><span className="text-2xs font-medium">More</span>
              </button>);
            return (
              <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => clsx("flex flex-col items-center gap-1 py-1.5 focus-ring rounded-xl", isActive ? "text-forest-800" : "text-ink-3")}>
                <Icon name={it.icon} size={22} /><span className="text-2xs font-medium">{it.label.split(" ")[0]}</span>
              </NavLink>);
          })}
        </div>
      </nav>
      {more && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="More">
          <button className="absolute inset-0 bg-ink/30" aria-label="Close menu" onClick={() => setMore(false)} />
          <div className="safe-bottom absolute inset-x-0 bottom-0 rounded-t-3xl bg-white p-4 shadow-lift">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-strong" />
            <div className="space-y-1">
              {items.map((it) => <NavItem key={it.to} it={it} onClick={() => setMore(false)} />)}
              {!admin && user?.role === "admin" && <NavItem it={{ to: "/admin", label: "Admin", icon: "shield" }} onClick={() => setMore(false)} />}
              {admin && <NavItem it={{ to: "/app", label: "Back to app", icon: "arrowLeft" }} onClick={() => setMore(false)} />}
              <NavItem it={{ to: "/app/settings", label: "Settings", icon: "settings" }} onClick={() => setMore(false)} />
              <button onClick={doLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-ink-2 hover:bg-paper-2"><Icon name="logout" size={19} />Sign out</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
