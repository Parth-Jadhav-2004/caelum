import { contracts, matches } from "./contracts";
import { invoke } from "@tauri-apps/api/core";
import type { Config } from "./config.generated";
export type { Config };
export type ConfigPatch = {
  [Section in keyof Config]?: Partial<Config[Section]>;
};
export interface Feedback {
  state: string;
  elapsed_ms: number;
  history: number[];
  level: number;
}
export interface Status {
  running: boolean;
  state: string;
  title: string;
  detail: string;
  paused: boolean;
  pending_audio?: boolean;
  can_copy?: boolean;
  storage_error?: boolean;
  backend?: string;
  hotkey?: string;
  shortcut_mode?: string;
  shortcut_description?: string;
  feedback?: Feedback;
  engine?: {
    kind: "online" | "local";
    model: string | null;
    state: "ready" | "loading" | "error" | "missing" | "unloaded";
    message: string;
  };
}
export interface Dictation {
  id: string;
  created_at: string;
  final_transcript: string;
  duration_ms: number;
  word_count: number;
  refined: number;
  copied: number;
  engine?: "online" | "local";
  language?: string;
  stt_model?: string;
}
export interface Summary {
  total_words: number;
  today_words: number;
  month_words: number;
  wpm: number;
  duration_ms: number;
  daily: Record<string, number>;
  activity: Record<string, number>;
}
export interface Bootstrap {
  version: number;
  config: Config;
  privacy: string;
  setup: { stage: number; complete: boolean };
  autostart: boolean;
  credentials: Record<
    string,
    string | { description: string; storage: string }
  >;
}
export interface Device {
  label: string;
  value: string | number | null;
}
export interface Ack {
  ok: boolean;
}
export interface ShortcutCheck {
  state: "available" | "pending" | "manual";
  message: string;
}
export interface ModelProgress {
  id: string;
  state:
    | "queued"
    | "downloading"
    | "stalled"
    | "paused"
    | "verifying"
    | "installing"
    | "ready"
    | "failed"
    | "cancelled";
  received_bytes: number;
  total_bytes: number;
  bytes_per_sec: number;
  eta_seconds: number | null;
  error: { code: string; message: string } | null;
}
export interface SpeechModel extends Omit<ModelProgress, "state"> {
  state: ModelProgress["state"] | "not_installed" | "installed";
  tier: string;
  label: string;
  blurb: string;
  languages: string[];
  auto_language: boolean;
  download_bytes: number;
  disk_bytes: number;
  licence: { id: string; url: string; attribution: string };
  wer: { open_asr_v1_1?: number; open_asr_latest?: number };
  in_use: boolean;
  visible: boolean;
  disabled_reason: string | null;
  requires_extra: string | null;
  stored_in: string;
  decode_ms: number | null;
  runtime_state?:
    "ready" | "loading" | "error" | "missing" | "unloaded" | "failed";
  runtime_message?: string;
  reference_wait_ms?: number;
}
export interface ModelList {
  hardware: {
    mem_total_mb: number;
    mem_available_mb: number;
    cores: number;
    arch: string;
    avx2: boolean;
    avx512: boolean;
    disk_free_mb: number;
    nvidia: boolean;
    language: string;
  };
  recommended: { id: string | null; reason_code: string; reason_text: string };
  models: SpeechModel[];
  pending_use: string | null;
  storage_bytes: number;
}
interface Methods {
  "models.list": [{ language?: string }, ModelList];
  "models.download": [{ id: string }, Ack];
  "models.pause": [{ id: string }, Ack];
  "models.resume": [{ id: string }, Ack];
  "models.cancel": [{ id: string }, Ack];
  "models.remove": [{ id: string }, { freed_bytes: number }];
  "models.verify": [{ id: string }, { ok: boolean; bad_files: string[] }];
  "models.use": [{ id: string; when_ready?: boolean }, { saved: boolean }];
  bootstrap: [Record<string, never>, Bootstrap];
  status: [Record<string, never>, Status];
  history: [{ query?: string }, Dictation[]];
  summary: [Record<string, never>, Summary];
  devices: [Record<string, never>, Device[]];
  "history.delete": [{ id?: string }, Ack];
  "history.export": [{ path: string }, Ack];
  "settings.save": [
    { config: ConfigPatch },
    { saved: boolean; warning?: string },
  ];
  "service.start": [Record<string, never>, Ack];
  "service.stop": [{ discard?: boolean }, Ack];
  control: [
    {
      action: "start" | "stop" | "cancel" | "retry" | "pause" | "resume" | "copy";
      discard?: boolean;
    },
    Ack,
  ];
  "providers.check": [Record<string, never>, string];
  "credentials.store": [{ name: string; value: string }, string];
  "credentials.delete": [{ name: string }, Ack];
  "microphone.test": [Record<string, never>, Ack];
  practice: [
    { consent: boolean; interactive?: boolean; insert?: boolean },
    { text: string; refined: boolean; inserted?: boolean },
  ];
  "sample.cancel": [{ finish?: boolean }, Ack];
  "setup.validate": [
    { consent: boolean; keys?: Record<string, string> },
    { storage: Record<string, string> },
  ];
  "shortcut.check": [{ accept_manual?: boolean }, ShortcutCheck];
  "setup.finish": [{ skip_practice?: boolean }, Ack];
  "setup.stage": [{ stage: number }, Ack];
  "setup.skip": [Record<string, never>, Ack];
  launcher: [{ autostart?: boolean; enabled?: boolean }, string];
  "updates.check": [Record<string, never>, { version: string } | null];
  "updates.testing": [
    Record<string, never>,
    { version: string; installed: boolean } | null,
  ];
  "updates.stage": [Record<string, never>, string];
  "updates.apply": [
    Record<string, never>,
    "installed" | "installer_launched" | "no_update",
  ];
  "updates.discard": [Record<string, never>, Ack];
  "updates.pending": [
    Record<string, never>,
    null | { state: "unverified"; version: null } | { state: "queued" | "installed"; version: string },
  ];
}
export async function ipc<M extends keyof Methods>(
  method: M,
  params: Methods[M][0],
): Promise<Methods[M][1]> {
  const schema = contracts[method];
  if (!schema || !matches(schema.params, params)) {
    throw new IpcError("invalid_request", "Invalid desktop request", false);
  }
  let result: unknown;
  try {
    result = await invoke("backend", { method, params });
  } catch (error) {
    throw ipcError(error);
  }
  if (!matches(schema.result, result)) {
    throw new IpcError(
      "protocol",
      "Invalid engine response. Restart Caelum.",
      false,
    );
  }
  return result as Methods[M][1];
}
export class IpcError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly retryable: boolean,
  ) {
    super(message);
    this.name = "IpcError";
  }
}
export function ipcError(error: unknown): IpcError {
  if (error instanceof IpcError) return error;
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string" &&
    "retryable" in error &&
    typeof error.retryable === "boolean"
  ) {
    return new IpcError(error.code, error.message, error.retryable);
  }
  return new IpcError(
    "internal",
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Operation failed",
    false,
  );
}
export const errorText = (error: unknown) => ipcError(error).message;
