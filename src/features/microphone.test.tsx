import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Settings } from "./settings";
import { testConfig } from "@/test-config";
import { ipc } from "@/lib/ipc";
const audio = vi.hoisted(() => ({
  emit: (level: number) => {
    void level;
  },
}));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (_name: string, callback: (event: unknown) => void) => {
    audio.emit = (level) =>
      callback({ event: "engine:microphone", id: 1, payload: { level } });
    return () => {
      audio.emit = () => {};
    };
  }),
}));
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap") return { credentials: {}, autostart: false };
    if (method === "devices")
      return [{ value: "usb", label: "USB microphone" }];
    if (method === "microphone.test") return new Promise(() => {});
    return { ok: true };
  }) as typeof ipc);
});
function mount(commit?: (next: typeof testConfig) => Promise<void>) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings
          config={{
            ...testConfig,
            app: { ...testConfig.app, microphone: "usb" },
          }}
          change={vi.fn()}
          saveState="Saved"
          commit={commit}
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
it("shows the named device and live meter, stops locally, closes and restores focus", async () => {
  mount();
  const trigger = screen.getByRole("button", { name: "Test mic" });
  await userEvent.click(trigger);
  expect(
    await screen.findByRole("dialog", { name: "Test your microphone" }),
  ).toBeInTheDocument();
  expect(
    await screen.findByText("USB microphone", { selector: "p" }),
  ).toBeInTheDocument();
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("microphone.test", {}));
  act(() => audio.emit(0.62));
  expect(
    screen.getByRole("meter", { name: "Microphone level" }),
  ).toHaveAttribute("aria-valuenow", "62");
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(ipc).toHaveBeenCalledWith("sample.cancel", {});
  expect(screen.getByRole("status")).toHaveTextContent("Stopped");
  await userEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("saves the selected microphone before starting the test", async () => {
  let finishSave: () => void = () => {};
  const commit = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finishSave = resolve;
      }),
  );
  mount(commit);
  await userEvent.click(screen.getByRole("button", { name: "Test mic" }));
  expect(commit).toHaveBeenCalledWith(
    expect.objectContaining({
      app: expect.objectContaining({ microphone: "usb" }),
    }),
  );
  expect(ipc).not.toHaveBeenCalledWith("microphone.test", {});
  await act(async () => finishSave());
  await screen.findByRole("dialog", { name: "Test your microphone" });
  expect(ipc).toHaveBeenCalledWith("microphone.test", {});
});

it("ignores a stopped test's delayed success, retries, and cancels on Escape", async () => {
  let finishTest: (result: { ok: boolean }) => void = () => {};
  const original = vi.mocked(ipc).getMockImplementation()!;
  vi.mocked(ipc).mockImplementation(((method, params) =>
    method === "microphone.test"
      ? new Promise((resolve) => {
          finishTest = resolve;
        })
      : original(method, params)) as typeof ipc);
  mount();
  const trigger = screen.getByRole("button", { name: "Test mic" });
  await userEvent.click(trigger);
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  await act(async () => finishTest({ ok: true }));
  expect(screen.getByRole("status")).toHaveTextContent("Stopped");
  await userEvent.click(screen.getByRole("button", { name: "Test again" }));
  expect(screen.getByRole("status")).toHaveTextContent("Listening…");
  expect(
    vi
      .mocked(ipc)
      .mock.calls.filter(([method]) => method === "microphone.test"),
  ).toHaveLength(2);
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(ipc).toHaveBeenCalledWith("sample.cancel", {});
});

it.each(["cancel", "capture"] as const)(
  "waits for both cancellation and capture teardown when %s settles first",
  async (first) => {
    const original = vi.mocked(ipc).getMockImplementation()!;
    let finishCapture: () => void = () => {};
    let acknowledgeCancel: () => void = () => {};
    vi.mocked(ipc).mockImplementation(((method, params) => {
      if (method === "microphone.test")
        return new Promise<{ ok: boolean }>((resolve) => {
          finishCapture = () => resolve({ ok: true });
        });
      if (method === "sample.cancel")
        return new Promise<{ ok: boolean }>((resolve) => {
          acknowledgeCancel = () => resolve({ ok: true });
        });
      return original(method, params);
    }) as typeof ipc);
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Test mic" }));
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    const retry = screen.getByRole("button", { name: "Test again" });
    expect(retry).toBeDisabled();
    await act(async () => {
      if (first === "cancel") acknowledgeCancel();
      else finishCapture();
    });
    expect(retry).toBeDisabled();
    await userEvent.click(retry);
    expect(
      vi
        .mocked(ipc)
        .mock.calls.filter(([method]) => method === "microphone.test"),
    ).toHaveLength(1);
    await act(async () => {
      if (first === "cancel") finishCapture();
      else acknowledgeCancel();
    });
    expect(retry).toBeEnabled();
    await userEvent.click(retry);
    expect(
      vi
        .mocked(ipc)
        .mock.calls.filter(([method]) => method === "microphone.test"),
    ).toHaveLength(2);
    expect(
      vi
        .mocked(ipc)
        .mock.calls.filter(([method]) => method === "sample.cancel"),
    ).toHaveLength(1);
    await act(async () => finishCapture());
  },
);
