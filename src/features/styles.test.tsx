import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { testConfig } from "@/test-config";
import { Styles } from "./styles";

it("keeps online refinement settings inactive for local transcription", () => {
  const config = { ...testConfig, stt: { ...testConfig.stt, engine: "local" },
    cleanup: { ...testConfig.cleanup, model: "saved-online-model", style: "email" } };
  const change = vi.fn();
  render(<Styles config={config} change={change} saveState="Saved" />);
  expect(screen.getByRole("button", { name: "Transcription settings" })).toBeVisible();
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
});

it("changes only the style for an existing custom online model", async () => {
  const config = { ...testConfig, cleanup: { ...testConfig.cleanup,
    base_url: "https://example.test/v1", model: "editor", reasoning_effort: "" } };
  const change = vi.fn();
  render(<Styles config={config} change={change} saveState="Saved" />);
  await userEvent.click(screen.getByRole("radio", { name: "Code" }));
  expect(change).toHaveBeenCalledWith({ ...config, cleanup: { ...config.cleanup, style: "code" } });
});
