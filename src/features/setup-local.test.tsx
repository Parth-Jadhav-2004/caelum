import { useState } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { Setup } from "./setup";
import { ipc, type Config, type ModelList } from "@/lib/ipc";
import { testConfig } from "@/test-config";
import { testModels } from "@/test-models";
import { TooltipProvider } from "@/components/ui/tooltip";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let list: ModelList;
let current: Config;
beforeEach(() => {
  list = structuredClone(testModels);
  current = structuredClone(testConfig);
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        config: current,
        setup: { stage: 0, complete: false },
        credentials: {},
        privacy: "",
      };
    if (method === "models.list") return list;
    if (method === "models.use") {
      list.models[0].state = "downloading";
      list.pending_use = "parakeet-v3";
      return { saved: true };
    }
    if (method === "devices") return [];
    if (method === "shortcut.check") return "Available";
    if (method === "setup.validate") return { storage: {} };
    if (method === "practice") return { text: "Hello Caelum", refined: false };
    return { ok: true };
  }) as typeof ipc);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Harness() {
    const [config, setConfig] = useState(current);
    return (
      <Setup
        config={config}
        commit={async (next) => {
          current = next;
          setConfig(next);
        }}
      />
    );
  }
  render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Harness />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return client;
}
async function chooseLocal() {
  await userEvent.click(
    screen.getByRole("combobox", { name: "Transcribe with" }),
  );
  await userEvent.click(
    screen.getByRole("option", { name: "On this computer" }),
  );
  await screen.findByRole("radiogroup", { name: "Speech model" });
}
async function goToPractice() {
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Choose your shortcut" });
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Try it" });
}
it("starts a model download on the welcome screen and skips API keys", async () => {
  mount();
  await chooseLocal();
  await userEvent.click(screen.getByRole("radio", { name: "Parakeet" }));
  expect(ipc).toHaveBeenCalledWith("models.use", {
    id: "parakeet-v3",
    when_ready: true,
  });
  expect(
    screen.getByRole("heading", { name: "Welcome to Caelum" }),
  ).toBeInTheDocument();
  await goToPractice();
  expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();
  expect(ipc).not.toHaveBeenCalledWith("setup.validate", expect.anything());
  expect(
    screen.getByText("Your practice recording stays on this computer."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Record practice" }),
  ).toBeDisabled();
  expect(current.stt.local_model).toBe("");
});
it("can finish while the selected model keeps downloading", async () => {
  mount();
  await chooseLocal();
  await userEvent.click(screen.getByRole("radio", { name: "Parakeet" }));
  await goToPractice();
  await userEvent.click(screen.getByRole("button", { name: "Try it later" }));
  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  expect(ipc).toHaveBeenCalledWith("setup.finish", { skip_practice: true });
  expect(ipc).not.toHaveBeenCalledWith("models.cancel", expect.anything());
});
it("allows setup without choosing or downloading a model", async () => {
  mount();
  await chooseLocal();
  await userEvent.click(
    screen.getByRole("button", { name: "Continue without a model" }),
  );
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).not.toHaveBeenCalledWith("models.use", expect.anything());
  expect(current.stt.engine).toBe("local");
});
it("explains the Online recommendation for Hindi", async () => {
  list.hardware.language = "hi";
  list.recommended = {
    id: null,
    reason_code: "indian_language",
    reason_text: "Online works best for Hindi for now.",
  };
  mount();
  await chooseLocal();
  expect(
    await screen.findByText(list.recommended.reason_text),
  ).toBeInTheDocument();
});
it("keeps a failed download visible and allows setup to continue", async () => {
  const client = mount();
  await chooseLocal();
  await userEvent.click(screen.getByRole("radio", { name: "Parakeet" }));
  await goToPractice();
  list.models[0].state = "failed";
  list.models[0].error = {
    code: "offline",
    message: "Download failed. Check your connection.",
  };
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["models"] });
  });
  expect(
    await screen.findByText("Download failed. Check your connection."),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try it later" })).toBeEnabled();
});
