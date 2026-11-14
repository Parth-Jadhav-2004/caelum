import { create } from "zustand";
import type { Status } from "@/lib/ipc";
export type Page = "home" | "statistics" | "history" | "settings" | "setup";
interface AppState {
  page: Page;
  status: Status | null;
  engineError: string | null;
  setEngineError: (message: string | null) => void;
  navigate: (page: Page) => void;
  setStatus: (status: Status | null) => void;
}
export const useApp = create<AppState>((set) => ({
  page: "home",
  status: null,
  engineError: null,
  setEngineError: (engineError) => set({ engineError }),
  navigate: (page) => set({ page }),
  setStatus: (status) => set({ status }),
}));
