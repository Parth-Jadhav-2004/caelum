import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, it, expect, beforeEach } from "vitest";
import { Setup } from "./setup";
import { ipc, type Config } from "@/lib/ipc";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async () => () => {}),
}));
const config = {
  app: { hotkey: "SUPER + ALT + V", microphone: null },
  stt: { key_env: "GROQ_API_KEY", base_url: "https://api.groq.com/openai/v1" },
  cleanup: {
    model: "",
    base_url: "https://api.groq.com/openai/v1",
    key_env: "GROQ_API_KEY",
  },
} as Config;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return {
        config,
        privacy: "Audio goes to your provider.",
        credentials: { GROQ_API_KEY: "key missing" },
      };
    if (method === "devices") return [];
    if (method === "shortcut.check") return "Shortcut is available.";
    if (method === "setup.validate") return { storage: {} };
    return { ok: true };
  }) as typeof ipc);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Setup config={config} commit={vi.fn()} />
    </QueryClientProvider>,
  );
}
it("requires consent and validates a staged secret before advancing", async () => {
  mount();
  const user = userEvent.setup();
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  await user.type(screen.getByLabelText("Provider API key"), "test-only");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("button", { name: "Test microphone" });
  expect(ipc).toHaveBeenCalledWith("setup.validate", {
    consent: true,
    keys: { GROQ_API_KEY: "test-only" },
  });
  expect(ipc).not.toHaveBeenCalledWith("credentials.store", expect.anything());
});
it("keeps microphone and practice steps gated on real service results", async () => {
  mount();
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await user.click(
    await screen.findByRole("button", { name: "Test microphone" }),
  );
  await user.click(await screen.findByRole("button", { name: "Continue" }));
  await user.click(await screen.findByRole("button", { name: "Continue" }));
  const record = await screen.findByRole("button", { name: "Record practice" });
  expect(record).toBeDisabled();
  expect(ipc).toHaveBeenCalledWith("microphone.test", {});
  expect(ipc).toHaveBeenCalledWith("shortcut.check", {});
  expect(ipc).not.toHaveBeenCalledWith("practice", expect.anything());
});
it("cancels an in-flight validation without advancing", async () => {
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap") return { credentials: {}, privacy: "" };
    if (method === "setup.validate") return new Promise(() => {});
    return { ok: true };
  }) as typeof ipc);
  mount();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Cancel test" }),
  );
  await waitFor(() => expect(ipc).toHaveBeenCalledWith("sample.cancel", {}));
  expect(screen.getByText("Step 1 of 4 · Provider")).toBeInTheDocument();
});
