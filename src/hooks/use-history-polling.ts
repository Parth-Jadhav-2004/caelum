import { useSyncExternalStore } from "react";

function subscribe(notify: () => void) {
  document.addEventListener("visibilitychange", notify);
  return () => document.removeEventListener("visibilitychange", notify);
}

export function useHistoryPolling() {
  const visible = useSyncExternalStore(
    subscribe,
    () => document.visibilityState === "visible",
    () => true,
  );
  return {
    refetchInterval: visible ? 3_000 : 30_000,
    refetchIntervalInBackground: true,
  };
}
