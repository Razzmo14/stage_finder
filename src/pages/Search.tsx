import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

interface CriteriaDto {
  id: number;
  name: string;
  keywords: string[];
  location: string;
  radius_km: number | null;
  contract_types: string[];
  remote: boolean;
  sources: string[];
  enabled: boolean;
}

interface OfferDto {
  id: number;
  source: string;
  source_id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  contract_type: string;
  published_at: string;
  seen: boolean;
  ignored: boolean;
  match: {
    score: number;
    rationale: string;
    matched_skills: string[];
    missing_skills: string[];
    red_flags: string[];
    model: string;
  } | null;
}

const EMPTY_CRITERIA = {
  name: "",
  keywords: "",
  location: "",
  contract_types: "",
  sources: "france_travail",
};

export default function SearchPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_CRITERIA);
  const [message, setMessage] = useState<string | null>(null);

  const criteria = useQuery<CriteriaDto[]>({
    queryKey: ["criteria"],
    queryFn: () => api.get<CriteriaDto[]>("/api/v1/criteria"),
  });

  const offers = useQuery<OfferDto[]>({
    queryKey: ["offers"],
    queryFn: () => api.get<OfferDto[]>("/api/v1/offers?sort=score"),
  });

  const runMatching = useMutation({
    mutationFn: () => api.post<unknown[]>("/api/v1/match/run", { top_n: 10 }),
    onSuccess: () => {
      setMessage("Matching done.");
      queryClient.invalidateQueries({ queryKey: ["offers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const createCriteria = useMutation({
    mutationFn: () =>
      api.post<CriteriaDto>("/api/v1/criteria", {
        name: form.name,
        keywords: form.keywords.split(",").map((s) => s.trim()).filter(Boolean),
        location: form.location,
        contract_types: form.contract_types.split(",").map((s) => s.trim()).filter(Boolean),
        sources: form.sources.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      setForm(EMPTY_CRITERIA);
      queryClient.invalidateQueries({ queryKey: ["criteria"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const runSearch = useMutation({
    mutationFn: (criteriaId: number) =>
      api.post<{ new: number; duplicates: number }>("/api/v1/search/run", {
        criteria_id: criteriaId,
      }),
    onSuccess: (result) => {
      setMessage(`Search done: ${result.new} new, ${result.duplicates} duplicates.`);
      queryClient.invalidateQueries({ queryKey: ["offers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const flagOffer = useMutation({
    mutationFn: ({ id, ignored }: { id: number; ignored: boolean }) =>
      api.patch<OfferDto>(`/api/v1/offers/${id}`, { ignored }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["offers"] }),
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Search & Offers</h2>
      {message && <p className="text-sm text-neutral-700">{message}</p>}

      <div className="max-w-3xl rounded border border-neutral-200 bg-white p-4">
        <h3 className="font-semibold">New criteria</h3>
        <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
          <input
            className="rounded border border-neutral-300 px-2 py-1"
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="rounded border border-neutral-300 px-2 py-1"
            placeholder="Keywords (comma separated)"
            value={form.keywords}
            onChange={(e) => setForm({ ...form, keywords: e.target.value })}
          />
          <input
            className="rounded border border-neutral-300 px-2 py-1"
            placeholder="Location (city code)"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
          />
          <input
            className="rounded border border-neutral-300 px-2 py-1"
            placeholder="Contract types (CDD,CDP...)"
            value={form.contract_types}
            onChange={(e) => setForm({ ...form, contract_types: e.target.value })}
          />
        </div>
        <button
          className="mt-3 rounded bg-neutral-900 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={!form.name || createCriteria.isPending}
          onClick={() => createCriteria.mutate()}
        >
          Save criteria
        </button>
      </div>

      <div className="max-w-3xl rounded border border-neutral-200 bg-white p-4">
        <h3 className="font-semibold">Saved criteria</h3>
        <ul className="mt-2 space-y-2">
          {(criteria.data ?? []).map((c) => (
            <li key={c.id} className="flex items-center justify-between text-sm">
              <div>
                <span className="font-medium">{c.name}</span>{" "}
                <span className="text-neutral-500">
                  {c.keywords.join(", ")} — {c.location || "anywhere"}
                </span>
              </div>
              <button
                className="rounded border border-neutral-300 px-2 py-0.5 text-xs disabled:opacity-50"
                disabled={runSearch.isPending}
                onClick={() => runSearch.mutate(c.id)}
              >
                {runSearch.isPending ? "Running..." : "Run search"}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded border border-neutral-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Offers ({offers.data?.length ?? 0}), sorted by match score</h3>
          <button
            className="rounded border border-neutral-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={runMatching.isPending}
            onClick={() => runMatching.mutate()}
          >
            {runMatching.isPending ? "Matching..." : "Run matching (top 10)"}
          </button>
        </div>
        <ul className="mt-2 divide-y divide-neutral-100">
          {(offers.data ?? []).map((o) => (
            <li key={o.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <a className="font-medium text-blue-700 hover:underline" href={o.url} target="_blank" rel="noreferrer">
                  {o.title}
                </a>{" "}
                <span className="text-neutral-600">
                  — {o.company} · {o.location} · {o.contract_type || "?"} · via {o.source}
                </span>
                {o.match && (
                  <div className="text-xs text-neutral-500">
                    Score {o.match.score}/100 · {o.match.rationale}
                    {o.match.missing_skills.length > 0 && (
                      <span> · missing: {o.match.missing_skills.join(", ")}</span>
                    )}
                    {o.match.red_flags.length > 0 && (
                      <span className="text-red-600"> · red flags: {o.match.red_flags.join(", ")}</span>
                    )}
                  </div>
                )}
              </div>
              <button
                className="rounded border border-neutral-300 px-2 py-0.5 text-xs"
                onClick={() => flagOffer.mutate({ id: o.id, ignored: !o.ignored })}
              >
                {o.ignored ? "Unignore" : "Ignore"}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
