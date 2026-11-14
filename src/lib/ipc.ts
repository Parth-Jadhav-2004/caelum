import { contracts, matches } from "./contracts";
import { invoke } from "@tauri-apps/api/core";
import type { Config } from "./config.generated";
export type { Config };
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
  storage_error?: boolean;
  backend?: string;
  feedback?: Feedback;
}
export interface Dictation {
  id: string;
  created_at: string;
  final_transcript: string;
  duration_ms: number;
  word_count: number;
  refined: number;
  copied: number;
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
  credentials: Record<string, string>;
}
export interface Device {
  label: string;
  value: string | number | null;
}
export interface Ack {
  ok: boolean;
}
interface Methods {
  bootstrap: [Record<string, never>, Bootstrap];
  status: [Record<string, never>, Status];
  history: [{ query?: string }, Dictation[]];
  summary: [Record<string, never>, Summary];
  devices: [Record<string, never>, Device[]];
  "history.delete": [{ id?: string }, Ack];
  "history.export": [{ path: string }, Ack];
  "settings.save": [{ config: Config }, { saved: boolean; warning?: string }];
  "service.start": [Record<string, never>, Ack];
  "service.stop": [{ discard?: boolean }, Ack];
  control: [
    {
      action: "start" | "stop" | "cancel" | "retry" | "pause" | "resume";
      discard?: boolean;
    },
    Ack,
  ];
  "providers.check": [Record<string, never>, string];
  "credentials.store": [{ name: string; value: string }, string];
  "credentials.delete": [{ name: string }, Ack];
  "microphone.test": [Record<string, never>, Ack];
  practice: [{ consent: boolean }, { text: string; refined: boolean }];
  "sample.cancel": [Record<string, never>, Ack];
  "setup.validate": [
    { consent: boolean; keys?: Record<string, string> },
    { storage: Record<string, string> },
  ];
  "shortcut.check": [Record<string, never>, string];
  "setup.finish": [Record<string, never>, Ack];
  launcher: [{ autostart?: boolean; enabled?: boolean }, string];
  "updates.check": [Record<string, never>, { version: string } | null];
  "updates.stage": [Record<string, never>, string];
  "updates.apply": [Record<string, never>, boolean];
  "updates.discard": [Record<string, never>, Ack];
  "updates.pending": [Record<string, never>, boolean];
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
