import {
  render,
  screen,
  waitFor,
  within,
  act,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, it, expect, beforeEach } from "vitest";
import App from "./App";
import { invoke } from "@tauri-apps/api/core";
import { ipc, IpcError, type Config } from "@/lib/ipc";
import { useApp } from "@/stores/app";
import { toast } from "sonner";
import { testModels } from "@/test-models";
import { testConfig } from "@/test-config";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => undefined),
}));
vi.mock("@/lib/ipc", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/ipc")>()),
  ipc: vi.fn(),
}));
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
    if (method === "updates.testing") return null;
    if (method === "history" || method === "devices") return [];
    if (method === "summary") return { daily: {}, activity: {} };
    return { saved: true };
  }) as typeof ipc);
});
function mount(
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}
it("starts the service after setup without automatically recording", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("service.start", {}));
  expect(ipc).not.toHaveBeenCalledWith("control", { action: "start" });
  expect(document.documentElement.dataset.reducedMotion).toBe("true");
});
it("shows the settings path and only resets on request, keeping failure and backup paths visible", async () => {
  let attempts = 0;
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      throw new IpcError("invalid_config", "Invalid settings file: /profile/config.toml", false);
    if (method === "settings.reset_invalid") {
      if (!attempts++) throw new Error("Permission denied");
      return { backup_path: "/profile/config.toml.original.bak" };
    }
    return useApp.getState().status;
  }) as typeof ipc);
  mount();
  await screen.findByText("Invalid settings file: /profile/config.toml");
  expect(ipc).not.toHaveBeenCalledWith("settings.reset_invalid", {});
  const reset = screen.getByRole("button", { name: "Back up and reset settings" });
  await userEvent.click(reset);
  expect(await screen.findByRole("alert")).toHaveTextContent("Permission denied");
  await userEvent.click(reset);
  expect(await screen.findByRole("status")).toHaveTextContent("/profile/config.toml.original.bak");
  expect(screen.getByRole("button", { name: "Continue to setup" })).toBeEnabled();
  expect(ipc).not.toHaveBeenCalledWith("service.start", {});
});
it("keeps unrelated startup failures on connection recovery", async () => {
  vi.mocked(ipc).mockRejectedValue(new IpcError("disconnected", "Disconnected", false));
  mount();
  await screen.findByRole("heading", { name: "Caelum couldn’t start." });
  expect(screen.queryByRole("button", { name: /reset settings/i })).not.toBeInTheDocument();
});
it.each(["queued", "installed"])("reconciles a %s Windows update without an online check", async (state) => {
  const agent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Windows NT");
  const confirmed = vi.spyOn(toast, "success");
  const reminder = vi.spyOn(toast, "info");
  try {
    const original = vi.mocked(ipc).getMockImplementation()!;
    vi.mocked(ipc).mockImplementation(((method, params) => method === "updates.pending"
      ? Promise.resolve({ state, version: "0.5.1" }) : original(method, params)) as typeof ipc);
    mount();
    if (state === "installed")
      await waitFor(() => expect(confirmed).toHaveBeenCalledWith("Update confirmed: Caelum 0.5.1 is running."));
    else {
      await waitFor(() => expect(reminder).toHaveBeenCalledWith(expect.stringContaining("0.5.1 is not installed yet")));
      expect(confirmed).not.toHaveBeenCalled();
    }
    expect(ipc).not.toHaveBeenCalledWith("updates.check", {});
    expect(ipc).not.toHaveBeenCalledWith("updates.apply", {});
  } finally {
    agent.mockRestore();
    confirmed.mockRestore();
    reminder.mockRestore();
  }
});
it("collapses the sidebar and persists the preference", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.click(screen.getByRole("button", { name: "Toggle Sidebar" }));
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", {
      config: { desktop: { sidebar_visible: false } },
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
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Appearance" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Appearance" }));
  await userEvent.click(screen.getByRole("option", { name: "Light" }));
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", {
      config: { desktop: { theme: "light" } },
    }),
  );
  expect(document.documentElement).not.toHaveClass("dark");
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
});

it("shows engine failure and requires confirmation before restarting without replay", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
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
  await screen.findByRole("heading", { name: /Record, finish/ });
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
        ? Promise.resolve(null)
        : implementation(method as never, params as never)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(await screen.findByRole("button", { name: "System" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Check updates" }),
  );
  const result = await screen.findByText("No newer stable release.", {
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
  await screen.findByRole("heading", { name: /Record, finish/ });
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
  await screen.findByRole("heading", { name: /Record, finish/ });
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
  await screen.findByRole("heading", { name: /Record, finish/ });
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
  await screen.findByRole("heading", { name: /Record, finish/ });
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
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(
    screen.queryByRole("option", { name: "Manage keys" }),
  ).not.toBeInTheDocument();
  expect(ipc).not.toHaveBeenCalledWith("service.start", {});
});

it("names the sidebar toggle and supports Ctrl+B without repeating on key hold", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  const trigger = screen.getByRole("button", { name: "Toggle Sidebar" });
  expect(trigger).toHaveAttribute("aria-label", "Toggle Sidebar");
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(trigger).toHaveAttribute("aria-controls", "main-navigation");
  await userEvent.keyboard("{Control>}b{/Control}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  fireEvent.keyDown(window, { key: "b", ctrlKey: true, repeat: true });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  const history = within(
    screen.getByRole("navigation", { name: "Main navigation" }),
  ).getByRole("button", { name: "History" });
  expect(history).toHaveAttribute("aria-label", "History");
  await userEvent.hover(history);
  expect(await screen.findByRole("tooltip")).toHaveTextContent("History");
  await userEvent.unhover(history);
  await userEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
});

it("restores the collapsed sidebar from backend settings", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "bootstrap"
      ? Promise.resolve({
          config: {
            ...config,
            desktop: { ...config.desktop, sidebar_visible: false },
          },
          setup: { complete: true },
          credentials: {},
        })
      : original(method, params)) as typeof ipc);
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  expect(
    screen.getByRole("button", { name: "Toggle Sidebar" }),
  ).toHaveAttribute("aria-expanded", "false");
});

it("moves focus into the destination screen and keeps one recording mode control", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  expect(
    screen.queryByRole("combobox", { name: "Recording mode" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "History" }));
  expect(screen.getByRole("heading", { name: "History" })).toHaveFocus();
  expect(document.getElementById("main-content")).toHaveAttribute(
    "aria-label",
    "History",
  );
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(
    screen.getAllByRole("combobox", { name: "Recording mode" }),
  ).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "Appearance" }));
  expect(screen.getByRole("region", { name: "Appearance" })).toHaveFocus();
});

it("lets shortcut capture consume Ctrl+B without collapsing the sidebar", async () => {
  mount();
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Recording shortcut" }),
  );
  await userEvent.keyboard("{Control>}b{/Control}");
  expect(
    screen.getByRole("button", { name: "Recording shortcut" }),
  ).toHaveTextContent("CTRL + B");
  expect(
    screen.getByRole("button", { name: "Toggle Sidebar" }),
  ).toHaveAttribute("aria-expanded", "true");
});

it("separates a saved portal preference from the binding reported before and after restart", async () => {
  const session = {
    ...useApp.getState().status!,
    backend: "portable", hotkey: "CTRL + V", shortcut_mode: "portal",
    shortcut_description: "Control+V",
  };
  useApp.setState({ status: session });
  mount();
  await screen.findByText("Active shortcut: Control+V");
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await screen.findByText("Pending shortcut: SUPER + ALT + V");
  expect(screen.getByText("Active shortcut: Control+V")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Restart Caelum" }));
  expect(invoke).toHaveBeenCalledWith("restart_app", { discard: false });

  act(() => useApp.setState({ status: {
    ...session, hotkey: config.app.hotkey, shortcut_mode: "pending",
    shortcut_description: "Waiting for desktop shortcut approval.",
  } }));
  expect(screen.getByText("Waiting for desktop shortcut approval.")).toBeInTheDocument();
  expect(screen.queryByText(/Active shortcut:/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restart Caelum" })).not.toBeInTheDocument();
  act(() => useApp.setState({ status: {
    ...session, hotkey: config.app.hotkey, shortcut_description: "Meta+D",
  } }));
  expect(screen.getByText("Active shortcut: Meta+D")).toBeInTheDocument();
  expect(screen.queryByText(/Pending shortcut:/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restart Caelum" })).not.toBeInTheDocument();
  act(() => useApp.setState({ status: {
    ...session, hotkey: config.app.hotkey, shortcut_mode: "manual", shortcut_description: "Use Record",
  } }));
  expect(screen.getByText("No active portal shortcut. Use Record")).toBeInTheDocument();
});

it("keeps a background model switch when an appearance edit is waiting to save", async () => {
  const saved = structuredClone(testConfig);
  saved.stt.engine = "local";
  saved.stt.local_model = "parakeet-v3";
  const snapshot = () => ({
    config: structuredClone(saved),
    setup: { complete: true },
    credentials: {},
    autostart: false,
  });
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "bootstrap"
      ? Promise.resolve(snapshot())
      : original(method, params)) as typeof ipc);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  mount(client);
  await screen.findByRole("heading", { name: /Record, finish/ });
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Appearance" }),
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Appearance" }));
  await userEvent.click(screen.getByRole("option", { name: "Light" }));
  await act(async () => {
    saved.stt.local_model = "cohere-transcribe";
    client.setQueryData(["bootstrap"], snapshot());
  });
  await waitFor(() =>
    expect(ipc).toHaveBeenCalledWith("settings.save", {
      config: { desktop: { theme: "light" } },
    }),
  );
  const saves = vi
    .mocked(ipc)
    .mock.calls.filter(([method]) => method === "settings.save");
  expect(
    saves.every(
      ([, params]) => !("stt" in (params as { config: object }).config),
    ),
  ).toBe(true);
});

it("retries an incompatible language with the installed model selected while saving", async () => {
  const saved = structuredClone(testConfig);
  Object.assign(saved.stt, { engine: "local", local_model: "parakeet-v3", language: "en" });
  const model = { ...testModels.models[0], id: "whisper-turbo", languages: ["ja"], state: "installed" };
  let rejectLanguage!: (reason: Error) => void;
  const firstSave = new Promise((_, reject) => { rejectLanguage = reject; });
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) => {
    if (method === "bootstrap")
      return Promise.resolve({ config: structuredClone(saved), setup: { complete: true }, credentials: {} });
    if (method === "models.list")
      return Promise.resolve({ ...testModels, models: [model] });
    if (method === "settings.save") {
      const { config } = params as { config: { stt: Partial<Config["stt"]> } };
      if (!config.stt.local_model) return firstSave;
      Object.assign(saved.stt, config.stt);
      return Promise.resolve({ saved: true });
    }
    return original(method, params);
  }) as typeof ipc);
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
  await userEvent.click(await screen.findByRole("combobox", { name: "Language" }));
  await userEvent.click(screen.getByRole("option", { name: "Japanese" }));
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("settings.save", {
    config: { stt: { language: "ja" } },
  }));
  await userEvent.click(screen.getByRole("button", { name: "Transcription" }));
  await userEvent.click(await screen.findByRole("button", { name: "Use" }));
  await act(async () => rejectLanguage(new Error("Unsupported language")));
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("settings.save", {
    config: { stt: { language: "ja", local_model: "whisper-turbo" } },
  }));
  expect(ipc).not.toHaveBeenCalledWith("models.use", expect.anything());
});
