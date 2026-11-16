import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { Settings } from "./settings";
import { ipc } from "@/lib/ipc";
import { testConfig } from "@/test-config";
import { useApp } from "@/stores/app";
vi.mock("@/lib/ipc", () => ({ ipc: vi.fn(), errorText: String }));

function mount(storage: string | { description: string; storage: string }) {
  vi.mocked(ipc).mockImplementation((async (method: string) => {
    if (method === "bootstrap")
      return { credentials: { GROQ_API_KEY: storage } };
    if (method === "devices") return [];
    return false;
  }) as typeof ipc);
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <Settings config={testConfig} change={vi.fn()} saveState="Saved" />
    </QueryClientProvider>,
  );
}
describe("credential storage warning", () => {
  it("warns for unencrypted files and links to key management", async () => {
    mount({ description: "Saved locally", storage: "file" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API keys are stored unencrypted",
    );
    await userEvent.click(screen.getByRole("button", { name: "Manage keys" }));
    expect(useApp.getState().page).toBe("setup");
  });
  it("supports legacy unencrypted descriptions", async () => {
    mount("key saved in private file (not encrypted)");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API keys are stored unencrypted",
    );
  });
  it.each([
    { description: "not encrypted is only display text", storage: "keyring" },
    "key saved in desktop keyring",
    "key present in environment",
    "key missing; open setup to add a key",
  ])("does not warn for %s", async (storage) => {
    mount(storage);
    await screen.findByRole("combobox", { name: "Microphone" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
