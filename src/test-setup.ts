import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
afterEach(cleanup);
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: () => ({
    matches: false,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
  }),
});
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock;
// Radix Select uses browser pointer/scroll APIs that jsdom does not implement.
HTMLElement.prototype.hasPointerCapture ??= () => false;
HTMLElement.prototype.setPointerCapture ??= () => {};
HTMLElement.prototype.releasePointerCapture ??= () => {};
HTMLElement.prototype.scrollIntoView ??= () => {};
