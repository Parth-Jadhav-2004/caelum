import { useQuery } from "@tanstack/react-query";
import { ipc } from "@/lib/ipc";
import { useDownloads } from "@/stores/models";

export function useModels() {
  const query = useQuery({
    queryKey: ["models"],
    queryFn: () => ipc("models.list", {}),
    refetchInterval: 5000,
  });
  const progress = useDownloads((s) => s.progress);
  const models = (query.data?.models ?? []).map((model) => {
    const event = progress[model.id];
    // A fresh snapshot owns installed / removed state. Active events are merged
    // without waiting for another IPC round trip.
    if (!event || event.state === "ready" || event.state === "cancelled")
      return model;
    if (model.state === "installed" && event.state !== "verifying")
      return model;
    return { ...model, ...event };
  });
  return { ...query, models };
}
