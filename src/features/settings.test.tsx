import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { act, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Settings } from "./settings";
import { ipc } from "@/lib/ipc";
import { testModels } from "@/test-models";
import { testConfig } from "@/test-config";
import { useApp } from "@/stores/app";
import { useDownloads } from "@/stores/models";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => undefined),
}));
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));

function mount(storage: string | { description: string; storage: string }) {
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return { credentials: { GROQ_API_KEY: storage } };
    if (method === "devices") return [];
    return false;
  }) as typeof ipc);
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings config={testConfig} change={vi.fn()} saveState="Saved" />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
describe("credential storage warning", () => {
  it("warns for unencrypted files and links to key management", async () => {
    mount({ description: "Saved locally", storage: "file" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API keys are stored unencrypted",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Transcription" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Manage keys" }));
    expect(useApp.getState().page).toBe("setup");
  });
  it("supports legacy unencrypted descriptions", async () => {
    mount("key saved in private file (not encrypted)");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API keys are stored unencrypted",
    );
  });
  it.each([
    { description: "not encrypted is only display text", storage: "keyring" },
    "key saved in desktop keyring",
    "key present in environment",
    "key missing; open setup to add a key",
  ])("does not warn for %s", async (storage) => {
    mount(storage);
    await screen.findByRole("combobox", { name: "Microphone" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

it("keeps model browsing passive and restores the confirmed transfer when returning to Transcription", async () => {
  const list = structuredClone(testModels);
  const model = list.models[1];
  model.visible = false;
  model.total_bytes = model.download_bytes;
  const client = new QueryClient();
  const config = structuredClone(testConfig);
  config.stt.engine = "local";
  const commit = vi.fn();
  vi.mocked(ipc)
    .mockClear()
    .mockImplementation((async (method: string, params: { id?: string }) => {
      if (method === "bootstrap") return { config, credentials: {} };
      if (method === "models.list") return structuredClone(list);
      if (method === "models.download" && params.id === model.id)
        model.state = "queued";
      return { ok: true };
    }) as typeof ipc);
  render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Settings
          config={config}
          change={vi.fn()}
          commit={commit}
          initialGroup="Transcription"
          saveState="Saved"
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Show all models (1)" }),
  );
  await userEvent.click(screen.getByRole("radio", { name: "Parakeet" }));
  await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowUp} ");
  const radio = screen.getByRole("radio", { name: model.label });
  expect(radio).toBeChecked();
  expect(radio).toHaveAccessibleDescription("Download: 109 MB Not installed");
  expect(commit).not.toHaveBeenCalled();
  expect(
    vi
      .mocked(ipc)
      .mock.calls.filter(
        ([method]) => method.startsWith("models.") && method !== "models.list",
      ),
  ).toEqual([]);
  await userEvent.click(
    screen.getByRole("button", { name: `Download ${model.label}` }),
  );
  const bar = { name: `${model.label} download` };
  expect(await screen.findByRole("progressbar", bar)).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await userEvent.click(screen.getByRole("button", { name: "Appearance" }));
  function progress(
    state: "downloading" | "verifying" | "ready",
    bytes: number,
  ) {
    useDownloads
      .getState()
      .update({
        id: model.id,
        state,
        received_bytes: bytes,
        total_bytes: model.total_bytes,
        error: null,
        eta_seconds: null,
        bytes_per_sec: 0,
      });
  }
  act(() => progress("downloading", 54_000_000));
  await userEvent.click(screen.getByRole("button", { name: "Transcription" }));
  expect(await screen.findByRole("progressbar", bar)).toHaveAttribute(
    "aria-valuetext",
    "Downloading · 50% · 54 MB / 109 MB",
  );
  act(() => progress("verifying", model.total_bytes));
  expect(screen.getByRole("progressbar", bar)).toHaveAttribute(
    "aria-valuetext",
    expect.stringContaining("Verifying files"),
  );
  expect(screen.queryByRole("button", { name: "Use" })).toBeNull();
  model.state = "installed";
  await act(async () => {
    progress("ready", model.total_bytes);
    await client.invalidateQueries({ queryKey: ["models"] });
  });
  await userEvent.click(await screen.findByRole("button", { name: "Use" }));
  expect(commit).toHaveBeenCalledWith({
    ...config,
    stt: { ...config.stt, local_model: model.id },
  });
  expect(
    vi
      .mocked(ipc)
      .mock.calls.filter(
        ([method]) => method === "models.download" || method === "models.use",
      ),
  ).toEqual([["models.download", { id: model.id }]]);
});

it("offers exactly seven settings groups and keeps advanced fields separate", async () => {
  mount({ description: "Saved", storage: "keyring" });
  const nav = screen.getByRole("navigation", { name: "Settings groups" });
  expect(nav.querySelectorAll("button")).toHaveLength(7);
  expect(screen.queryByLabelText("Provider URL")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Advanced" }));
  expect(screen.getAllByLabelText("Provider URL")).toHaveLength(2);
});
it("adds and removes vocabulary through the existing settings contract", async () => {
  const change = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings
          config={{
            ...testConfig,
            stt: { ...testConfig.stt, vocabulary: "Caelum" },
          }}
          change={change}
          saveState="Saved"
          initialGroup="Dictionary"
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "New word" }),
    "Parth",
  );
  await userEvent.click(screen.getByRole("button", { name: "Add" }));
  expect(change).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stt: expect.objectContaining({ vocabulary: "Caelum, Parth" }),
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Remove Caelum" }));
  expect(change).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stt: expect.objectContaining({ vocabulary: "" }),
    }),
  );
});
it("saves Forever without changing the existing day limit", async () => {
  const change = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings
          config={testConfig}
          change={change}
          saveState="Saved"
          initialGroup="Privacy & data"
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(
    screen.getByRole("combobox", { name: "Keep history for" }),
  );
  await userEvent.click(screen.getByRole("option", { name: "Forever" }));
  expect(change).toHaveBeenLastCalledWith(
    expect.objectContaining({
      desktop: expect.objectContaining({
        history_forever: true,
        retention_days: 30,
      }),
    }),
  );
});

it("persists an accent selected with the keyboard", async () => {
  const change = vi.fn();
  function AccentSettings() {
    const [config, setConfig] = useState(testConfig);
    return (
      <Settings
        config={config}
        change={(next) => {
          setConfig(next);
          change(next);
        }}
        saveState="Saved"
        initialGroup="Appearance"
      />
    );
  }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <AccentSettings />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  const accent = screen.getByRole("combobox", { name: "Caelum accent" });
  accent.focus();
  await userEvent.keyboard("{ArrowDown}{Home}{ArrowDown}{Enter}");
  expect(accent).toHaveTextContent("Iris");
  expect(change).toHaveBeenLastCalledWith(
    expect.objectContaining({
      desktop: expect.objectContaining({ color_theme: "caelum-iris" }),
    }),
  );
});

it("resets connection feedback when the checked provider changes", async () => {
  vi.mocked(ipc).mockImplementation((async (method: string) =>
    method === "bootstrap"
      ? { credentials: {} }
      : method === "providers.check"
        ? "Connected"
        : false) as typeof ipc);
  const client = new QueryClient();
  const view = (config: typeof testConfig) => (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Settings
          config={config}
          change={vi.fn()}
          saveState="Saved"
          initialGroup="Transcription"
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
  const mounted = render(view(testConfig));
  await userEvent.click(
    screen.getByRole("button", { name: "Test connection" }),
  );
  await screen.findByText("Connected");
  mounted.rerender(
    view({ ...testConfig, stt: { ...testConfig.stt, model: "another-model" } }),
  );
  expect(screen.queryByText("Connected")).not.toBeInTheDocument();
});

it.each([
  "Transcription: key missing; open Manage keys",
  "Transcription: model unavailable; choose another model in Advanced",
  "Transcription: connected (model available)\nRefinement: invalid API key",
])(
  "shows the provider check result without claiming success: %s",
  async (result) => {
    mount({ description: "Saved", storage: "keyring" });
    const original = vi.mocked(ipc).getMockImplementation()!;
    vi.mocked(ipc).mockImplementation(((method, params) =>
      method === "providers.check"
        ? Promise.resolve(result)
        : original(method, params)) as typeof ipc);
    await userEvent.click(
      screen.getByRole("button", { name: "Transcription" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Test connection" }),
    );
    expect(
      await screen.findByText(result.replace(/\n/g, " ")),
    ).toBeInTheDocument();
    expect(screen.queryByText("Connected ✓")).not.toBeInTheDocument();
  },
);

it("keeps update checks independent of an in-flight connection check", async () => {
  vi.mocked(ipc).mockImplementation((async (method: string) =>
    method === "bootstrap"
      ? { credentials: {} }
      : method === "providers.check"
        ? new Promise(() => {})
        : method === "updates.check"
          ? null
          : false) as typeof ipc);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings
          config={testConfig}
          change={vi.fn()}
          saveState="Saved"
          initialGroup="Transcription"
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Test connection" }),
  );
  expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "System" }));
  expect(
    await screen.findByRole("button", { name: "Check updates" }),
  ).toBeEnabled();
});

it("shows help on screen and focuses the selected group without repeated headings", async () => {
  mount({ description: "Saved", storage: "keyring" });
  await userEvent.click(screen.getByRole("button", { name: "System" }));
  expect(
    await screen.findByText("Caelum verifies updates against a signed release manifest."),
  ).toBeVisible();
  expect(screen.getByRole("region", { name: "System" })).toHaveFocus();
  expect(
    screen.queryByRole("heading", { name: "System" }),
  ).not.toBeInTheDocument();
});

it("finds same-version testing builds without offering unsigned automatic installation", async () => {
  mount({ description: "Saved", storage: "keyring" });
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "updates.check"
      ? Promise.resolve(null)
      : method === "updates.testing"
        ? Promise.resolve({ version: "0.4.1-rc.2", installed: false })
        : original(method, params)) as typeof ipc);
  await userEvent.click(screen.getByRole("button", { name: "System" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Check updates" }),
  );
  expect(
    await screen.findByRole("button", { name: "Download testing build" }),
  ).toBeEnabled();
  expect(screen.getByRole("status")).toHaveTextContent(
    "0.4.1-rc.2 is available for manual installation",
  );
  expect(
    screen.queryByRole("button", { name: "Update & restart" }),
  ).not.toBeInTheDocument();
  expect(ipc).not.toHaveBeenCalledWith("updates.stage", {});
  await userEvent.click(
    screen.getByRole("button", { name: "Download testing build" }),
  );
  expect(invoke).toHaveBeenCalledWith("open_releases", {
    version: "0.4.1-rc.2",
  });
});

it("reports a failed testing check while keeping a signed stable update available", async () => {
  mount({ description: "Saved", storage: "keyring" });
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "updates.check"
      ? Promise.resolve({ version: "0.4.2" })
      : method === "updates.testing"
        ? Promise.reject(new Error("Rate limited"))
        : original(method, params)) as typeof ipc);
  await userEvent.click(screen.getByRole("button", { name: "System" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Check updates" }),
  );
  expect(
    await screen.findByRole("button", { name: "Update & restart" }),
  ).toBeEnabled();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Testing releases could not be checked",
  );
});

it.each(["installed", "no_update"])(
  "restarts only when an update was installed (%s)",
  async (applied) => {
    vi.mocked(invoke).mockClear();
    mount({ description: "Saved", storage: "keyring" });
    let queued = true;
    const original = vi.mocked(ipc).getMockImplementation()!;
    vi.mocked(ipc).mockImplementation(((method, params) => {
      if (method === "updates.pending") return Promise.resolve(queued ? { state: "queued", version: "0.4.3" } : null);
      if (method === "updates.apply") {
        queued = false;
        return Promise.resolve(applied);
      }
      return original(method, params);
    }) as typeof ipc);
    await userEvent.click(screen.getByRole("button", { name: "System" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Update & restart" }),
    );
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Update & restart",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
    if (applied === "installed") expect(invoke).toHaveBeenCalledWith("restart_app");
    else {
      expect(invoke).not.toHaveBeenCalledWith("restart_app");
      expect(screen.getByRole("status")).toHaveTextContent(
        "No update is queued",
      );
    }
  },
);

it("explains SmartScreen before handing off to the Windows installer and quitting", async () => {
  const agent = vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Windows NT");
  try {
    vi.mocked(invoke).mockClear();
    mount({ description: "Saved", storage: "keyring" });
    const original = vi.mocked(ipc).getMockImplementation()!;
    vi.mocked(ipc).mockImplementation(((method, params) =>
      method === "updates.pending" ? Promise.resolve({ state: "queued", version: "0.4.3" })
      : method === "updates.apply" ? Promise.resolve("installer_launched")
      : original(method, params)) as typeof ipc);
    await userEvent.click(screen.getByRole("button", { name: "System" }));
    await userEvent.click(await screen.findByRole("button", { name: "Open installer" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("signed release manifest");
    expect(dialog).toHaveTextContent("not Authenticode-signed");
    expect(dialog).toHaveTextContent("SmartScreen");
    await userEvent.click(within(dialog).getByRole("button", { name: "Open installer" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("quit_app", { discard: false }));
    expect(invoke).not.toHaveBeenCalledWith("restart_app");
    expect(ipc).not.toHaveBeenCalledWith("updates.stage", {});
  } finally {
    agent.mockRestore();
  }
});

it("retains a queued update after failure and shows its installation error", async () => {
  mount({ description: "Saved", storage: "keyring" });
  let queued = false;
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) => {
    if (method === "updates.pending") return Promise.resolve(queued ? { state: "queued", version: "0.4.3" } : null);
    if (method === "updates.check")
      return Promise.resolve({ version: "0.4.3" });
    if (method === "updates.stage") {
      queued = true;
      return Promise.resolve("0.4.3");
    }
    if (method === "updates.apply")
      return Promise.reject("The package database is locked.");
    return original(method, params);
  }) as typeof ipc);
  await userEvent.click(screen.getByRole("button", { name: "System" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Check updates" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Update & restart" }),
  );
  const confirm = within(screen.getByRole("alertdialog")).getByRole("button", {
    name: "Update & restart",
  });
  await userEvent.click(confirm);
  expect(
    await screen.findByText("The package database is locked."),
  ).toBeVisible();
  await waitFor(() => expect(confirm).toBeEnabled());
  await userEvent.click(confirm);
  expect(
    vi.mocked(ipc).mock.calls.filter(([method]) => method === "updates.stage"),
  ).toHaveLength(1);
});


function mountLocalSettings() {
  const change = vi.fn();
  vi.mocked(ipc).mockImplementation((async (method: string) => method === "models.list" ? testModels : {}) as typeof ipc);
  const config = {
    ...testConfig,
    stt: { ...testConfig.stt, engine: "local", local_model: "parakeet-110m" },
    cleanup: {
      ...testConfig.cleanup,
      model: "cloud-cleanup",
      style: "code",
      local_style: "light",
      local_model: "",
      local_base_url: "http://127.0.0.1:11434/v1",
    },
  };
  function Harness() {
    const [draft, setDraft] = useState<typeof testConfig>(config);
    return (
      <Settings
        config={draft}
        change={(next) => { change(next); setDraft(next); }}
        saveState="Saved"
        initialGroup="Transcription"
      />
    );
  }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Harness />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { config, change };
}

it("lets keyboard users choose local refinement independently of their online style", async () => {
  const { config, change } = mountLocalSettings();
  const localStyle = screen.getByRole("combobox", { name: "Local refinement" });
  expect(localStyle).toHaveTextContent("Light");
  expect(localStyle).toHaveAccessibleDescription(/rules.*on this computer/i);
  localStyle.focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(screen.getAllByRole("option").map((option) => option.textContent))
    .toEqual(["Off", "Light", "Thorough"]);
  await userEvent.keyboard("{End}{Enter}");
  expect(change).toHaveBeenLastCalledWith({
    ...config, cleanup: { ...config.cleanup, local_style: "thorough" },
  });
  await userEvent.click(screen.getByRole("combobox", { name: "Transcription engine" }));
  await userEvent.click(screen.getByRole("option", { name: "Online" }));
  expect(screen.getByRole("combobox", { name: "Text cleanup" })).toHaveTextContent("Code");
  expect(screen.queryByRole("combobox", { name: "Local refinement" })).not.toBeInTheDocument();
});

it("saves the selected cleanup style through the generated settings contract", async () => {
  const change = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings config={testConfig} change={change} saveState="Saved" initialGroup="Transcription" />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("combobox", { name: "Text cleanup" }));
  await userEvent.click(screen.getByRole("option", { name: "Code" }));
  expect(change).toHaveBeenLastCalledWith(expect.objectContaining({
    cleanup: expect.objectContaining({ style: "code", reasoning_effort: "low" }),
  }));
});

it("can edit refinement for a local fallback without switching away from online transcription", async () => {
  const { change } = mountLocalSettings();
  await userEvent.click(screen.getByRole("combobox", { name: "Transcription engine" }));
  await userEvent.click(screen.getByRole("option", { name: "Online" }));
  await userEvent.click(screen.getByRole("combobox", { name: "Online fallback" }));
  await userEvent.click(screen.getByRole("option", { name: "Use a local model" }));
  await userEvent.click(screen.getByRole("combobox", { name: "Local refinement" }));
  await userEvent.click(screen.getByRole("option", { name: "Off" }));
  expect(change).toHaveBeenLastCalledWith(expect.objectContaining({
    stt: expect.objectContaining({ engine: "online", fallback: "local" }),
    cleanup: expect.objectContaining({ local_style: "off", model: "cloud-cleanup", style: "code" }),
  }));
});

it("configures an optional local model and retains it while refinement is off", async () => {
  const { config, change } = mountLocalSettings();
  await userEvent.click(screen.getByText("Optional local refinement model"));
  const model = screen.getByRole("textbox", { name: "Local refinement model" });
  const url = screen.getByRole("textbox", { name: "Local server URL" });
  expect(model).toHaveValue("");
  expect(model).toHaveAccessibleDescription(/built-in rules.*unavailable/i);
  expect(url).toHaveAccessibleDescription(/loopback/i);
  await userEvent.type(model, "my-installed-model");
  await userEvent.clear(url);
  await userEvent.type(url, "http://127.0.0.1:8080/v1");
  await userEvent.click(screen.getByRole("combobox", { name: "Local refinement" }));
  await userEvent.click(screen.getByRole("option", { name: "Off" }));
  expect(screen.queryByText("Optional local refinement model")).not.toBeInTheDocument();
  expect(change).toHaveBeenLastCalledWith({
    ...config,
    cleanup: {
      ...config.cleanup,
      local_style: "off",
      local_model: "my-installed-model",
      local_base_url: "http://127.0.0.1:8080/v1",
    },
  });
});
