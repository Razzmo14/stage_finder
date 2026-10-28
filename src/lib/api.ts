/** Authenticated access to the sidecar backend.
 *
 * The backend URL and the per-launch session token come from the Tauri
 * core via invoke(); the token lives in memory only.
 */

import { invoke } from "@tauri-apps/api/core";

let backendUrl: string | null = null;
let sessionToken: string | null = null;

async function ensureConnection(): Promise<void> {
  if (backendUrl === null || sessionToken === null) {
    backendUrl = await invoke<string>("get_backend_url");
    sessionToken = await invoke<string>("get_session_token");
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  await ensureConnection();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${sessionToken}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${backendUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export interface LlmSettings {
  provider: string;
  api_key_masked: string | null;
  data_collection: string;
}

export interface ModelInfoDto {
  id: string;
  name: string;
  context_length: number | null;
  supported_parameters: string[];
  supports_structured_output: boolean;
  pricing: Record<string, string>;
}

export interface LlmTestResult {
  reply: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost: number;
}
