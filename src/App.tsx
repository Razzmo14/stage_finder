import { useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { api } from "./lib/api";
import { LANGUAGES, setLanguage } from "./i18n";
import Settings from "./pages/Settings";
import Overview from "./pages/Overview";
import ProfilePage from "./pages/Profile";
import SearchPage from "./pages/Search";
import ReviewPage from "./pages/Review";
import ApplicationsPage from "./pages/Applications";

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

function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  return (
    <div className="mt-auto flex items-center gap-2 px-4 py-3 text-xs text-neutral-300">
      <span>{t("common.language")}</span>
      {LANGUAGES.map((code) => (
        <button
          key={code}
          className={`rounded px-2 py-0.5 ${
            i18n.language === code ? "bg-neutral-700 text-white" : "hover:bg-neutral-800"
          }`}
          onClick={() => setLanguage(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

interface FollowUpDto {
  application_id: number;
  follow_up_date: string;
  status: string;
  offer_title: string;
}

function FollowUpWatcher() {
  const { t } = useTranslation();
  const notified = useRef<Set<number>>(new Set());
  const followUps = useQuery<FollowUpDto[]>({
    queryKey: ["follow-ups"],
    queryFn: () => api.get<FollowUpDto[]>("/api/v1/follow-ups"),
    refetchInterval: 60000,
  });
  const [banner, setBanner] = useState<FollowUpDto[]>([]);

  useEffect(() => {
    const due = followUps.data ?? [];
    const fresh = due.filter((f) => !notified.current.has(f.application_id));
    if (fresh.length === 0) return;
    fresh.forEach((f) => notified.current.add(f.application_id));
    setBanner((current) => [...current, ...fresh]);
    fresh.forEach((f) => {
      try {
        new Notification(t("followUp.notification"), {
          body: `${f.offer_title}: ${t("followUp.plannedFor", { date: f.follow_up_date })}`,
        });
      } catch {
        // Notification API unavailable; the in-app banner still shows.
      }
    });
  }, [followUps.data, t]);

  if (banner.length === 0) return null;
  return (
    <div className="flex items-center justify-between gap-4 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <span>
        {t("followUp.banner", {
          count: banner.length,
          titles: banner.map((b) => b.offer_title).join(", "),
        })}
      </span>
      <button className="underline" onClick={() => setBanner([])}>
        {t("common.dismiss")}
      </button>
    </div>
  );
}

function StatusBar() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<HealthState>({ kind: "checking" });

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  const label =
    health.kind === "checking"
      ? t("health.checking")
      : health.kind === "ok"
        ? t("health.ok", { url: health.url })
        : health.kind === "unreachable"
          ? t("health.unreachable", { url: health.url, detail: health.detail })
          : t("health.outside");

  return (
    <footer className="flex items-center gap-4 border-t border-neutral-200 bg-white px-4 py-2 text-xs text-neutral-600">
      <span>{label}</span>
      <button
        className="underline hover:text-neutral-900"
        onClick={() => {
          setHealth({ kind: "checking" });
          checkHealth().then(setHealth);
        }}
      >
        {t("common.refresh")}
      </button>
    </footer>
  );
}

const NAV = [
  { to: "/", key: "nav.overview" },
  { to: "/profile", key: "nav.profile" },
  { to: "/search", key: "nav.search" },
  { to: "/review", key: "nav.review" },
  { to: "/applications", key: "nav.applications" },
  { to: "/settings", key: "nav.settings" },
];

export default function App() {
  const { t } = useTranslation();
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
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <LanguageSwitcher />
      </aside>
      <div className="flex flex-1 flex-col">
        <FollowUpWatcher />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route
              path="*"
              element={<p className="text-neutral-500">{t("overview.pending")}</p>}
            />
          </Routes>
        </main>
        <StatusBar />
      </div>
    </div>
  );
}
