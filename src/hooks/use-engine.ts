import { useEffect } from "react";
import { listen } from "@tauri-apps/api/event";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ipc, errorText, type Status } from "@/lib/ipc";
import { useApp } from "@/stores/app";
export function useEngine(onQuit: () => void) {
  const client = useQueryClient();
  const data = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
    retry: false,
  });
  useEffect(() => {
    let disposed = false;
    const stops: (() => void)[] = [];
    function register<T>(name: string, callback: (payload: T) => void) {
      void listen<T>(name, (e) => callback(e.payload))
        .then((stop) => (disposed ? stop() : stops.push(stop)))
        .catch((e) => toast.error(errorText(e)));
    }
    register<Status>("engine:status", (status) => {
      const previous = useApp.getState().status;
      useApp.getState().setStatus(status);
      if (previous?.state !== status.state) {
        void client.invalidateQueries({ queryKey: ["history"] });
        void client.invalidateQueries({ queryKey: ["summary"] });
      }
    });
    register("engine:disconnected", () => {
      useApp.getState().setStatus(null);
      toast.error("Python engine disconnected. Restart Caelum.", {
        duration: Infinity,
      });
    });
    register<string>("desktop:error", (message) => toast.error(message));
    register("desktop:quit", onQuit);
    register<{ message: string }>("engine:status-error", (value) => {
      useApp.getState().setStatus(null);
      toast.error(value.message, { id: "status-error" });
    });
    return () => {
      disposed = true;
      stops.forEach((stop) => stop());
    };
  }, [client, onQuit]);
  return data;
}
