import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { UsageCalendar } from "./dashboard";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 16, 12));
});
afterEach(() => vi.useRealTimers());
function day(date: string) {
  return screen.getByRole("button", { name: new RegExp(`^${date}:`) });
}
it("moves by day/week and selects with Enter, then clears with Escape", async () => {
  const user = userEvent.setup();
  render(<UsageCalendar activity={{ "2026-11-09": 123 }} />);
  day("2026-11-16").focus();
  await user.keyboard("{ArrowUp}");
  expect(day("2026-11-09")).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(day("2026-11-09")).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("status")).toHaveTextContent("2026-11-09: 123 words");
  await user.keyboard("{ArrowLeft}{ArrowRight}{ArrowDown}");
  expect(day("2026-11-16")).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(day("2026-11-09")).toHaveAttribute("aria-pressed", "false");
  expect(day("2026-11-16")).toHaveFocus();
});
it("supports week boundaries, crosses months, and prevents future focus", async () => {
  const user = userEvent.setup();
  render(<UsageCalendar activity={{}} />);
  day("2026-11-16").focus();
  await user.keyboard("{Home}");
  expect(day("2026-11-15")).toHaveFocus();
  await user.keyboard("{End}");
  expect(day("2026-11-16")).toHaveFocus();
  await user.keyboard("{ArrowRight}{ArrowDown}");
  expect(day("2026-11-16")).toHaveFocus();
  day("2026-11-01").focus();
  await user.keyboard("{ArrowLeft}");
  expect(day("2026-10-31")).toHaveFocus();
  await user.keyboard("{Home}{End}");
  expect(day("2026-10-31")).toHaveFocus();
  await user.keyboard("{ArrowRight}");
  expect(day("2026-11-01")).toHaveFocus();
  const buttons = within(
    screen.getByRole("group", { name: "Daily usage calendar" }),
  ).getAllByRole("button");
  expect(buttons.filter((button) => button.tabIndex === 0)).toEqual([
    day("2026-11-01"),
  ]);
});
it("keeps a calendar tab stop after changing month with the controls", async () => {
  const user = userEvent.setup();
  render(<UsageCalendar activity={{}} />);
  await user.click(screen.getByRole("button", { name: "Previous month" }));
  expect(day("2026-10-01")).toHaveAttribute("tabindex", "0");
  await user.click(screen.getByRole("button", { name: "Next month" }));
  expect(day("2026-11-01")).toHaveAttribute("tabindex", "0");
});
