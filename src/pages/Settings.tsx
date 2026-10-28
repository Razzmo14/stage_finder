import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type LlmSettings,
  type LlmTestResult,
  type ModelInfoDto,
} from "../lib/api";

function LlmSection() {
  const queryClient = useQueryClient();
  const [keyInput, setKeyInput] = useState("");
  const [search, setSearch] = useState("");
  const [testModel, setTestModel] = useState("");
  const [testResult, setTestResult] = useState<LlmTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const settings = useQuery<LlmSettings>({
    queryKey: ["llm-settings"],
    queryFn: () => api.get<LlmSettings>("/api/v1/settings/llm"),
  });

  const models = useQuery<ModelInfoDto[]>({
    queryKey: ["models"],
    queryFn: () => api.get<ModelInfoDto[]>("/api/v1/models"),
  });

  const saveKey = useMutation({
    mutationFn: (apiKey: string) =>
      api.put<LlmSettings>("/api/v1/settings/llm/key", { api_key: apiKey }),
    onSuccess: () => {
      setKeyInput("");
      queryClient.invalidateQueries({ queryKey: ["llm-settings"] });
    },
  });

  const deleteKey = useMutation({
    mutationFn: () => api.del<void>("/api/v1/settings/llm/key"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["llm-settings"] }),
  });

  const runTest = useMutation({
    mutationFn: (model: string) =>
      api.post<LlmTestResult>("/api/v1/settings/llm/test", { model }),
    onSuccess: (result) => {
      setTestResult(result);
      setTestError(null);
    },
    onError: (error: Error) => {
      setTestError(error.message);
      setTestResult(null);
    },
  });

  const filtered = (models.data ?? []).filter((m) =>
    `${m.id} ${m.name}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <section className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="font-semibold">LLM (OpenRouter)</h3>

      <div className="mt-3 flex items-center gap-2">
        <span className="text-sm text-neutral-600">
          API key: {settings.data?.api_key_masked ?? "not configured"}
        </span>
        <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
          keychain only
        </span>
      </div>
      <div className="mt-2 flex gap-2">
        <input
          type="password"
          className="w-80 rounded border border-neutral-300 px-2 py-1 text-sm"
          placeholder="sk-or-v1-..."
          value={keyInput}
          onChange={(e) => setKeyInput(e.target.value)}
        />
        <button
          className="rounded bg-neutral-900 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={keyInput.length < 8 || saveKey.isPending}
          onClick={() => saveKey.mutate(keyInput)}
        >
          Save key
        </button>
        <button
          className="rounded border border-neutral-300 px-3 py-1 text-sm"
          disabled={!settings.data?.api_key_masked || deleteKey.isPending}
          onClick={() => deleteKey.mutate()}
        >
          Remove
        </button>
      </div>
      {saveKey.isError && <p className="mt-1 text-sm text-red-600">{saveKey.error.message}</p>}

      <h4 className="mt-6 font-medium">Model catalog</h4>
      {models.isError && <p className="text-sm text-red-600">{models.error.message}</p>}
      <input
        className="mt-2 w-72 rounded border border-neutral-300 px-2 py-1 text-sm"
        placeholder="Search models..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <button
        className="ml-2 rounded border border-neutral-300 px-2 py-1 text-sm"
        onClick={() => models.refetch()}
      >
        Refresh
      </button>
      <div className="mt-2 max-h-72 overflow-y-auto rounded border border-neutral-200">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-2 py-1">Model</th>
              <th className="px-2 py-1">Context</th>
              <th className="px-2 py-1">Structured</th>
              <th className="px-2 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.id} className="border-t border-neutral-100">
                <td className="px-2 py-1">
                  <div>{m.name}</div>
                  <div className="text-xs text-neutral-500">{m.id}</div>
                </td>
                <td className="px-2 py-1">{m.context_length ?? "?"}</td>
                <td className="px-2 py-1">{m.supports_structured_output ? "yes" : "fallback"}</td>
                <td className="px-2 py-1">
                  <button
                    className="rounded border border-neutral-300 px-2 py-0.5 text-xs"
                    onClick={() => {
                      setTestModel(m.id);
                      runTest.mutate(m.id);
                    }}
                  >
                    Test
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {runTest.isPending && testModel && <p className="mt-2 text-sm">Testing {testModel}...</p>}
      {testResult && (
        <p className="mt-2 text-sm">
          {testResult.reply} — {testResult.prompt_tokens}+{testResult.completion_tokens} tokens,
          cost {testResult.cost}
        </p>
      )}
      {testError && <p className="mt-2 text-sm text-red-600">{testError}</p>}
    </section>
  );
}

export default function Settings() {
  return (
    <div className="max-w-3xl space-y-6">
      <h2 className="text-xl font-semibold">Settings</h2>
      <LlmSection />
      <p className="text-sm text-neutral-500">
        Email accounts, send limits, data export and language settings arrive with
        their features.
      </p>
    </div>
  );
}
