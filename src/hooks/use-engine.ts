import { useEffect } from "react";
import { listen } from "@tauri-apps/api/event";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { validStatus } from "@/lib/contracts";
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
      return listen<T>(name, (e) => {
        try {
          callback(e.payload);
        } catch (error) {
          useApp.getState().setStatus(null);
          useApp.getState().setEngineError(errorText(error));
          toast.error(errorText(error), { id: "protocol-error" });
        }
      })
        .then((stop) => {
          if (disposed) {
            stop();
            return false;
          }
          stops.push(stop);
          return true;
        })
        .catch((e) => {
          toast.error(errorText(e));
          return false;
        });
    }
    let statusRevision = 0;
    function applyStatus(status: Status) {
      if (!validStatus(status))
        throw new Error("Invalid engine status. Restart Caelum.");
      const previous = useApp.getState().status;
      useApp.getState().setStatus(status);
      useApp.getState().setEngineError(null);
      if (previous?.state !== status.state) {
        void client.invalidateQueries({ queryKey: ["history"] });
        void client.invalidateQueries({ queryKey: ["summary"] });
      }
    }
    // Subscribe before taking a snapshot. Do not overwrite a newer event with a
    // delayed read, and do not depend on repeated unchanged idle events.
    void register<Status>("engine:status", (status) => {
      statusRevision++;
      applyStatus(status);
    }).then(async (active) => {
      if (!active) return;
      const revision = statusRevision;
      try {
        const snapshot = await ipc("status", {});
        if (!disposed && revision === statusRevision) applyStatus(snapshot);
      } catch (error) {
        if (!disposed && revision === statusRevision) {
          useApp.getState().setStatus(null);
          useApp.getState().setEngineError(errorText(error));
        }
      }
    });
    register<unknown>("engine:disconnected", (error) => {
      statusRevision++;
      useApp.getState().setStatus(null);
      useApp.getState().setEngineError(errorText(error));
      toast.error(errorText(error), {
        duration: Infinity,
        id: "engine-disconnected",
      });
    });
    register<unknown>("desktop:error", (error) =>
      toast.error(errorText(error)),
    );
    register("desktop:quit", onQuit);
    register<{ message: string }>("engine:status-error", (value) => {
      statusRevision++;
      useApp.getState().setStatus(null);
      useApp.getState().setEngineError(value.message);
      toast.error(value.message, { id: "status-error" });
    });
    return () => {
      disposed = true;
      stops.forEach((stop) => stop());
    };
  }, [client, onQuit]);
  return data;
}
