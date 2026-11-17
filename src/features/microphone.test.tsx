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
it("shows the named device and live meter, stops locally, closes and restores focus", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <Settings
          config={{
            ...testConfig,
            app: { ...testConfig.app, microphone: "usb" },
          }}
          change={vi.fn()}
          saveState="Saved"
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
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
