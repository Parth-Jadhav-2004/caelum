import { create } from "zustand";
import type { ModelProgress } from "@/lib/ipc";

export const useDownloads = create<{
  progress: Record<string, ModelProgress>;
  announcement: string;
  update: (event: ModelProgress, label?: string) => void;
}>((set, get) => ({
  progress: {},
  announcement: "",
  update: (event, label) => {
    const previous = get().progress[event.id];
    const changed = previous?.state !== event.state;
    const messages: Partial<Record<ModelProgress["state"], string>> = {
      queued: "Download queued",
      downloading: "Download started",
      paused: "Download paused",
      stalled: "Download stalled. Waiting for the connection.",
      ready: `${label ?? "Speech model"} is ready`,
      verifying: "Verifying downloaded files",
      installing: "Installing speech model",
      cancelled: "Download cancelled",
      failed: event.error?.message ?? "Download failed",
    };
    set({
      progress: { ...get().progress, [event.id]: event },
      ...(changed && messages[event.state]
        ? { announcement: messages[event.state] }
        : {}),
    });
  },
}));
