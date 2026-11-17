import { has, t } from "./i18n";
// 허브 API 클라이언트. 상태 이름은 허브가 주는 값 그대로 써요(components.md 15).

export type VerdictKey = "gpu_ok" | "cpu_ok" | "cpu_slow" | "tight" | "no" | "unverified";
export type Verdict = { verdict: VerdictKey; reason: string; device: string | null; need_gb?: number; rtf_cpu?: number };
export type InstallStatus = "none" | "installing" | "paused" | "failed" | "installed" | "update" | "source_changed";
export type RunState = "stopped" | "loading" | "ready" | "idle" | "restarting" | "stalled" | "dead";
export type InstallStep = "env" | "code" | "packages" | "weights" | "selftest";

export type EngineEvent = { at: number; kind: "user" | "auto" | "error"; msg: string };
export type Engine = {
  id: string;
  name: string;
  recipe_version: number;
  role: string;
  summary?: string;
  maker?: string;
  homepage?: string;
  devices: { cpu?: string; nvidia?: string; mac?: string };
  measured: {
    at?: string;
    evidence?: "verified" | "measured" | "unverified";
    cer_ko?: number;
    hallu?: string;
    rtf_cpu?: number;
    rtf_gpu?: number;
    ram_gb?: number;
    gpu_mem_gb?: number;
    load_s?: number;
    sample_rate?: number;
  };
  license: {
    id: string;
    name: string;
    url: string;
    commercial?: "yes" | "conditional" | "noncommercial" | "unknown";
    summary: string[];
    has_text: boolean;
    restrictions_from?: string;
  };
  maintenance?: { status: "active" | "quiet" | "archived" | "unknown"; since?: string; note?: string; archive_url?: string };
  voices?: { id: string; name: string; name_en?: string; gender?: string; extra?: boolean }[];
  // 레시피의 사람 말 번역(언어 코드 → 칸). 없는 칸은 원문(한국어)을 써요.
  i18n?: Record<string, {
    summary?: string; good_for?: string[]; human_eval_line?: string; human_eval_by?: string;
    license_summary?: string[]; maintenance_note?: string; voices?: Record<string, string>; selftest?: string[];
  }>;
  default_voice?: string;
  tags?: Record<string, string>;
  max_chars?: number;
  human_eval?: { line: string; short?: string; by?: string };
  good_for?: string[];
  threads?: number;
  speed?: { default: number; min: number; max: number };
  download_bytes: number;
  runtime?: "native" | "wsl" | "none";
  has_code?: boolean;
  voices_from?: string;
  weights_sources: { repo: string; revision: string }[];
  this_pc: Verdict;
  install: {
    status: InstallStatus;
    done: InstallStep[];
    error: { kind: string; message: string; step?: string } | null;
    consent: { license: string; at: string } | null;
    selftest: { lines: { text: string; gen_s: number; audio_s: number }[]; rtf: number | null; load_s: number | null; at: string } | null;
    installed_at?: string;
    progress: { step: InstallStep | null; bytes_done: number; bytes_total: number } | null;
  };
  disk_bytes: number;
  run: {
    state: RunState;
    error: { kind: string; message: string; retry_at?: number; attempt?: number; log?: string } | null;
    pid: number | null;
    loaded_s: number | null;
    restarts: number;
    crashes_10min: number;
    rss_bytes: number | null;
    threads?: number;
    events: EngineEvent[];
  };
};

export type Hardware = {
  os: string;
  os_name: string;
  platform: string;
  arch: string;
  cpu: string;
  cores: number;
  ram_gb: number | null;
  gpus: { name: string; vram_gb: number; driver: string }[];
  apple_silicon: boolean;
  models_dir: string;
  disk_free_gb: number;
};

export type Settings = {
  theme: "system" | "light" | "dark";
  language: "system" | "ko" | "en";
  font_scale: number;
  wizard_done: boolean;
  api_enabled: boolean;
  last_screen?: string;
  models_dir: string;
  version: string;
};

export type Plan = {
  engine: string;
  steps: InstallStep[];
  download_bytes: number;
  weights_bytes: number;
  env_bytes_estimate: number;
  need_bytes: number;
  free_bytes: number;
  disk_ok: boolean;
  sources: string[];
  target: string;
  est_minutes: number;
};

export type WslState = { state: "not_windows" | "none" | "needs_setup" | "no_distro" | "ready"; virtualization_off?: boolean; detail?: string };
export type Recommend = { use: string; recommended: string | null; alternatives: string[]; not_here: string[]; coming_later: string[] };
export type Drive = { root: string; label: string; total_bytes: number; free_bytes: number; suggested: string };
export type ApiInfo = {
  enabled: boolean;
  base_url: string;
  token: string | null;
  calls: { at: number; method: string; path: string; status: number; ms?: number; reason?: string }[];
};

declare global {
  interface Window {
    sori?: {
      desktop: boolean;
      token: string;
      platform: string;
      openExternal?: (url: string) => void;
      openPath?: (p: string) => void;
      installWsl?: () => Promise<{ ok: boolean; code: number; out: string }>;
    };
  }
}

export class ApiError extends Error {
  constructor(public status: number, public kind: string, message: string) {
    super(message);
  }
}

/** 화면에 보일 오류 문장 - 허브가 준 kind 로 언어 표에서 골라요(허브 문장은 한국어라 로그용). */
export function errorText(x: unknown): string {
  if (x instanceof ApiError) {
    const k = `errors.${x.kind}`;
    return has(k) ? t(k) : t("errors.unknown");
  }
  return t("errors.unknown");
}

const TOKEN_KEY = "sori-hub-token";
export function getToken(): string {
  return window.sori?.token || localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t);
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${getToken()}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers, body });
  } catch {
    throw new ApiError(0, "network", t("errors.network"));
  }
  if (!res.ok) {
    let kind = "unknown";
    let message = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      const d = j.detail ?? j.error ?? j;
      kind = d.kind ?? kind;
      message = d.message ?? message;
    } catch {
      /* 본문 없음 */
    }
    throw new ApiError(res.status, kind, message);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as T;
}

export async function speech(model: string, input: string, voice?: string, seed = 0, speed?: number) {
  const headers = { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" };
  let res: Response;
  try {
    res = await fetch("/v1/audio/speech", { method: "POST", headers, body: JSON.stringify({ model, input, voice, seed, ...(speed ? { speed } : {}) }) });
  } catch {
    throw new ApiError(0, "network", t("errors.network"));
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    const d = j.detail ?? {};
    throw new ApiError(res.status, d.kind ?? "unknown", d.message ?? `HTTP ${res.status}`);
  }
  return {
    blob: await res.blob(),
    genS: Number(res.headers.get("x-sori-gen-seconds") || 0),
    audioS: Number(res.headers.get("x-sori-audio-seconds") || 0),
    retries: Number(res.headers.get("x-sori-retries") || 0),
    suspect: res.headers.get("x-sori-suspect") || "",
  };
}

export function openExternal(url: string) {
  if (window.sori?.openExternal) window.sori.openExternal(url);
  else window.open(url, "_blank", "noopener");
}
