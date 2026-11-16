import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ErrorBoundary } from "./error-boundary";

it("renders children normally", () => {
  render(
    <ErrorBoundary>
      <p>Ready to record</p>
    </ErrorBoundary>,
  );
  expect(screen.getByText("Ready to record")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("contains a component crash and offers a reload", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const reload = vi.fn();
  function Broken(): never {
    throw new Error("sensitive internal detail");
  }
  try {
    render(
      <ErrorBoundary reload={reload}>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(
      screen.queryByText("sensitive internal detail"),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Reload window" }),
    );
    expect(reload).toHaveBeenCalledOnce();
  } finally {
    log.mockRestore();
  }
});
