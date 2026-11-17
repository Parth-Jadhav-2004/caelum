import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Settings } from "./settings";
import { ipc } from "@/lib/ipc";
import { testConfig } from "@/test-config";
import { useApp } from "@/stores/app";
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
  await userEvent.click(screen.getByRole("radio", { name: "Mint" }));
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("radio", { name: "Iris" })).toBeChecked();
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
  expect(screen.getByRole("button", { name: "Check updates" })).toBeEnabled();
});
