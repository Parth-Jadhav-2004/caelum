import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, it, expect, beforeEach } from "vitest";
import { Setup } from "./setup";
import { ipc } from "@/lib/ipc";
import { testConfig } from "@/test-config";
import { useApp } from "@/stores/app";
import { useState } from "react";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        config: testConfig,
        autostart: false,
        privacy: "Audio goes to your selected service.",
        credentials: {
          GROQ_API_KEY: { description: "Key missing", storage: "missing" },
        },
      };
    if (method === "devices") return [];
    if (method === "setup.validate") return { storage: {} };
    if (method === "practice")
      return { text: "A little less typing.", refined: true };
    return { ok: true };
  }) as typeof ipc);
});
function mount(initialConfig = testConfig) {
  function StatefulSetup() {
    const [config, setConfig] = useState(initialConfig);
    return <Setup config={config} commit={async (next) => setConfig(next)} />;
  }
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <StatefulSetup />
    </QueryClientProvider>,
  );
}
async function connect() {
  await userEvent.click(screen.getByRole("button", { name: "Get started" }));
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
}
it("starts with a time estimate and requires consent before validating a key", async () => {
  mount();
  expect(screen.getByText("About two minutes")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Get started" }));
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("API key"), "test-only");
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).toHaveBeenCalledWith("setup.validate", {
    consent: true,
    keys: { GROQ_API_KEY: "test-only" },
  });
  expect(ipc).not.toHaveBeenCalledWith("credentials.store", expect.anything());
});
it("retains both providers' pending keys across selection changes and failed validation", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  let attempts = 0;
  vi.mocked(ipc).mockImplementation(((method, params) => {
    if (method === "setup.validate" && attempts++ === 0)
      return Promise.reject(new Error("Provider unavailable"));
    return original(method, params);
  }) as typeof ipc);
  mount({
    ...testConfig,
    cleanup: {
      ...testConfig.cleanup,
      model: "cleanup-model",
      key_env: "CLEANUP_KEY",
    },
  });
  await userEvent.click(screen.getByRole("button", { name: "Get started" }));
  await userEvent.type(screen.getByLabelText("API key"), "speech-key");
  await userEvent.click(screen.getByRole("combobox", { name: "Key to edit" }));
  await userEvent.click(screen.getByRole("option", { name: "CLEANUP_KEY" }));
  expect(screen.getByLabelText("API key")).toHaveValue("");
  await userEvent.type(screen.getByLabelText("API key"), "cleanup-key");
  await userEvent.click(screen.getByRole("combobox", { name: "Key to edit" }));
  await userEvent.click(screen.getByRole("option", { name: "GROQ_API_KEY" }));
  expect(screen.getByLabelText("API key")).toHaveValue("speech-key");
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("Error: Provider unavailable");
  expect(screen.getByLabelText("API key")).toHaveValue("speech-key");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).toHaveBeenCalledWith("setup.validate", {
    consent: true,
    keys: { GROQ_API_KEY: "speech-key", CLEANUP_KEY: "cleanup-key" },
  });
  await userEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByLabelText("API key")).toHaveValue("");
});

it("uses a renamed credential and excludes pending keys no longer in the configuration", async () => {
  mount({
    ...testConfig,
    stt: { ...testConfig.stt, base_url: "https://speech.example/v1" },
  });
  await userEvent.click(screen.getByRole("button", { name: "Get started" }));
  await userEvent.type(screen.getByLabelText("API key"), "obsolete-key");
  await userEvent.click(
    screen.getByRole("button", { name: "Use another service" }),
  );
  await userEvent.clear(screen.getByLabelText("Key name"));
  await userEvent.type(screen.getByLabelText("Key name"), "SPEECH_KEY");
  await userEvent.keyboard("{Escape}");
  expect(
    screen.queryByRole("combobox", { name: "Key to edit" }),
  ).not.toBeInTheDocument();
  await userEvent.clear(screen.getByLabelText("API key"));
  await userEvent.type(screen.getByLabelText("API key"), "new-speech-key");
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).toHaveBeenCalledWith("setup.validate", {
    consent: true,
    keys: { SPEECH_KEY: "new-speech-key" },
  });
});
it("automatically tests the microphone and gates Continue on its result", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  let finish: () => void = () => {};
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "microphone.test"
      ? new Promise((resolve) => {
          finish = () => resolve({ ok: true } as never);
        })
      : original(method, params)) as typeof ipc);
  mount();
  await connect();
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("microphone.test", {}));
  expect(screen.getByRole("button", { name: "Listening…" })).toBeDisabled();
  await act(async () => finish());
  expect(await screen.findByText("We hear you ✓")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
});
it("completes six steps with one upload consent and real practice results", async () => {
  mount();
  await connect();
  await screen.findByText("We hear you ✓");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Choose your shortcut" });
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Try it" });
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Practice text" })).toHaveValue(
    "",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Record practice" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "Practice text" })).toHaveValue(
      "A little less typing.",
    ),
  );
  expect(ipc).toHaveBeenCalledWith("practice", { consent: true });
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "You’re all set" });
  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  await waitFor(() => expect(useApp.getState().page).toBe("home"));
  expect(ipc).toHaveBeenCalledWith("launcher", {
    autostart: true,
    enabled: false,
  });
  expect(ipc).toHaveBeenCalledWith("setup.finish", {});
});
it("requires a new practice run after revisiting the service and microphone checks", async () => {
  mount();
  await connect();
  await screen.findByText("We hear you ✓");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Record practice" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "You’re all set" });
  await userEvent.click(screen.getByRole("button", { name: "Change Service" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("We hear you ✓");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByRole("textbox", { name: "Practice text" })).toHaveValue(
    "",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Record practice" }),
  );
  expect(
    vi.mocked(ipc).mock.calls.filter(([method]) => method === "practice"),
  ).toHaveLength(2);
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("setup.finish", {}));
});
it("keeps failures on the microphone step and cancels the sample on unmount", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "microphone.test"
      ? Promise.reject(new Error("No speech. Try again"))
      : original(method, params)) as typeof ipc);
  const view = mount();
  await connect();
  await screen.findByText("Error: No speech. Try again");
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  view.unmount();
  expect(ipc).toHaveBeenCalledWith("sample.cancel", {});
});

it("records with the chosen shortcut and finishes capture on release", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  let finish: (value: unknown) => void = () => {};
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "practice"
      ? new Promise<unknown>((resolve) => {
          finish = resolve;
        })
      : original(method as never, params as never)) as typeof ipc);
  mount();
  await connect();
  await screen.findByText("We hear you ✓");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("textbox", { name: "Practice text" });
  await userEvent.keyboard("{Meta>}{Alt>}v{/Alt}{/Meta}");
  expect(ipc).toHaveBeenCalledWith("practice", {
    consent: true,
    interactive: true,
    insert: true,
  });
  expect(ipc).toHaveBeenCalledWith("sample.cancel", { finish: true });
  await act(async () =>
    finish({ text: "Actual practice", refined: true, inserted: true }),
  );
  expect(screen.getByRole("textbox", { name: "Practice text" })).toHaveValue(
    "Actual practice",
  );
});

it("cancels an active microphone check without advancing", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  let cancel = () => {};
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) => {
    if (method === "microphone.test")
      return new Promise<unknown>((_, reject) => {
        cancel = () => reject(new Error("Recording cancelled"));
      });
    if (method === "sample.cancel") {
      cancel();
      return Promise.resolve({ ok: true });
    }
    return original(method as never, params as never);
  }) as typeof ipc);
  mount();
  await connect();
  await screen.findByRole("button", { name: "Listening…" });
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(ipc).toHaveBeenCalledWith("sample.cancel", {});
  await screen.findByText("Error: Recording cancelled");
  expect(
    screen.getByRole("heading", { name: "Check your microphone" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
});

it("keeps the structured file-storage warning visible after microphone success", async () => {
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method: string, params: unknown) =>
    method === "setup.validate"
      ? Promise.resolve({ storage: { GROQ_API_KEY: "file" } })
      : original(method as never, params as never)) as typeof ipc);
  mount();
  await connect();
  await screen.findByText("We hear you ✓");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Key stored without encryption",
  );
});
