import { create } from "zustand";
import type { Status } from "@/lib/ipc";
export type Page = "home" | "statistics" | "history" | "settings" | "setup";
interface AppState {
  page: Page;
  status: Status | null;
  navigate: (page: Page) => void;
  setStatus: (status: Status | null) => void;
}
export const useApp = create<AppState>((set) => ({
  page: "home",
  status: null,
  navigate: (page) => set({ page }),
  setStatus: (status) => set({ status }),
}));
