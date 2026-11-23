import { useState } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
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
  vi.mocked(ipc).mockImplementation((async (
    method: string,
    params: { id?: string; when_ready?: boolean },
  ) => {
    if (method === "bootstrap")
      return {
        config: current,
        setup: { stage: 0, complete: false },
        credentials: {},
        privacy: "",
      };
    if (method === "models.list") return structuredClone(list);
    const model = list.models.find((item) => item.id === params.id);
    if (method === "models.use" && model) {
      if (params.when_ready) {
        model.state = "downloading";
        list.pending_use = model.id;
      } else {
        current.stt.engine = "local";
        current.stt.local_model = model.id;
      }
      return { saved: true };
    }
    if (model && method === "models.pause") model.state = "paused";
    if (model && method === "models.resume") model.state = "downloading";
    if (model && method === "models.cancel") {
      model.state = "not_installed";
      list.pending_use = null;
    }
    if (method === "devices") return [];
    if (method === "shortcut.check")
      return { state: "available", message: "Available" };
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
  await userEvent.click(
    screen.getByRole("button", { name: "Download and continue" }),
  );
  await screen.findByRole("heading", { name: "Check your microphone" });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Choose your shortcut" });
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Try it" });
}
it("browses by mouse and keyboard, then downloads only the confirmed choice and skips API keys", async () => {
  mount();
  await chooseLocal();
  expect(
    screen.getByRole("progressbar", { name: "Setup step 1 of 5" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: "Parakeet" }));
  await userEvent.keyboard("{ArrowDown}{Enter}");
  expect(screen.getByRole("radio", { name: "Small and quick" })).toBeChecked();
  expect(screen.getByText("Download Small and quick · 109 MB")).toBeVisible();
  expect(ipc).not.toHaveBeenCalledWith("models.use", expect.anything());
  expect(ipc).not.toHaveBeenCalledWith("models.download", expect.anything());
  await goToPractice();
  expect(ipc).toHaveBeenCalledWith("models.use", {
    id: "parakeet-110m",
    when_ready: true,
  });
  expect(
    vi.mocked(ipc).mock.calls.filter(([method]) => method === "models.use"),
  ).toHaveLength(1);
  expect(
    screen.getByRole("progressbar", { name: "Setup step 4 of 5" }),
  ).toBeInTheDocument();
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
  await userEvent.click(screen.getByRole("radio", { name: "Small and quick" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Continue without a model" }),
  );
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).not.toHaveBeenCalledWith("models.use", expect.anything());
  expect(ipc).not.toHaveBeenCalledWith("models.download", expect.anything());
  expect(current.stt.engine).toBe("local");
});
it("keeps a transfer visible across steps and does not resume a paused download on Continue", async () => {
  mount();
  await chooseLocal();
  await userEvent.click(
    screen.getByRole("button", { name: "Download and continue" }),
  );
  await userEvent.click(await screen.findByRole("button", { name: "Pause" }));
  expect(
    await screen.findByRole("progressbar", { name: "Parakeet download" }),
  ).toHaveAttribute("aria-valuetext", expect.stringContaining("Paused"));
  await userEvent.click(screen.getByRole("button", { name: "Back" }));
  await screen.findByRole("button", { name: "Resume" });
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(await screen.findByRole("button", { name: "Resume" }));
  await screen.findByRole("button", { name: "Pause" });
  await userEvent.click(
    within(
      screen.getByRole("region", { name: "Speech model download" }),
    ).getByRole("button", { name: "Cancel" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("progressbar", { name: "Parakeet download" }),
    ).toBeNull(),
  );
  expect(
    vi
      .mocked(ipc)
      .mock.calls.filter(
        ([method]) => method.startsWith("models.") && method !== "models.list",
      ),
  ).toEqual([
    ["models.use", { id: "parakeet-v3", when_ready: true }],
    ["models.pause", { id: "parakeet-v3" }],
    ["models.resume", { id: "parakeet-v3" }],
    ["models.cancel", { id: "parakeet-v3" }],
  ]);
});
it("uses an existing verified installation with plain Continue", async () => {
  list.models[1].state = "installed";
  mount();
  await chooseLocal();
  await userEvent.click(screen.getByRole("radio", { name: "Small and quick" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(ipc).toHaveBeenCalledWith("models.use", { id: "parakeet-110m" });
  expect(ipc).not.toHaveBeenCalledWith("models.download", expect.anything());
});
it("saves the chosen local refinement with an installed speech model and skips provider setup", async () => {
  list.models[1].state = "installed";
  current.cleanup.model = "online-model";
  mount();
  expect(screen.queryByRole("combobox", { name: "Local refinement" })).not.toBeInTheDocument();
  await chooseLocal();
  await userEvent.click(screen.getByRole("combobox", { name: "Local refinement" }));
  await userEvent.click(screen.getByRole("option", { name: "Thorough" }));
  await userEvent.click(screen.getByRole("radio", { name: "Small and quick" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your microphone" });
  expect(current.stt.local_model).toBe("parakeet-110m");
  expect(current.cleanup).toMatchObject({ local_style: "thorough", model: "online-model" });
  expect(ipc).not.toHaveBeenCalledWith("setup.validate", expect.anything());
});
it("can change the recommendation and leave local setup without a transfer", async () => {
  mount();
  await chooseLocal();
  list.recommended = {
    id: null,
    reason_code: "indian_language",
    reason_text: "Online works best for Hindi for now.",
  };
  await userEvent.click(
    screen.getByRole("combobox", { name: "Dictation language" }),
  );
  await userEvent.click(screen.getByRole("option", { name: "Hindi" }));
  expect(await screen.findByText(list.recommended.reason_text)).toBeVisible();
  await userEvent.click(
    screen.getByRole("combobox", { name: "Transcribe with" }),
  );
  await userEvent.click(screen.getByRole("option", { name: "Online" }));
  expect(
    vi
      .mocked(ipc)
      .mock.calls.filter(
        ([method]) => method.startsWith("models.") && method !== "models.list",
      ),
  ).toEqual([]);
});
it("requires explicit consent to retry a failed pending download", async () => {
  list.models[0].state = "failed";
  list.pending_use = list.models[0].id;
  mount();
  await chooseLocal();
  expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
  expect(ipc).not.toHaveBeenCalledWith("models.use", expect.anything());
  await userEvent.click(
    screen.getByRole("button", { name: "Download and continue" }),
  );
  expect(
    await screen.findByRole("progressbar", { name: "Parakeet download" }),
  ).toBeVisible();
  expect(ipc).toHaveBeenCalledWith("models.use", {
    id: list.models[0].id,
    when_ready: true,
  });
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
