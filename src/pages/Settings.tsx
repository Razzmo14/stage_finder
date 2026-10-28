import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  api,
  type LlmSettings,
  type LlmTestResult,
  type ModelInfoDto,
} from "../lib/api";

interface MailStatusDto {
  gmail_connected: boolean;
  graph_connected: boolean;
  smtp_connected: boolean;
  account: string;
  allow_direct_send: boolean;
  daily_send_limit: number;
  sends_today: number;
  sender_email: string;
}

function MailSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [account, setAccount] = useState("gmail");
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
        account,
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
      setMessage(t("settings.openUrl"));
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
      <h3 className="font-semibold">{t("settings.mailTitle")}</h3>
      <p className="mt-2 text-sm">
        {t("settings.mailStatus", {
          status: s?.gmail_connected ? t("settings.connected") : t("settings.notConnected"),
          count: s?.sends_today ?? 0,
        })}
      </p>
      {!s?.gmail_connected ? (
        <div className="mt-2 space-y-2">
          <button
            className="rounded bg-neutral-900 px-3 py-1 text-sm text-white"
            onClick={() => startConnect.mutate()}
          >
            {t("settings.connectGmail")}
          </button>
          {authorizeUrl && (
            <>
              <a className="block break-all text-sm text-blue-700 underline" href={authorizeUrl} target="_blank" rel="noreferrer">
                {authorizeUrl}
              </a>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
                  placeholder={t("settings.pasteCode")}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-sm disabled:opacity-50"
                  disabled={!code || completeConnect.isPending}
                  onClick={() => completeConnect.mutate()}
                >
                  {t("settings.complete")}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      <h4 className="mt-4 font-medium">{t("settings.deliverySettings")}</h4>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span>{t("settings.activeAccount")}</span>
        {(["gmail", "graph", "smtp"] as const).map((name) => (
          <label key={name} className="flex items-center gap-1">
            <input
              type="radio"
              checked={account === name}
              onChange={() => setAccount(name)}
            />
            {name}
          </label>
        ))}
      </div>
      <p className="mt-1 text-xs text-neutral-500">
        Outlook and generic SMTP/IMAP accounts are configured through the
        keychain (see README); connect Gmail above or select the account
        your administrator configured.
      </p>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={allowSend}
          onChange={(e) => setAllowSend(e.target.checked)}
        />
        {t("settings.allowDirectSend")}
      </label>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span>{t("settings.dailyLimit")}</span>
        <input
          type="number"
          className="w-20 rounded border border-neutral-300 px-2 py-1"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value) || 1)}
        />
        <span>{t("settings.senderEmail")}</span>
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

interface SchedulerSettingsDto {
  enabled: boolean;
  search_interval_minutes: number;
  follow_up_check_minutes: number;
}

function SchedulerSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [interval, setIntervalMinutes] = useState(240);
  const [message, setMessage] = useState<string | null>(null);

  const settings = useQuery<SchedulerSettingsDto>({
    queryKey: ["scheduler-settings"],
    queryFn: () => api.get<SchedulerSettingsDto>("/api/v1/settings/scheduler"),
  });

  const save = useMutation({
    mutationFn: () =>
      api.put<SchedulerSettingsDto>("/api/v1/settings/scheduler", {
        enabled,
        search_interval_minutes: interval,
        follow_up_check_minutes: settings.data?.follow_up_check_minutes ?? 15,
      }),
    onSuccess: () => {
      setMessage("Scheduler settings saved.");
      queryClient.invalidateQueries({ queryKey: ["scheduler-settings"] });
    },
  });

  const runNow = useMutation({
    mutationFn: () =>
      api.post<{ criteria: number; new: number; duplicates: number }>(
        "/api/v1/scheduler/run-searches",
        {}
      ),
    onSuccess: (stats) =>
      setMessage(`Run finished: ${stats.criteria} criteria, ${stats.new} new offers.`),
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <section className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="font-semibold">{t("settings.schedulerTitle")}</h3>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        {t("settings.runPeriodically")}
      </label>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span>{t("settings.every")}</span>
        <input
          type="number"
          className="w-24 rounded border border-neutral-300 px-2 py-1"
          value={interval}
          onChange={(e) => setIntervalMinutes(Number(e.target.value) || 60)}
        />
        <span>{t("settings.minutes")}</span>
      </div>
      <p className="mt-2 text-xs text-neutral-500">
        {t("settings.schedulerHardRule")}
      </p>
      <div className="mt-2 flex gap-2">
        <button
          className="rounded border border-neutral-300 px-3 py-1 text-sm disabled:opacity-50"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </button>
        <button
          className="rounded border border-neutral-300 px-3 py-1 text-sm disabled:opacity-50"
          disabled={runNow.isPending}
          onClick={() => runNow.mutate()}
        >
          {t("settings.runNow")}
        </button>
      </div>
      {message && <p className="mt-2 text-sm text-neutral-600">{message}</p>}
    </section>
  );
}

interface LlmConfigDto {
  active_provider: string;
  monthly_budget_usd: number | null;
  ollama_base_url: string;
}

function LlmConfigSection() {
  const { t } = useTranslation();
  const [provider, setProvider] = useState("openrouter");
  const [budget, setBudget] = useState<number | null>(null);
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [message, setMessage] = useState<string | null>(null);

  const budgetStatus = useQuery<{ spent_usd: number; monthly_budget_usd: number | null }>({
    queryKey: ["budget"],
    queryFn: () => api.get<{ spent_usd: number; monthly_budget_usd: number | null }>("/api/v1/budget"),
  });

  const save = useMutation({
    mutationFn: () =>
      api.put<LlmConfigDto>("/api/v1/settings/llm-config", {
        active_provider: provider,
        monthly_budget_usd: budget,
        ollama_base_url: ollamaUrl,
      }),
    onSuccess: () => setMessage("LLM provider settings saved."),
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <section className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="font-semibold">{t("settings.llmProviderTitle")}</h3>
      <div className="mt-2 flex items-center gap-3 text-sm">
        <span>{t("settings.provider")}</span>
        {(["openrouter", "anthropic", "openai", "ollama"] as const).map((name) => (
          <label key={name} className="flex items-center gap-1">
            <input type="radio" checked={provider === name} onChange={() => setProvider(name)} />
            {name}
            {name === "ollama" && <span className="text-xs text-neutral-400">{t("settings.localOnly")}</span>}
          </label>
        ))}
      </div>
      {provider === "ollama" && (
        <input
          className="mt-2 w-72 rounded border border-neutral-300 px-2 py-1 text-sm"
          value={ollamaUrl}
          onChange={(e) => setOllamaUrl(e.target.value)}
          placeholder={t("settings.ollamaUrl")}
        />
      )}
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span>{t("settings.budget")}:</span>
        <input
          type="number"
          className="w-24 rounded border border-neutral-300 px-2 py-1"
          value={budget ?? ""}
          onChange={(e) => setBudget(e.target.value === "" ? null : Number(e.target.value))}
        />
        {budgetStatus.data && (
          <span className="text-xs text-neutral-500">
            {t("settings.spentThisMonth", { amount: budgetStatus.data.spent_usd })}
          </span>
        )}
      </div>
      <button
        className="mt-2 rounded border border-neutral-300 px-3 py-1 text-sm disabled:opacity-50"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {t("common.save")}
      </button>
      {message && <p className="mt-2 text-sm text-neutral-600">{message}</p>}
    </section>
  );
}

function LlmSection() {
  const { t } = useTranslation();
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
      <h3 className="font-semibold">{t("settings.llmTitle")}</h3>

      <div className="mt-3 flex items-center gap-2">
        <span className="text-sm text-neutral-600">
          {t("settings.apiKey")}: {settings.data?.api_key_masked ?? t("settings.notConfigured")}
        </span>
        <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
          {t("settings.keychainOnly")}
        </span>
      </div>
      <div className="mt-2 flex gap-2">
        <input
          type="password"
          className="w-80 rounded border border-neutral-300 px-2 py-1 text-sm"
          placeholder={t("settings.apiKeyPlaceholder")}
          value={keyInput}
          onChange={(e) => setKeyInput(e.target.value)}
        />
        <button
          className="rounded bg-neutral-900 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={keyInput.length < 8 || saveKey.isPending}
          onClick={() => saveKey.mutate(keyInput)}
        >
          {t("settings.saveKey")}
        </button>
        <button
          className="rounded border border-neutral-300 px-3 py-1 text-sm"
          disabled={!settings.data?.api_key_masked || deleteKey.isPending}
          onClick={() => deleteKey.mutate()}
        >
          {t("settings.remove")}
        </button>
      </div>
      {saveKey.isError && <p className="mt-1 text-sm text-red-600">{saveKey.error.message}</p>}

      <h4 className="mt-6 font-medium">{t("settings.modelCatalog")}</h4>
      {models.isError && <p className="text-sm text-red-600">{models.error.message}</p>}
      <input
        className="mt-2 w-72 rounded border border-neutral-300 px-2 py-1 text-sm"
        placeholder={t("settings.searchModels")}
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
              <th className="px-2 py-1">{t("settings.model")}</th>
              <th className="px-2 py-1">{t("settings.context")}</th>
              <th className="px-2 py-1">{t("settings.structured")}</th>
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
                <td className="px-2 py-1">{m.supports_structured_output ? t("settings.yes") : t("settings.fallback")}</td>
                <td className="px-2 py-1">
                  <button
                    className="rounded border border-neutral-300 px-2 py-0.5 text-xs"
                    onClick={() => {
                      setTestModel(m.id);
                      runTest.mutate(m.id);
                    }}
                  >
                    {t("settings.test")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {runTest.isPending && testModel && <p className="mt-2 text-sm">{t("settings.testing", { model: testModel })}</p>}
      {testResult && (
        <p className="mt-2 text-sm">
          {t("settings.testResult", {
            reply: testResult.reply,
            prompt: testResult.prompt_tokens,
            completion: testResult.completion_tokens,
            cost: testResult.cost,
          })}
        </p>
      )}
      {testError && <p className="mt-2 text-sm text-red-600">{testError}</p>}
    </section>
  );
}

export default function Settings() {
  const { t } = useTranslation();
  return (
    <div className="max-w-3xl space-y-6">
      <h2 className="text-xl font-semibold">{t("settings.title")}</h2>
      <LlmConfigSection />
      <LlmSection />
      <MailSection />
      <SchedulerSection />
      <p className="text-sm text-neutral-500">
        Data export and language settings arrive with their features.
      </p>
    </div>
  );
}
