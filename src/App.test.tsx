import { render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, it, expect, beforeEach } from "vitest";
import App from "./App";
import { invoke } from "@tauri-apps/api/core";
import { ipc, type Config } from "@/lib/ipc";
import { useApp } from "@/stores/app";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => undefined),
}));
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));
const config = {
  app: {
    hotkey: "SUPER + ALT + V",
    microphone: null,
    recording_mode: "hold",
    reduced_motion: true,
  },
  stt: { key_env: "GROQ_API_KEY", base_url: "https://api.groq.com/openai/v1" },
  cleanup: {
    model: "",
    base_url: "https://api.groq.com/openai/v1",
    key_env: "GROQ_API_KEY",
  },
  desktop: { theme: "dark", sidebar_visible: true, check_updates: false },
} as Config;
beforeEach(() => {
  useApp.setState({
    page: "home",
    engineError: null,
    status: {
      running: true,
      state: "hidden",
      title: "Ready",
      detail: "Hold your shortcut.",
      paused: false,
    },
  });
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        config,
        setup: { complete: true },
        credentials: {},
        autostart: false,
      };
    if (method === "status") return useApp.getState().status;
    if (method === "history" || method === "devices") return [];
    if (method === "summary") return { daily: {}, activity: {} };
    return { saved: true };
  }) as typeof ipc);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}
it("starts the service after setup without automatically recording", async () => {
  mount();
  await screen.findByRole("heading", { name: "Dictation" });
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("service.start", {}));
  expect(ipc).not.toHaveBeenCalledWith("control", { action: "start" });
  expect(document.documentElement.dataset.reducedMotion).toBe("true");
});
it("collapses the sidebar and persists the preference", async () => {
  mount();
  await screen.findByRole("heading", { name: "Dictation" });
  await userEvent.click(screen.getByRole("button", { name: "Toggle Sidebar" }));
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", {
      config: {
        ...config,
        desktop: { ...config.desktop, sidebar_visible: false },
      },
    }),
  );
  expect(
    document.querySelector('[data-state="collapsed"]'),
  ).toBeInTheDocument();
});
it("opens first-run setup without starting the service", async () => {
  vi.mocked(ipc).mockImplementation((async (method: string) =>
    method === "bootstrap"
      ? { config, setup: { complete: false }, credentials: {}, privacy: "" }
      : []) as typeof ipc);
  mount();
  await screen.findByText("Set up your provider");
  expect(ipc).not.toHaveBeenCalledWith("service.start", {});
});
it("changes and saves the palette independently, then restores it on reload", async () => {
  const view = mount();
  await screen.findByRole("heading", { name: "Dictation" });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  const themes = await screen.findByRole("region", { name: "Theme" });
  expect(
    within(themes).getByRole("combobox", { name: "Appearance" }),
  ).toBeInTheDocument();
  await userEvent.click(
    within(themes).getByRole("combobox", { name: "Color theme" }),
  );
  expect(screen.getAllByRole("option")).toHaveLength(7);
  await userEvent.click(screen.getByRole("option", { name: "Ocean" }));
  await waitFor(() =>
    expect(document.documentElement.dataset.colorTheme).toBe("ocean"),
  );
  const saved = {
    ...config,
    desktop: { ...config.desktop, color_theme: "ocean" },
  };
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", { config: saved }),
  );
  expect(document.documentElement).toHaveClass("dark");
  view.unmount();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        config: saved,
        setup: { complete: true },
        credentials: {},
        autostart: false,
      };
    if (method === "status") return useApp.getState().status;
    if (method === "history" || method === "devices") return [];
    if (method === "summary") return { daily: {}, activity: {} };
    return { saved: true };
  }) as typeof ipc);
  mount();
  await screen.findByRole("combobox", { name: "Color theme" });
  expect(document.documentElement.dataset.colorTheme).toBe("ocean");
});

it("shows engine failure and requires confirmation before restarting without replay", async () => {
  mount();
  await screen.findByRole("heading", { name: "Dictation" });
  act(() =>
    useApp.setState({
      status: null,
      engineError: "Python engine disconnected.",
    }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Engine unavailable");
  expect(invoke).not.toHaveBeenCalledWith("restart_app", { discard: true });
  await userEvent.click(screen.getByRole("button", { name: "Restart Caelum" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("will not be replayed");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Restart Caelum" }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("restart_app", { discard: true }),
  );
  expect(ipc).not.toHaveBeenCalledWith("control", { action: "start" });
});
it("can recover after a failed settings save without replaying the save on restart", async () => {
  const implementation = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "settings.save"
      ? Promise.reject(new Error("Engine disconnected"))
      : implementation(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: "Dictation" });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("combobox", { name: "Color theme" }),
  );
  await userEvent.click(screen.getByRole("option", { name: "Ocean" }));
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", expect.anything()),
  );
  act(() =>
    useApp.setState({
      status: null,
      engineError: "Python engine disconnected.",
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Restart Caelum" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("unsaved settings may be lost");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Restart Caelum" }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("restart_app", { discard: true }),
  );
  expect(
    vi.mocked(ipc).mock.calls.filter(([method]) => method === "settings.save"),
  ).toHaveLength(1);
});
