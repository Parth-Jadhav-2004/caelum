import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ipc, IpcError, errorText } from "./ipc";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
it("rejects invalid requests before sending anything", async () => {
  await expect(
    ipc("control", { action: "unsupported" as "start" }),
  ).rejects.toMatchObject({ code: "invalid_request" });
  expect(invoke).not.toHaveBeenCalled();
});
it("rejects malformed results and never replays an operation", async () => {
  vi.mocked(invoke).mockResolvedValue({ ok: "yes" });
  await expect(ipc("control", { action: "start" })).rejects.toMatchObject({
    code: "protocol",
  });
  expect(invoke).toHaveBeenCalledTimes(1);
});
it("retains typed errors and separates blocked from transient failures", async () => {
  for (const [code, retryable] of [
    ["permission", false],
    ["rate_limit", true],
  ] as const) {
    vi.mocked(invoke).mockRejectedValue({
      code,
      retryable,
      message: "A sanitized message",
    });
    await expect(ipc("providers.check", {})).rejects.toMatchObject({
      code,
      retryable,
    });
  }
  expect(errorText(new IpcError("timeout", "Outcome unknown", false))).toBe(
    "Outcome unknown",
  );
});
it("accepts valid data while rejecting invalid nested values", async () => {
  vi.mocked(invoke).mockResolvedValue([{ label: "Default", value: null }]);
  expect(await ipc("devices", {})).toEqual([{ label: "Default", value: null }]);
  vi.mocked(invoke).mockResolvedValue([{ label: "Default", value: true }]);
  await expect(ipc("devices", {})).rejects.toMatchObject({ code: "protocol" });
});
