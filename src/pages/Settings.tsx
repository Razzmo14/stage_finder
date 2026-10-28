import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type LlmSettings,
  type LlmTestResult,
  type ModelInfoDto,
} from "../lib/api";

interface MailStatusDto {
  gmail_connected: boolean;
  allow_direct_send: boolean;
  daily_send_limit: number;
  sends_today: number;
  sender_email: string;
}

function MailSection() {
  const queryClient = useQueryClient();
  const [allowSend, setAllowSend] = useState(false);
  const [limit, setLimit] = useState(20);
  const [sender, setSender] = useState("");
  const [authorizeUrl, setAuthorizeUrl] = useState<string | null>(null);
  const [oauthState, setOauthState] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const status = useQuery<MailStatusDto>({
    queryKey: ["mail-status"],
    queryFn: () => api.get<MailStatusDto>("/api/v1/mail/status"),
  });

  const saveSettings = useMutation({
    mutationFn: () =>
      api.put<MailStatusDto>("/api/v1/mail/settings", {
        allow_direct_send: allowSend,
        daily_send_limit: limit,
        sender_email: sender,
      }),
    onSuccess: (data) => {
      setMessage("Mail settings saved.");
      queryClient.invalidateQueries({ queryKey: ["mail-status"] });
      void data;
    },
  });

  const startConnect = useMutation({
    mutationFn: () => api.post<{ authorize_url: string; state: string }>("/api/v1/mail/gmail/connect/start", {}),
    onSuccess: (data) => {
      setAuthorizeUrl(data.authorize_url);
      setOauthState(data.state);
      setMessage("Open the URL, authorize, then paste the code here.");
    },
  });

  const completeConnect = useMutation({
    mutationFn: () =>
      api.post<{ email_address: string }>("/api/v1/mail/gmail/connect/complete", {
        code,
        state: oauthState,
      }),
    onSuccess: () => {
      setMessage("Gmail connected.");
      setCode("");
      setAuthorizeUrl(null);
      queryClient.invalidateQueries({ queryKey: ["mail-status"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const s = status.data;
  return (
    <section className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="font-semibold">Email (Gmail)</h3>
      <p className="mt-2 text-sm">
        Status: {s?.gmail_connected ? "connected" : "not connected"} · sends today: {s?.sends_today ?? 0}
      </p>
      {!s?.gmail_connected ? (
        <div className="mt-2 space-y-2">
          <button
            className="rounded bg-neutral-900 px-3 py-1 text-sm text-white"
            onClick={() => startConnect.mutate()}
          >
            Connect Gmail (OAuth2)
          </button>
          {authorizeUrl && (
            <>
              <a className="block break-all text-sm text-blue-700 underline" href={authorizeUrl} target="_blank" rel="noreferrer">
                {authorizeUrl}
              </a>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
                  placeholder="Paste the authorization code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-sm disabled:opacity-50"
                  disabled={!code || completeConnect.isPending}
                  onClick={() => completeConnect.mutate()}
                >
                  Complete
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      <h4 className="mt-4 font-medium">Delivery settings</h4>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={allowSend}
          onChange={(e) => setAllowSend(e.target.checked)}
        />
        Allow direct sending (opt-in; default is creating a draft)
      </label>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span>Daily send limit:</span>
        <input
          type="number"
          className="w-20 rounded border border-neutral-300 px-2 py-1"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value) || 1)}
        />
        <span>Sender email:</span>
        <input
          className="w-56 rounded border border-neutral-300 px-2 py-1"
          value={sender}
          onChange={(e) => setSender(e.target.value)}
        />
      </div>
      <button
        className="mt-2 rounded border border-neutral-300 px-3 py-1 text-sm disabled:opacity-50"
        disabled={saveSettings.isPending}
        onClick={() => saveSettings.mutate()}
      >
        Save mail settings
      </button>
      {message && <p className="mt-2 text-sm text-neutral-600">{message}</p>}
    </section>
  );
}

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
      <MailSection />
      <p className="text-sm text-neutral-500">
        Data export and language settings arrive with their features.
      </p>
    </div>
  );
}
