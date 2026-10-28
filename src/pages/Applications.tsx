import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

interface EventDto {
  event_type: string;
  detail: string;
  created_at: string;
}

interface ApplicationDto {
  id: number;
  offer_id: number;
  status: string;
  recipient: string;
  email_subject: string;
  letter_text: string;
  follow_up_date: string;
  offer: { id: number; title: string; company: string; location: string; url: string } | null;
  events: EventDto[];
}

const COLUMNS = [
  { key: "pending_review", label: "Pending review" },
  { key: "approved", label: "Approved" },
  { key: "draft_saved", label: "Draft saved" },
  { key: "sent", label: "Sent" },
  { key: "draft", label: "Saved for later" },
  { key: "rejected", label: "Rejected" },
];

export default function ApplicationsPage() {
  const [view, setView] = useState<"kanban" | "list">("kanban");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const applications = useQuery<ApplicationDto[]>({
    queryKey: ["applications"],
    queryFn: () => api.get<ApplicationDto[]>("/api/v1/applications"),
  });

  const rows = applications.data ?? [];
  const selected = rows.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Applications ({rows.length})</h2>
        <div className="flex gap-1 text-sm">
          {(["kanban", "list"] as const).map((mode) => (
            <button
              key={mode}
              className={`rounded px-2 py-1 ${view === mode ? "bg-neutral-900 text-white" : "border border-neutral-300"}`}
              onClick={() => setView(mode)}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto">
          {COLUMNS.map((column) => {
            const items = rows.filter((a) => a.status === column.key);
            return (
              <div key={column.key} className="w-64 shrink-0 rounded border border-neutral-200 bg-white p-2">
                <h3 className="text-sm font-semibold">
                  {column.label} <span className="text-neutral-400">({items.length})</span>
                </h3>
                <ul className="mt-2 space-y-2">
                  {items.map((application) => (
                    <li key={application.id}>
                      <button
                        className={`w-full rounded border p-2 text-left text-xs hover:bg-neutral-50 ${
                          application.id === selectedId ? "border-neutral-900" : "border-neutral-200"
                        }`}
                        onClick={() => setSelectedId(application.id)}
                      >
                        <span className="font-medium">{application.offer?.title ?? `#${application.id}`}</span>
                        <br />
                        <span className="text-neutral-500">{application.offer?.company}</span>
                        {application.follow_up_date && (
                          <>
                            <br />
                            <span className="text-amber-700">Follow-up: {application.follow_up_date}</span>
                          </>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      ) : (
        <table className="w-full max-w-4xl text-sm">
          <thead className="text-left text-xs uppercase text-neutral-500">
            <tr>
              <th className="py-1">Offer</th>
              <th className="py-1">Status</th>
              <th className="py-1">Recipient</th>
              <th className="py-1">Follow-up</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((application) => (
              <tr
                key={application.id}
                className="cursor-pointer border-t border-neutral-100 hover:bg-neutral-50"
                onClick={() => setSelectedId(application.id)}
              >
                <td className="py-1">
                  {application.offer?.title ?? `#${application.id}`}{" "}
                  <span className="text-neutral-500">{application.offer?.company}</span>
                </td>
                <td className="py-1">{application.status}</td>
                <td className="py-1">{application.recipient || "—"}</td>
                <td className="py-1">{application.follow_up_date || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <div className="max-w-2xl rounded border border-neutral-200 bg-white p-4">
          <h3 className="font-semibold">{selected.offer?.title ?? `Application #${selected.id}`}</h3>
          <p className="text-sm text-neutral-600">
            {selected.offer?.company} · status {selected.status} · recipient {selected.recipient || "?"}
          </p>
          <h4 className="mt-3 text-sm font-semibold">Timeline</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {selected.events.map((event, i) => (
              <li key={i} className="flex gap-2">
                <span className="w-40 shrink-0 text-xs text-neutral-400">{event.created_at}</span>
                <span className="font-medium">{event.event_type}</span>
                {event.detail && <span className="text-neutral-500">{event.detail}</span>}
              </li>
            ))}
            {selected.events.length === 0 && <li className="text-neutral-500">No events yet.</li>}
          </ul>
          {selected.follow_up_date && (
            <p className="mt-3 text-sm text-amber-700">Follow-up reminder: {selected.follow_up_date}</p>
          )}
        </div>
      )}
    </div>
  );
}
