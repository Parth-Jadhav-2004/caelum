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
interface Methods {
  bootstrap: [Record<string, never>, Bootstrap];
  status: [Record<string, never>, Status];
  history: [{ query?: string }, Dictation[]];
  summary: [Record<string, never>, Summary];
  devices: [Record<string, never>, Device[]];
  "history.delete": [{ id?: string }, unknown];
  "history.export": [{ path: string }, unknown];
  "settings.save": [{ config: Config }, { saved: boolean; warning?: string }];
  "service.start": [Record<string, never>, unknown];
  "service.stop": [{ discard?: boolean }, unknown];
  control: [
    {
      action: "start" | "stop" | "cancel" | "retry" | "pause" | "resume";
      discard?: boolean;
    },
    unknown,
  ];
  "providers.check": [Record<string, never>, string];
  "credentials.store": [{ name: string; value: string }, string];
  "credentials.delete": [{ name: string }, unknown];
  "microphone.test": [Record<string, never>, unknown];
  practice: [{ consent: boolean }, { text: string; refined: boolean }];
  "sample.cancel": [Record<string, never>, unknown];
  "setup.validate": [
    { consent: boolean; keys?: Record<string, string> },
    { storage: Record<string, string> },
  ];
  "shortcut.check": [Record<string, never>, string];
  "setup.finish": [Record<string, never>, unknown];
  launcher: [{ autostart?: boolean; enabled?: boolean }, string];
  "updates.check": [Record<string, never>, { version: string } | null];
  "updates.stage": [Record<string, never>, string];
  "updates.apply": [Record<string, never>, boolean];
  "updates.discard": [Record<string, never>, unknown];
  "updates.pending": [Record<string, never>, boolean];
}
export function ipc<M extends keyof Methods>(
  method: M,
  params: Methods[M][0],
): Promise<Methods[M][1]> {
  return invoke("backend", { method, params });
}
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
