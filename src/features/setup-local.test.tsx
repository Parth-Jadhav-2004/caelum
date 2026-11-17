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
    if (method === "models.download") {
      list.models[0].state = "downloading";
      return { ok: true };
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
async function goToPractice() {
  await userEvent.click(
    await screen.findByRole("button", { name: "Download and continue" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Test microphone" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue" }),
  );
  await screen.findByRole("heading", { name: "Try dictation" });
}
it("chooses local, downloads in the background, and practices without upload consent", async () => {
  const client = mount();
  await waitFor(() =>
    expect(
      screen.getByRole("radio", { name: /On this computer/ }),
    ).toBeChecked(),
  );
  await goToPractice();
  expect(ipc).toHaveBeenCalledWith("models.use", { id: "parakeet-v3" });
  expect(
    screen.getByText("Your practice recording stays on this computer."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Record practice" }),
  ).toBeDisabled();
  expect(screen.getByText("Almost ready")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Wait here" }));
  list.models[0].state = "installed";
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["models"] });
  });
  await userEvent.click(
    await screen.findByRole("button", { name: "Record practice" }),
  );
  expect(ipc).toHaveBeenCalledWith("practice", { consent: false });
  expect(await screen.findByText("Hello Caelum")).toBeInTheDocument();
});
it("finishes setup while a model continues downloading", async () => {
  mount();
  await goToPractice();
  await userEvent.click(screen.getByRole("button", { name: "Skip for now" }));
  expect(ipc).toHaveBeenCalledWith("setup.finish", { skip_practice: true });
  expect(ipc).not.toHaveBeenCalledWith("models.cancel", expect.anything());
});
it("recommends Online plainly for Hindi", async () => {
  list.hardware.language = "hi";
  list.recommended = {
    id: null,
    reason_code: "indian_language",
    reason_text:
      "On-device models aren't good at Hindi yet. Online works best for now.",
  };
  mount();
  expect(await screen.findByRole("radio", { name: /^Online/ })).toBeChecked();
  expect(
    await screen.findByText(list.recommended.reason_text),
  ).toBeInTheDocument();
});
it("offers retry, Online, and skip after download failure", async () => {
  const client = mount();
  await goToPractice();
  list.models[0].state = "failed";
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["models"] });
  });
  expect(
    await screen.findByText("Couldn't download Parakeet"),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Use Online instead" }),
  ).toBeEnabled();
  expect(screen.getByRole("button", { name: "Skip for now" })).toBeEnabled();
});
