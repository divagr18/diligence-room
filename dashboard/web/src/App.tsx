import { NavLink, Route, Routes } from "react-router-dom";
import { FileSearch, FileStack, LayoutDashboard, ShieldCheck, Vault } from "lucide-react";
import Documents from "./views/Documents";
import Findings from "./views/Findings";
import FindingDetail from "./views/FindingDetail";
import Overview from "./views/Overview";
import Registry from "./views/Registry";
import Security from "./views/Security";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/findings", label: "Findings", icon: FileSearch, end: false },
  { to: "/documents", label: "Documents", icon: FileStack, end: false },
  { to: "/security", label: "Security", icon: ShieldCheck, end: false },
  { to: "/registry", label: "Registry", icon: Vault, end: false },
];

function Shell() {
  return (
    <div className="flex min-h-dvh">
      <aside className="fixed inset-y-0 left-0 z-10 hidden w-[232px] flex-col border-r border-line bg-panel md:flex">
        <div className="border-b border-line px-5 py-5">
          <div className="text-[15px] font-semibold tracking-tight text-ink1">
            Project Falcon
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-ink4">deal-falcon · acquisition</div>
        </div>
        <nav className="flex-1 px-3 py-4" aria-label="Primary">
          <ul className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  aria-current="page"
                  className={({ isActive }) =>
                    `group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150 ${
                      isActive
                        ? "bg-card2 text-ink1 before:absolute before:inset-y-1 before:left-0 before:w-[2px] before:rounded-full before:bg-accent"
                        : "text-ink3 hover:bg-card2 hover:text-ink2"
                    }`
                  }
                >
                  <Icon className="size-4" strokeWidth={1.75} aria-hidden />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="border-t border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-ok" aria-hidden />
            <span className="text-[12px] text-ink3">8 agents active</span>
          </div>
          <div className="mt-1 font-mono text-[11px] text-ink4">zero-trust runtime · v0.1</div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="fixed inset-x-0 top-0 z-10 flex items-center justify-between border-b border-line bg-panel px-4 py-3 md:hidden">
        <div>
          <div className="text-[14px] font-semibold text-ink1">Project Falcon</div>
        </div>
        <nav aria-label="Primary">
          <ul className="flex items-center gap-1">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `flex items-center gap-1 rounded-md px-2 py-1.5 text-[12px] font-medium ${
                      isActive ? "bg-card2 text-ink1" : "text-ink3"
                    }`
                  }
                >
                  <Icon className="size-3.5" strokeWidth={1.75} aria-hidden />
                  <span className="hidden sm:inline">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="min-w-0 flex-1 pt-[64px] md:ml-[232px] md:pt-0">
        <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-8 md:py-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/findings" element={<Findings />} />
            <Route path="/findings/:findingId" element={<FindingDetail />} />
            <Route path="/documents" element={<Documents />} />
        <Route path="/security" element={<Security />} />
            <Route path="/registry" element={<Registry />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return <Shell />;
}
