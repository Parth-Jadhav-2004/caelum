import { useHistoryPolling } from "@/hooks/use-history-polling";
import {
  memo,
  useDeferredValue,
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
} from "react";
import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Download, Search, Trash2, X, Ellipsis } from "lucide-react";
import { save } from "@tauri-apps/plugin-dialog";
import { ipc } from "@/lib/ipc";
import { Heading, Confirm, action } from "@/components/common";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  TranscriptList,
  Transcript,
  TranscriptDetails,
} from "@/components/transcript";
import { useApp } from "@/stores/app";
import { Skeleton } from "@/components/ui/skeleton";
export const History = memo(function History({
  compact = false,
}: {
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const navigate = useApp((s) => s.navigate);
  const [selectedId, setSelectedId] = useState<string>();
  const menu = useRef<HTMLDetailsElement>(null);
  const detail = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    if (selectedId) detail.current?.focus({ preventScroll: true });
  }, [selectedId]);
  useEffect(() => {
    const outside = (e: PointerEvent) => {
      if (menu.current && !menu.current.contains(e.target as Node))
        menu.current.open = false;
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  useEffect(() => {
    if (compact) return;
    const focus = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, [compact]);
  const historyPolling = useHistoryPolling();
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
    placeholderData: keepPreviousData,
    ...historyPolling,
  });
  const selected = history.data?.find((entry) => entry.id === selectedId);
  function closeDetails() {
    setSelectedId(undefined);
    document.getElementById(`dictation-details-${selectedId}`)?.focus();
  }
  return (
    <div className="space-y-8">
      {!compact && (
        <>
          <Heading title="History" />
          <p className="text-meta text-muted-foreground">
            {bootstrap.data?.config?.desktop.history_enabled === false
              ? "History saving is off"
              : bootstrap.data?.config?.desktop.history_forever
                ? "Kept forever"
                : `Kept ${bootstrap.data?.config?.desktop.retention_days ?? 30} days`}
          </p>
        </>
      )}
      {compact && (
        <div className="flex items-center justify-between">
          <h2 className="text-section font-medium">Latest dictations</h2>
          <Button variant="ghost" size="sm" onClick={() => navigate("history")}>
            See all
          </Button>
        </div>
      )}
      {!compact && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-48 flex-1">
            <Search className="absolute top-3 left-3 size-4 text-muted-foreground" />
            <Input
              ref={input}
              className="pl-9"
              aria-label="Search your dictations"
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <details
            ref={menu}
            className="relative"
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.currentTarget.open = false;
                e.currentTarget.querySelector("summary")?.focus();
              }
            }}
          >
            <summary
              className="list-none cursor-pointer rounded-md px-3 py-2"
              aria-label="History actions"
            >
              <Ellipsis className="size-4" aria-hidden="true" />
            </summary>
            <div className="absolute right-0 z-10 flex rounded-lg border bg-popover p-2">
              <Button
                variant="outline"
                onClick={() => {
                  void action(async () => {
                    const path = await save({
                      defaultPath: "caelum-history.jsonl",
                      title: "Export history",
                    });
                    if (path) {
                      await ipc("history.export", { path });
                      return "exported";
                    }
                  }).then((result) => {
                    if (result) void action(async () => {}, "Exported");
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
          </details>
        </div>
      )}
      {history.isPending ? (
        <div
          aria-label="Loading dictations"
          aria-busy="true"
          className="space-y-3"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-22" />
          ))}
        </div>
      ) : history.isError ? (
        <p role="alert">History unavailable. Check storage permissions.</p>
      ) : history.data.length ? (
        compact ? (
          <div className="space-y-3">
            {history.data.slice(0, 3).map((entry) => (
              <Transcript
                key={entry.id}
                entry={entry}
                onDelete={() => setDeleting(entry.id)}
              />
            ))}
          </div>
        ) : (
          <div
            aria-busy={history.isPlaceholderData || query !== search}
            className={`grid min-w-0 items-start gap-8 ${selected ? "lg:grid-cols-[minmax(0,1fr)_280px]" : ""}`}
          >
            <TranscriptList
              entries={history.data}
              onDelete={setDeleting}
              onDetails={(entry) =>
                setSelectedId(entry.id === selectedId ? undefined : entry.id)
              }
              selectedId={selectedId}
            />
            {selected && (
              <aside
                ref={detail}
                tabIndex={-1}
                id="history-detail"
                aria-label="Dictation details"
                className="screen-enter sticky top-4 min-w-0 space-y-6 rounded-lg bg-card p-6 break-words"
                onKeyDown={(e) => {
                  if (e.key === "Escape") closeDetails();
                }}
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-section font-medium">
                    Dictation details
                  </h2>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Close dictation details"
                    onClick={closeDetails}
                  >
                    <X />
                  </Button>
                </div>
                <time
                  className="text-meta text-muted-foreground"
                  dateTime={selected.created_at}
                >
                  {new Date(selected.created_at).toLocaleString()}
                </time>
                <p className="select-text whitespace-pre-wrap text-body">
                  {selected.final_transcript}
                </p>
                <TranscriptDetails entry={selected} />
              </aside>
            )}
          </div>
        )
      ) : (
        <p className="py-12 text-body text-muted-foreground">
          {query
            ? "No matching dictations"
            : "Your dictations will appear here"}
        </p>
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
});

export function HistoryTools() {
  const [deleting, setDeleting] = useState(false);
  const client = useQueryClient();
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="outline"
        onClick={() =>
          void action(async () => {
            const path = await save({
              defaultPath: "caelum-history.jsonl",
              title: "Export history",
            });
            if (path) {
              await ipc("history.export", { path });
              return true;
            }
          }).then((done) => {
            if (done) void action(async () => {}, "Exported");
          })
        }
      >
        <Download />
        Export
      </Button>
      <Button variant="ghost" onClick={() => setDeleting(true)}>
        <Trash2 />
        Delete all
      </Button>
      <Confirm
        open={deleting}
        title="Delete all saved dictations?"
        detail="This permanently deletes local transcripts. Clipboard copies, exports, and lifetime word totals remain."
        confirm="Delete"
        onCancel={() => setDeleting(false)}
        onConfirm={async () => {
          await ipc("history.delete", {});
          setDeleting(false);
          await client.invalidateQueries({ queryKey: ["history"] });
          await client.invalidateQueries({ queryKey: ["summary"] });
        }}
      />
    </div>
  );
}
