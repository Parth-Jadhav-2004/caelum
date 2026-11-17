import { render, act } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ThemeProvider, useTheme } from "./theme";

function Current() {
  return <output>{useTheme().theme}</output>;
}
it("maps legacy palettes to Caelum while preserving appearance", () => {
  const view = render(
    <ThemeProvider theme="light">
      <Current />
    </ThemeProvider>,
  );
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
  expect(document.documentElement).not.toHaveClass("dark");
  view.rerender(
    <ThemeProvider theme="light" colorTheme="ocean">
      <Current />
    </ThemeProvider>,
  );
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
  expect(view.getByText("light")).toBeInTheDocument();
  view.rerender(
    <ThemeProvider theme="dark" colorTheme="unrecognized">
      <Current />
    </ThemeProvider>,
  );
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
  expect(document.documentElement).toHaveClass("dark");
});
it("follows system appearance changes and removes its listener", () => {
  let listener: () => void = () => {};
  const media = {
    matches: false,
    addEventListener: vi.fn((_event, fn) => {
      listener = fn;
    }),
    removeEventListener: vi.fn(),
  };
  const spy = vi
    .spyOn(window, "matchMedia")
    .mockReturnValue(media as unknown as MediaQueryList);
  const view = render(
    <ThemeProvider theme="system" colorTheme="iris">
      <Current />
    </ThemeProvider>,
  );
  expect(view.getByText("light")).toBeInTheDocument();
  act(() => {
    media.matches = true;
    listener();
  });
  expect(view.getByText("dark")).toBeInTheDocument();
  expect(document.documentElement.dataset.colorTheme).toBe("caelum");
  view.unmount();
  expect(media.removeEventListener).toHaveBeenCalledWith("change", listener);
  spy.mockRestore();
});

it.each(["caelum-iris", "caelum-ochre"])(
  "restores saved %s independently of appearance",
  (accent) => {
    render(
      <ThemeProvider theme="dark" colorTheme={accent}>
        <Current />
      </ThemeProvider>,
    );
    expect(document.documentElement.dataset.colorTheme).toBe(accent);
    expect(document.documentElement).toHaveClass("dark");
  },
);
