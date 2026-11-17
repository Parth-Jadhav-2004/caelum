import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export class ErrorBoundary extends Component<
  { children: ReactNode; reload?: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Caelum screen crashed", error, info);
  }

  render() {
    if (this.state.failed) {
      return (
        <main
          className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center"
          role="alert"
        >
          <h1 className="text-title font-semibold">Something went wrong</h1>
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
