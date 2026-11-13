import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Dashboard, DeviceSelect, Waveform } from "./dashboard";
import { History } from "./history";
import { Shortcut } from "./settings";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useApp } from "@/stores/app";
import { ipc, type Config } from "@/lib/ipc";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));
const config = {
  app: {
    hotkey: "SUPER + ALT + V",
    microphone: "missing",
    recording_mode: "hold",
  },
  desktop: { history_enabled: true },
} as Config;
function mount(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  useApp.setState({
    status: {
      running: true,
      state: "hidden",
      title: "Ready",
      detail: "Hold your shortcut.",
      paused: false,
    },
    page: "home",
  });
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "devices") return [];
    if (method === "history") return [];
    if (method === "summary") return { daily: {}, activity: {} };
    return { ok: true };
  }) as typeof ipc);
});
describe("recording controls", () => {
  it("starts and finishes recording through the typed boundary", async () => {
    const user = userEvent.setup();
    mount(<Dashboard config={config} onMicrophone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Record" }));
    expect(ipc).toHaveBeenCalledWith("control", { action: "start" });
    useApp.setState({
      status: {
        running: true,
        state: "recording",
        title: "Recording",
        detail: "Release to stop.",
        paused: false,
      },
    });
    await user.click(
      await screen.findByRole("button", { name: "Finish recording" }),
    );
    expect(ipc).toHaveBeenCalledWith("control", { action: "stop" });
  });
  it("keeps retry audio protected from a new recording", async () => {
    useApp.setState({
      status: {
        running: true,
        state: "error",
        title: "Awaiting retry",
        detail: "Audio in memory.",
        paused: false,
        pending_audio: true,
      },
    });
    mount(<Dashboard config={config} onMicrophone={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Record" })).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: "Retry dictation" }),
    );
    expect(ipc).toHaveBeenCalledWith("control", { action: "retry" });
    expect(
      screen.getByRole("button", { name: "Discard recording" }),
    ).toBeEnabled();
  });
  it("uses only supplied microphone levels", () => {
    const { container } = render(<Waveform values={[0, 0.5, 1]} />);
    expect(
      [...container.querySelectorAll("span")].map((e) => e.style.height),
    ).toEqual(["4px", "27px", "50px"]);
  });
  it("preserves a disconnected microphone preference", () => {
    mount(<DeviceSelect value="missing" onChange={vi.fn()} />);
    expect(
      screen.getByRole("combobox", { name: "Microphone" }),
    ).toHaveTextContent("configured, not detected");
  });
});
it("captures modified shortcuts and permits Escape cancellation", async () => {
  const change = vi.fn();
  mount(<Shortcut value="SUPER + V" change={change} />);
  const button = screen.getByRole("button", { name: "Recording shortcut" });
  await userEvent.click(button);
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(change).toHaveBeenCalledWith("CTRL + K");
  await userEvent.click(button);
  await userEvent.keyboard("{Escape}");
  expect(button).toHaveTextContent("SUPER + V");
});
it("requires confirmation before deleting transcripts", async () => {
  vi.mocked(ipc).mockImplementation(async (method) =>
    method === "history"
      ? [
          {
            id: "1",
            created_at: "2026-11-13",
            final_transcript: "Private words",
            duration_ms: 1000,
            word_count: 2,
            refined: 1,
            copied: 0,
          },
        ]
      : ({ ok: true } as never),
  );
  mount(<History />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Delete dictation" }),
  );
  expect(ipc).not.toHaveBeenCalledWith("history.delete", expect.anything());
  expect(screen.getByRole("alertdialog")).toHaveTextContent(
    "Clipboard copies, exports, and lifetime word totals remain",
  );
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
it("keeps native capture on the global shortcut so text targets the original app", () => {
  useApp.setState({
    status: {
      running: true,
      backend: "hyprland",
      state: "hidden",
      title: "Ready",
      detail: "Hold your shortcut.",
      paused: false,
    },
  });
  mount(<Dashboard config={config} onMicrophone={vi.fn()} />);
  expect(
    screen.getByRole("button", { name: "Use your recording shortcut" }),
  ).toBeDisabled();
});
