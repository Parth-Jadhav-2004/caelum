import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { dayLabel, TranscriptList } from "./transcript";
import { TooltipProvider } from "./ui/tooltip";
it("labels days in local time across month and year boundaries", () => {
  const now = new Date(2026, 0, 1, 12);
  expect(dayLabel(new Date(2026, 0, 1, 1).toISOString(), now)).toBe("Today");
  expect(dayLabel(new Date(2025, 11, 31, 23).toISOString(), now)).toBe(
    "Yesterday",
  );
  expect(dayLabel(new Date(2025, 11, 30, 23).toISOString(), now)).not.toBe(
    "Yesterday",
  );
});
it("groups transcripts by day and reveals metadata only on selection", async () => {
  render(
    <TooltipProvider>
      <TranscriptList
        entries={[
          {
            id: "1",
            created_at: new Date().toISOString(),
            final_transcript: "My own words",
            word_count: 3,
            duration_ms: 1500,
            refined: 0,
            copied: 0,
          },
        ]}
      />
    </TooltipProvider>,
  );
  expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
  expect(screen.queryByText("3 words")).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Show dictation details" }),
  );
  expect(screen.getByText("3 words")).toBeInTheDocument();
  expect(screen.getByText("Raw")).toBeInTheDocument();
  await userEvent.keyboard("{Enter}");
  expect(screen.queryByText("3 words")).not.toBeInTheDocument();
});

it("exposes selectable transcript words as text, independently of the details button", () => {
  render(
    <TooltipProvider>
      <TranscriptList
        entries={[
          {
            id: "1",
            created_at: new Date().toISOString(),
            final_transcript: "Words a screen reader can read",
            word_count: 7,
            duration_ms: 1000,
            refined: 1,
            copied: 0,
          },
        ]}
      />
    </TooltipProvider>,
  );
  expect(screen.getByRole("paragraph")).toHaveTextContent(
    "Words a screen reader can read",
  );
  expect(screen.getByRole("paragraph")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Show dictation details" }),
  ).not.toHaveTextContent("Words a screen reader can read");
});
it("keeps the Raw explanation visible with its metadata", async () => {
  render(
    <TooltipProvider>
      <TranscriptList
        entries={[
          {
            id: "1",
            created_at: new Date().toISOString(),
            final_transcript: "Raw words",
            word_count: 2,
            duration_ms: 1000,
            refined: 0,
            copied: 0,
          },
        ]}
      />
    </TooltipProvider>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Show dictation details" }),
  );
  expect(
    screen.getByText(/Text cleanup was skipped or unavailable/),
  ).toBeVisible();
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
});
