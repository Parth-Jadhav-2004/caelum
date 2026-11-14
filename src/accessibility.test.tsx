import { render, screen, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import App from "./App";
import { ipc } from "@/lib/ipc";
import { useApp, type Page } from "@/stores/app";
import { testConfig } from "./test-config";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => undefined),
}));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
const status = {
  running: true,
  paused: false,
  state: "hidden",
  title: "Ready",
  detail: "Hold your shortcut",
  backend: "portable",
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  useApp.setState({ page: "home", status, engineError: null });
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        version: 1,
        config: testConfig,
        privacy: "Only test audio is sent to your provider.",
        setup: { complete: true, stage: 4 },
        credentials: {},
        autostart: false,
      };
    if (method === "status") return status;
    if (method === "history" || method === "devices") return [];
    if (method === "summary")
      return {
        total_words: 0,
        today_words: 0,
        month_words: 0,
        wpm: 0,
        duration_ms: 0,
        daily: {},
        activity: {},
      };
    return { ok: true };
  }) as typeof ipc);
});
afterEach(() => vi.restoreAllMocks());
it.each<[Page, string]>([
  ["home", "Dictation"],
  ["statistics", "Statistics"],
  ["history", "History"],
  ["settings", "Settings"],
  ["setup", "Set up your provider"],
])(
  "has no detectable semantic accessibility violations on %s",
  async (page, heading) => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { name: "Dictation" });
    act(() => useApp.setState({ page }));
    await screen.findByRole("heading", { name: heading });
    const result = await axe.run(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(
      result.violations.map(({ id, nodes }) => ({
        id,
        targets: nodes.map((node) => node.target),
      })),
    ).toEqual([]);
  },
);
