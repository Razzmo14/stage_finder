import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import Settings from "./pages/Settings";
import Overview from "./pages/Overview";
import ProfilePage from "./pages/Profile";
import SearchPage from "./pages/Search";

export type HealthState =
  | { kind: "checking" }
  | { kind: "ok"; url: string }
  | { kind: "unreachable"; url: string; detail: string }
  | { kind: "outside-tauri" };

async function checkHealth(): Promise<HealthState> {
  let backendUrl: string;
  let sessionToken: string;
  try {
    backendUrl = await invoke<string>("get_backend_url");
    sessionToken = await invoke<string>("get_session_token");
  } catch {
    return { kind: "outside-tauri" };
  }
  try {
    const response = await fetch(`${backendUrl}/health`, {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (!response.ok) {
      return { kind: "unreachable", url: backendUrl, detail: `HTTP ${response.status}` };
    }
    return { kind: "ok", url: backendUrl };
  } catch (error) {
    return {
      kind: "unreachable",
      url: backendUrl,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

export function healthLabel(state: HealthState): string {
  switch (state.kind) {
    case "checking":
      return "Sidecar: checking...";
    case "ok":
      return `Sidecar: healthy (${state.url})`;
    case "unreachable":
      return `Sidecar: unreachable (${state.url}) — ${state.detail}`;
    case "outside-tauri":
      return "Sidecar: n/a (running outside the Tauri shell)";
  }
}

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/profile", label: "Profile" },
  { to: "/search", label: "Search & Offers" },
  { to: "/review", label: "Review queue" },
  { to: "/applications", label: "Applications" },
  { to: "/settings", label: "Settings" },
];

export default function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "checking" });

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  return (
    <div className="flex h-screen text-neutral-900">
      <aside className="flex w-56 shrink-0 flex-col border-r border-neutral-200 bg-neutral-900 text-neutral-100">
        <h1 className="px-4 py-4 text-lg font-semibold">Stage Finder</h1>
        <nav className="flex flex-col">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `px-4 py-2 text-sm hover:bg-neutral-800 ${isActive ? "bg-neutral-800 font-medium" : ""}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route
              path="*"
              element={<p className="text-neutral-500">This screen arrives with its feature.</p>}
            />
          </Routes>
        </main>
        <footer className="flex items-center gap-4 border-t border-neutral-200 bg-white px-4 py-2 text-xs text-neutral-600">
          <span>{healthLabel(health)}</span>
          <button
            className="underline hover:text-neutral-900"
            onClick={() => {
              setHealth({ kind: "checking" });
              checkHealth().then(setHealth);
            }}
          >
            refresh
          </button>
        </footer>
      </div>
    </div>
  );
}
