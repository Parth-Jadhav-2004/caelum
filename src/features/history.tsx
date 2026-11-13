import { useDeferredValue, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Search, Trash2, FileText } from "lucide-react";
import { save } from "@tauri-apps/plugin-dialog";
import { ipc } from "@/lib/ipc";
import { Heading, Confirm, action } from "@/components/common";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Transcript } from "@/components/transcript";
import { Skeleton } from "@/components/ui/skeleton";
export function History() {
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search);
  const [deleting, setDeleting] = useState<string | null>(null);
  const client = useQueryClient();
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
  });
  const history = useQuery({
    queryKey: ["history", query],
    queryFn: () => ipc("history", { query }),
    refetchInterval: 3000,
  });
  return (
    <div className="space-y-8">
      <Heading
        eyebrow="Your words, kept locally"
        title="History"
        detail="Completed dictations, never microphone audio. Search the latest 200 matches."
      />
      <p className="text-xs text-muted-foreground">
        {bootstrap.data?.config?.desktop.history_enabled === false
          ? "History saving is off. Existing entries remain manageable."
          : `Completed dictations are saved locally for ${bootstrap.data?.config?.desktop.retention_days ?? 30} days.`}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 flex-1">
          <Search className="absolute top-3 left-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            aria-label="Search your dictations"
            placeholder="Search your dictations…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button
          variant="outline"
          onClick={() => {
            void action(async () => {
              const path = await save({
                defaultPath: "caelum-history.jsonl",
                title:
                  "Export sensitive transcript history · choose a trusted destination",
              });
              if (path) {
                await ipc("history.export", { path });
                return "exported";
              }
            }).then((result) => {
              if (result)
                void action(
                  async () => {},
                  "History exported. Keep this file private.",
                );
            });
          }}
        >
          <Download />
          Export
        </Button>
        <Button
          variant="ghost"
          disabled={!history.data?.length}
          onClick={() => setDeleting("all")}
        >
          <Trash2 />
          Delete all
        </Button>
      </div>
      {history.isPending ? (
        <Skeleton className="h-40" />
      ) : history.isError ? (
        <p role="alert">
          History unavailable. Check local storage permissions. Recording
          remains available.
        </p>
      ) : history.data.length ? (
        <div className="space-y-3">
          {history.data.map((entry) => (
            <Transcript
              key={entry.id}
              entry={entry}
              onDelete={() => setDeleting(entry.id)}
            />
          ))}
        </div>
      ) : (
        <Card className="py-14 text-center shadow-none">
          <FileText className="mx-auto mb-4 size-7 text-muted-foreground" />
          <h2 className="font-medium">
            {query ? "No matching dictations" : "No dictations yet"}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {query
              ? "Try another word or phrase."
              : "Your completed recordings appear here when history saving is on."}
          </p>
        </Card>
      )}
      <Confirm
        open={deleting !== null}
        title={
          deleting === "all"
            ? "Delete all saved dictations?"
            : "Delete this dictation?"
        }
        detail="This permanently deletes local transcripts. Clipboard copies, exports, and lifetime word totals remain."
        confirm="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          await ipc(
            "history.delete",
            deleting === "all" ? {} : { id: deleting! },
          );
          setDeleting(null);
          await client.invalidateQueries({ queryKey: ["history"] });
          await client.invalidateQueries({ queryKey: ["summary"] });
        }}
      />
    </div>
  );
}
