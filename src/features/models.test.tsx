import { act, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { ModelPicker } from "./models";
import { ipc, type ModelList, type SpeechModel } from "@/lib/ipc";
import { testModels } from "@/test-models";
import { useDownloads } from "@/stores/models";
import { useApp } from "@/stores/app";
import { TooltipProvider } from "@/components/ui/tooltip";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let data: ModelList;
beforeEach(() => {
  data = structuredClone(testModels);
  data.models = [data.models[0]];
  useDownloads.setState({ progress: {}, announcement: "" });
  useApp.setState({ status: null });
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) =>
    method === "models.list" ? data : { ok: true }) as typeof ipc);
});
function mount(onSelect?: (id: string) => void, beforeUse?: () => Promise<void>) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TooltipProvider>
        <ModelPicker
          onSelect={onSelect}
          beforeUse={beforeUse}
          selected={onSelect ? "parakeet-v3" : undefined}
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
it.each<[SpeechModel["state"], string]>([
  ["not_installed", "Download 671 MB"],
  ["queued", "Waiting…"],
  ["downloading", "Pause"],
  ["paused", "Resume"],
  ["verifying", "Checking files…"],
  ["installing", "Checking files…"],
  ["installed", "Use"],
  ["failed", "Try again"],
])("renders %s calmly", async (state, label) => {
  data.models[0].state = state;
  mount();
  expect(
    (await screen.findAllByText(label, { exact: true })).length,
  ).toBeGreaterThan(0);
});
it("shows in-use and loading states without offering removal", async () => {
  data.models[0].state = "installed";
  data.models[0].in_use = true;
  useApp.setState({
    status: {
      running: true,
      paused: false,
      title: "",
      detail: "",
      state: "hidden",
      engine: {
        kind: "local",
        model: "parakeet-v3",
        state: "loading",
        message: "",
      },
    },
  });
  mount();
  expect(await screen.findByText("Getting ready…")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Actions for Parakeet" }),
  );
  expect(
    screen.getByRole("menuitem", { name: "Check files" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("menuitem", { name: "Remove" }),
  ).not.toBeInTheDocument();
});
it("has accessible progress and state-only live announcements", async () => {
  Object.assign(data.models[0], {
    state: "downloading",
    received_bytes: 212000000,
    total_bytes: 671000000,
  });
  mount();
  const progress = await screen.findByRole("progressbar");
  expect(progress).toHaveAttribute("aria-valuetext", "212 megabytes of 671");
  expect(progress).toHaveAttribute("aria-valuenow", "32");
  act(() =>
    useDownloads.getState().update({
      id: "parakeet-v3",
      state: "paused",
      received_bytes: 212000000,
      total_bytes: 671000000,
      bytes_per_sec: 0,
      eta_seconds: null,
      error: null,
    }),
  );
  expect(screen.getByText("Download paused")).toHaveAttribute(
    "aria-live",
    "polite",
  );
});
it("supports arrows, Space and Enter in the model radiogroup", async () => {
  data = structuredClone(testModels);
  const select = vi.fn();
  mount(select);
  const first = await screen.findByRole("radio", { name: "Parakeet" });
  first.focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(screen.getByRole("radio", { name: "Small and quick" })).toHaveFocus();
  expect(select).toHaveBeenCalledWith("parakeet-110m");
  await userEvent.keyboard("{Enter}");
  expect(select).toHaveBeenLastCalledWith("parakeet-110m");
});
it("exposes hidden models but disables hardware- and component-blocked downloads", async () => {
  data = structuredClone(testModels);
  data.models[2].visible = false;
  data.models[2].disabled_reason = "Needs 8 GB memory";
  data.models[3].disabled_reason = "Needs an extra component.";
  mount();
  await userEvent.click(
    await screen.findByRole("button", { name: "Show all models (1)" }),
  );
  expect(screen.getByText("Needs 8 GB memory")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Download 1.7 GB" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Download 1.6 GB" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "How to add it" }),
  ).toBeInTheDocument();
});
it("keeps jargon out of primary model views", async () => {
  data = structuredClone(testModels);
  const { container } = mount();
  await screen.findByRole("radiogroup");
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("details").forEach((node) => node.remove());
  expect(clone.textContent).not.toMatch(/WER|int8|ONNX|sherpa|CTranslate/);
});

it("flushes pending settings before applying a model", async () => {
  data.models[0].state = "installed";
  const order: string[] = [];
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "models.list") return data;
    if (method === "models.use") order.push("use");
    return { ok: true };
  }) as typeof ipc);
  mount(undefined, async () => { order.push("flush"); });
  await userEvent.click(await screen.findByRole("button", { name: "Use" }));
  await waitFor(() => expect(order).toEqual(["flush", "use"]));
});

it("has no detectable semantic accessibility violations in the local picker", async () => {
  data = structuredClone(testModels);
  const { container } = mount();
  await screen.findByRole("radiogroup");
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
});
