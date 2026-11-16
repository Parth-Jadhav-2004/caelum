import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export class ErrorBoundary extends Component<
  { children: ReactNode; reload?: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <main
          className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center"
          role="alert"
        >
          <h1 className="text-2xl font-semibold">Something went wrong</h1>
          <p>
            Caelum couldn’t display this screen. Reload the window to try again.
          </p>
          <Button
            onClick={() =>
              (this.props.reload ?? (() => window.location.reload()))()
            }
          >
            Reload window
          </Button>
        </main>
      );
    }
    return this.props.children;
  }
}
