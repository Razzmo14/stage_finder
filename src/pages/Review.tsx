import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { invoke } from "@tauri-apps/api/core";
import { api } from "../lib/api";
import { diffWords } from "../lib/diff";

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
  email_body: string;
  letter_text: string;
  claims: { claim: string; supported: boolean; reason: string }[];
  flagged_claims: { claim: string; supported: boolean; reason: string }[];
  follow_up_date: string;
  offer: {
    id: number;
    title: string;
    company: string;
    location: string;
    description: string;
    url: string;
    contract_type: string;
  } | null;
  events: EventDto[];
}

async function streamRegenerate(applicationId: number, instructions: string, onChunk: (t: string) => void) {
  const backendUrl = await invoke<string>("get_backend_url");
  const token = await invoke<string>("get_session_token");
  const response = await fetch(`${backendUrl}/api/v1/letters/regenerate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ application_id: applicationId, instructions }),
  });
  if (!response.ok || !response.body) throw new Error(await response.text());
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

function DiffView({ before, after }: { before: string; after: string }) {
  const parts = diffWords(before, after);
  return (
    <div className="whitespace-pre-wrap rounded border border-neutral-200 bg-neutral-50 p-2 font-mono text-xs">
      {parts.map((p, i) => (
        <span
          key={i}
          className={
            p.added
              ? "bg-green-100 text-green-900"
              : p.removed
                ? "bg-red-100 text-red-900 line-through"
                : ""
          }
        >
          {p.value}
        </span>
      ))}
    </div>
  );
}

export default function ReviewPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [letter, setLetter] = useState("");
  const [instructions, setInstructions] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [showDiff, setShowDiff] = useState(true);
  const [baseLetter, setBaseLetter] = useState("");
  const letterAreaRef = useRef<HTMLTextAreaElement>(null);

  const queue = useQuery<ApplicationDto[]>({
    queryKey: ["applications", "reviewable"],
    queryFn: () => api.get<ApplicationDto[]>("/api/v1/applications"),
    select: (apps) =>
      apps.filter((a) => a.status === "pending_review" || a.status === "approved"),
  });

  const profile = useQuery<{ base_letter: string }>({
    queryKey: ["profile"],
    queryFn: () => api.get<{ base_letter: string }>("/api/v1/profile"),
  });

  useEffect(() => {
    setBaseLetter(profile.data?.base_letter ?? "");
  }, [profile.data]);

  const selected = (queue.data ?? []).find((a) => a.id === selectedId) ?? null;

  useEffect(() => {
    setLetter(selected?.letter_text ?? "");
  }, [selected?.id, selected?.letter_text]);

  const transition = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      api.post<ApplicationDto>(`/api/v1/applications/${id}/${action}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  const saveEdit = useMutation({
    mutationFn: () => api.patch<ApplicationDto>(`/api/v1/applications/${selectedId}`, { letter_text: letter }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [deliverMode, setDeliverMode] = useState<"draft" | "send">("draft");
  const [deliverMessage, setDeliverMessage] = useState<string | null>(null);

  const mailStatus = useQuery<{ gmail_connected: boolean; allow_direct_send: boolean }>({
    queryKey: ["mail-status"],
    queryFn: () => api.get<{ gmail_connected: boolean; allow_direct_send: boolean }>("/api/v1/mail/status"),
  });

  const deliver = useMutation({
    mutationFn: (mode: "draft" | "send") =>
      api.post<{ id: number; status: string }>(`/api/v1/applications/${selectedId}/deliver`, {
        mode,
        confirm: true,
      }),
    onSuccess: (result) => {
      setDeliverMessage(t("review.done", { status: result.status }));
      setConfirmOpen(false);
      setConfirmChecked(false);
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (e: Error) => {
      setDeliverMessage(e.message);
      setConfirmOpen(false);
      setConfirmChecked(false);
    },
  });

  const regenerate = async () => {
    if (!selectedId || !instructions.trim()) return;
    setStreaming(true);
    setLetter("");
    try {
      await streamRegenerate(selectedId, instructions, (chunk) => {
        setLetter((current) => current + chunk);
      });
    } catch (error) {
      setLetter(`Error: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setStreaming(false);
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">{t("review.title")}</h2>

      <div className="flex gap-4">
        <div className="w-64 shrink-0 rounded border border-neutral-200 bg-white p-2">
          <ul>
            {(queue.data ?? []).map((application) => (
              <li key={application.id}>
                <button
                  className={`w-full rounded px-2 py-1 text-left text-sm hover:bg-neutral-100 ${
                    application.id === selectedId ? "bg-neutral-100 font-medium" : ""
                  }`}
                  onClick={() => setSelectedId(application.id)}
                >
                  {application.offer?.title ?? "#" + application.id}
                  {application.flagged_claims.length > 0 && (
                    <span className="ml-1 text-xs text-red-600">
                      ({t("review.flagged", { count: application.flagged_claims.length })})
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
          {(queue.data ?? []).length === 0 && (
            <p className="p-2 text-sm text-neutral-500">{t("review.nothingPending")}</p>
          )}
        </div>

        {selected ? (
          <div className="flex flex-1 gap-4">
            <div className="w-1/2 space-y-2 rounded border border-neutral-200 bg-white p-3 text-sm">
              <h3 className="font-semibold">{selected.offer?.title}</h3>
              <p className="text-neutral-600">
                {selected.offer?.company} · {selected.offer?.location} · {selected.offer?.contract_type}
              </p>
              <a className="text-blue-700 underline" href={selected.offer?.url} target="_blank" rel="noreferrer">
                {t("review.originalOffer")}
              </a>
              <p className="max-h-80 overflow-y-auto whitespace-pre-wrap text-neutral-700">
                {selected.offer?.description}
              </p>
              <div>
                <h4 className="font-medium text-red-700">{t("review.flaggedClaims")}</h4>
                <ul className="list-disc pl-5">
                  {selected.flagged_claims.map((c, i) => (
                    <li key={i} className="bg-red-50 text-red-800">
                      {c.claim} {c.reason && <em className="text-xs">({c.reason})</em>}
                    </li>
                  ))}
                </ul>
                {selected.flagged_claims.length === 0 && (
                  <p className="text-xs text-neutral-500">{t("review.noFlaggedClaims")}</p>
                )}
              </div>
            </div>

            <div className="flex w-1/2 flex-col gap-2 rounded border border-neutral-200 bg-white p-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">{t("review.letter")}</h3>
                <label className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
                  {t("review.diffToggle")}
                </label>
              </div>

              {showDiff ? (
                <DiffView before={baseLetter} after={letter} />
              ) : (
                <textarea
                  ref={letterAreaRef}
                  className="h-64 w-full rounded border border-neutral-300 p-2 font-mono text-xs"
                  value={letter}
                  onChange={(e) => setLetter(e.target.value)}
                />
              )}

              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
                  placeholder={t("review.instructionsPlaceholder")}
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && regenerate()}
                />
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-sm disabled:opacity-50"
                  disabled={streaming || !instructions.trim()}
                  onClick={regenerate}
                >
                  {streaming ? t("review.generating") : t("review.regenerate")}
                </button>
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-sm"
                  disabled={streaming || letter === selected.letter_text}
                  onClick={() => saveEdit.mutate()}
                >
                  {t("review.saveEdit")}
                </button>
              </div>

              <div className="mt-2 flex gap-2">
                {selected.status === "pending_review" && (
                  <button
                    className="rounded bg-neutral-900 px-3 py-1 text-sm text-white"
                    onClick={() => transition.mutate({ id: selected.id, action: "approve" })}
                  >
                    {t("review.approve")}
                  </button>
                )}
                {selected.status === "approved" && (
                  <button
                    className="rounded bg-neutral-900 px-3 py-1 text-sm text-white"
                    disabled={!mailStatus.data?.gmail_connected}
                    onClick={() => {
                      setDeliverMode("draft");
                      setDeliverMessage(null);
                      setConfirmOpen(true);
                    }}
                  >
                    {t("review.deliver")}
                  </button>
                )}
                <button
                  className="rounded border border-neutral-300 px-3 py-1 text-sm"
                  onClick={() => transition.mutate({ id: selected.id, action: "save-for-later" })}
                >
                  {t("review.saveForLater")}
                </button>
                <button
                  className="rounded border border-red-300 px-3 py-1 text-sm text-red-700"
                  onClick={() => transition.mutate({ id: selected.id, action: "reject" })}
                >
                  {t("review.reject")}
                </button>
              </div>
              {deliverMessage && <p className="text-xs text-neutral-700">{deliverMessage}</p>}
              <p className="text-xs text-neutral-500">
                {t("review.hardRule")}
              </p>

              {confirmOpen && selected && (
                <div className="fixed inset-0 flex items-center justify-center bg-black/40">
                  <div className="w-96 rounded bg-white p-4 shadow-lg">
                    <h3 className="font-semibold">{t("review.confirmTitle")}</h3>
                    <ul className="mt-2 space-y-1 text-sm">
                      <li><span className="text-neutral-500">{t("review.recipient")}:</span> {selected.recipient}</li>
                      <li><span className="text-neutral-500">{t("review.subject")}:</span> {selected.email_subject}</li>
                      <li><span className="text-neutral-500">{t("review.letterChars")}:</span> {letter.length} characters</li>
                      <li><span className="text-neutral-500">{t("review.attachments")}:</span> {t("common.none")}</li>
                    </ul>
                    <div className="mt-3 flex gap-2 text-sm">
                      <label className="flex items-center gap-1">
                        <input
                          type="radio"
                          checked={deliverMode === "draft"}
                          onChange={() => setDeliverMode("draft")}
                        />
                        {t("review.createDraft")}
                      </label>
                      <label className={`flex items-center gap-1 ${!mailStatus.data?.allow_direct_send ? "text-neutral-400" : ""}`}>
                        <input
                          type="radio"
                          checked={deliverMode === "send"}
                          onChange={() => setDeliverMode("send")}
                          disabled={!mailStatus.data?.allow_direct_send}
                        />
                        {t("review.sendDirectly")}
                      </label>
                    </div>
                    <label className="mt-3 flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={confirmChecked}
                        onChange={(e) => setConfirmChecked(e.target.checked)}
                      />
                      {t("review.confirmCheckbox")}
                    </label>
                    <div className="mt-3 flex justify-end gap-2">
                      <button
                        className="rounded border border-neutral-300 px-3 py-1 text-sm"
                        onClick={() => setConfirmOpen(false)}
                      >
                        {t("common.cancel")}
                      </button>
                      <button
                        className="rounded bg-neutral-900 px-3 py-1 text-sm text-white disabled:opacity-50"
                        disabled={!confirmChecked || deliver.isPending}
                        onClick={() => deliver.mutate(deliverMode)}
                      >
                        {deliverMode === "draft" ? t("review.createDraftButton") : t("review.sendButton")}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-neutral-500">{t("review.selectApplication")}</p>
        )}
      </div>
    </div>
  );
}
