import { act, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { History } from "./history";
import { Dashboard } from "./dashboard";
import { ipc } from "@/lib/ipc";
import { testConfig } from "@/test-config";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it.each(["history", "dashboard"])(
  "pauses %s history polling when hidden and immediately refetches when visible",
  async (page) => {
    vi.useFakeTimers();
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("visible");
    vi.mocked(ipc).mockImplementation((async (method: string) => {
      if (method === "history" || method === "devices") return [];
      if (method === "bootstrap") return { config: testConfig };
      if (method === "summary") return { activity: {}, daily: {} };
      return {};
    }) as typeof ipc);
    vi.mocked(ipc).mockClear();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        {page === "history" ? <History /> : <Dashboard config={testConfig} />}
      </QueryClientProvider>,
    );
    const count = () =>
      vi.mocked(ipc).mock.calls.filter(([method]) => method === "history")
        .length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(count()).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(count()).toBe(2);
    act(() => {
      visibility.mockReturnValue("hidden");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29999);
    });
    expect(count()).toBe(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(count()).toBe(2);
    act(() => {
      visibility.mockReturnValue("visible");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(count()).toBe(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(count()).toBe(4);
    view.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(count()).toBe(4);
    client.clear();
  },
);
