import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { listen } from "@tauri-apps/api/event";
import type { ReactNode } from "react";
import { ipc, type Status } from "@/lib/ipc";
import { useApp } from "@/stores/app";
import { useEngine } from "./use-engine";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
const handlers = new Map<string, (event: { payload: unknown }) => void>();
const stops: ReturnType<typeof vi.fn>[] = [];
const ready: Status = {
  running: true,
  paused: false,
  state: "hidden",
  title: "Ready",
  detail: "Hold to talk",
};
let snapshot: (value: Status) => void;
beforeEach(() => {
  vi.clearAllMocks();
  handlers.clear();
  stops.length = 0;
  useApp.setState({ status: null, engineError: null });
  vi.mocked(listen).mockImplementation(async (name, callback) => {
    handlers.set(
      name as string,
      callback as (event: { payload: unknown }) => void,
    );
    const stop = vi.fn();
    stops.push(stop);
    return stop;
  });
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "status")
      return new Promise<Status>((resolve) => {
        snapshot = resolve;
      });
    return {};
  }) as typeof ipc);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const onQuit = vi.fn();
  return renderHook(() => useEngine(onQuit), { wrapper });
}
it("loads an initial status without waiting for an idle event, then cleans up", async () => {
  const view = mount();
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("status", {}));
  await act(async () => snapshot(ready));
  expect(useApp.getState().status).toEqual(ready);
  view.unmount();
  expect(stops.every((stop) => stop.mock.calls.length === 1)).toBe(true);
});
it("does not overwrite a newer event with a delayed snapshot", async () => {
  mount();
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("status", {}));
  act(() =>
    handlers.get("engine:status")!({
      payload: { ...ready, state: "recording", title: "Recording" },
    }),
  );
  await act(async () => snapshot(ready));
  expect(useApp.getState().status?.state).toBe("recording");
});
it("keeps disconnect state when a stale snapshot finishes and does not replay", async () => {
  mount();
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("status", {}));
  act(() =>
    handlers.get("engine:disconnected")!({ payload: "Engine disconnected" }),
  );
  await act(async () => snapshot(ready));
  expect(useApp.getState().status).toBeNull();
  expect(useApp.getState().engineError).toBe("Engine disconnected");
  expect(
    vi
      .mocked(ipc)
      .mock.calls.every(
        ([method]) => method === "status" || method === "bootstrap",
      ),
  ).toBe(true);
});
