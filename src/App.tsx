import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type HealthState =
  | { kind: "checking" }
  | { kind: "ok"; url: string }
  | { kind: "unreachable"; url: string; detail: string }
  | { kind: "outside-tauri" };

const NAV_ITEMS = [
  "Overview",
  "Profile",
  "Search & Offers",
  "Review queue",
  "Applications",
  "Settings",
] as const;

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

function healthLabel(state: HealthState): string {
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
          {NAV_ITEMS.map((item) => (
            <button
              key={item}
              className="px-4 py-2 text-left text-sm hover:bg-neutral-800"
              disabled
            >
              {item}
            </button>
          ))}
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <main className="flex-1 overflow-y-auto p-6">
          <p className="text-neutral-500">
            Skeleton is running. Feature screens arrive with the matching feature in
            feature_list.json.
          </p>
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
