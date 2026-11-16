import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

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
  const client = useQueryClient();
  useEffect(() => {
    let wasVisible = document.visibilityState === "visible";
    const onVisibilityChange = () => {
      const isVisible = document.visibilityState === "visible";
      if (isVisible && !wasVisible) {
        void client.refetchQueries({ queryKey: ["history"], type: "active" });
      }
      wasVisible = isVisible;
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [client]);
  return { refetchInterval: visible ? 3_000 : (false as const) };
}
