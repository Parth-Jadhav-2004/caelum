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
    settingsGroup: "General",
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
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("service.start", {}));
  expect(ipc).not.toHaveBeenCalledWith("control", { action: "start" });
  expect(document.documentElement.dataset.reducedMotion).toBe("true");
});
it("collapses the sidebar and persists the preference", async () => {
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
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
  expect(
    screen.getByRole("button", { name: "Caelum home" }),
  ).toBeInTheDocument();
});
it("opens first-run setup without starting the service", async () => {
  vi.mocked(ipc).mockImplementation((async (method: string) =>
    method === "bootstrap"
      ? { config, setup: { complete: false }, credentials: {}, privacy: "" }
      : []) as typeof ipc);
  mount();
  await screen.findByText("Welcome to Caelum");
  expect(ipc).not.toHaveBeenCalledWith("service.start", {});
});
it("saves appearance while keeping the Caelum identity", async () => {
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Appearance" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Appearance" }));
  await userEvent.click(screen.getByRole("option", { name: "Light" }));
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", {
      config: { ...config, desktop: { ...config.desktop, theme: "light" } },
    }),
  );
  expect(document.documentElement).not.toHaveClass("dark");
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
});

it("shows engine failure and requires confirmation before restarting without replay", async () => {
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  act(() =>
    useApp.setState({
      status: null,
      engineError: "Python engine disconnected.",
    }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Caelum stopped.");
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
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Appearance" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Appearance" }));
  await userEvent.click(screen.getByRole("option", { name: "Light" }));
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

it("shows stable update results beside the update controls and links to releases", async () => {
  const implementation = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "updates.check"
      ? Promise.resolve(null)
      : method === "updates.pending"
        ? Promise.resolve(false)
        : implementation(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(await screen.findByRole("button", { name: "System" }));
  await userEvent.click(screen.getByRole("button", { name: "Check updates" }));
  const result = await screen.findByText("Up to date", {
    selector: "p[role=status]",
  });
  expect(result).toHaveAttribute("role", "status");
  expect(screen.getByRole("button", { name: "System" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await userEvent.click(screen.getByRole("button", { name: "View releases" }));
  expect(invoke).toHaveBeenCalledWith("open_releases");
});

it("closes returning-user key management back to Transcription without changing startup", async () => {
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(screen.getByRole("button", { name: "Transcription" }));
  await userEvent.click(screen.getByRole("button", { name: "Manage keys" }));
  await screen.findByRole("heading", { name: "Manage keys" });
  expect(
    screen.queryByRole("button", { name: "Get started" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(
    await screen.findByRole("region", { name: "Transcription" }),
  ).toBeInTheDocument();
  expect(useApp.getState().page).toBe("settings");
  expect(ipc).not.toHaveBeenCalledWith("launcher", expect.anything());
  expect(ipc).not.toHaveBeenCalledWith("setup.finish", expect.anything());
});

it("returns to Transcription after validating a replacement key", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "setup.validate"
      ? Promise.resolve({ storage: { GROQ_API_KEY: "keyring" } })
      : original(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(screen.getByRole("button", { name: "Transcription" }));
  await userEvent.click(screen.getByRole("button", { name: "Manage keys" }));
  await userEvent.type(
    await screen.findByLabelText("API key"),
    "replacement-key",
  );
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Save keys" }));
  expect(
    await screen.findByRole("region", { name: "Transcription" }),
  ).toBeInTheDocument();
  expect(ipc).toHaveBeenCalledWith("setup.validate", {
    consent: true,
    keys: { GROQ_API_KEY: "replacement-key" },
  });
  for (const method of [
    "microphone.test",
    "shortcut.check",
    "practice",
    "launcher",
    "setup.finish",
  ]) {
    expect(vi.mocked(ipc).mock.calls.some(([name]) => name === method)).toBe(
      false,
    );
  }
});

it("names key management in the palette and hides that entry while managing keys", async () => {
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.keyboard("{Control>}k{/Control}");
  const entry = await screen.findByRole("option", { name: "Manage keys" });
  expect(screen.queryByText("Setup & keys")).not.toBeInTheDocument();
  await userEvent.click(entry);
  await screen.findByRole("heading", { name: "Manage keys" });
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(
    screen.queryByRole("option", { name: "Manage keys" }),
  ).not.toBeInTheDocument();
});

it("opens key storage review directly in returning-user key management", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "bootstrap"
      ? Promise.resolve({
          config,
          setup: { complete: true },
          autostart: false,
          credentials: {
            GROQ_API_KEY: { description: "Saved", storage: "file" },
          },
        })
      : original(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Review key storage" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Manage keys" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(
    await screen.findByRole("region", { name: "Transcription" }),
  ).toBeInTheDocument();
  expect(ipc).not.toHaveBeenCalledWith("launcher", expect.anything());
});

it("omits key management from the palette until onboarding is complete", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "bootstrap"
      ? Promise.resolve({
          config,
          setup: { complete: false },
          credentials: {},
          autostart: false,
          privacy: "",
        })
      : original(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: "Welcome to Caelum" });
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(
    screen.queryByRole("option", { name: "Manage keys" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Setup & keys" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("option", { name: "Home" }));
  await screen.findByRole("heading", { name: /dictate anywhere/ });
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(
    screen.queryByRole("option", { name: "Manage keys" }),
  ).not.toBeInTheDocument();
  expect(ipc).not.toHaveBeenCalledWith("service.start", {});
});
