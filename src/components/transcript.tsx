import { memo, useId, useState } from "react";
import { ChevronRight, Trash2 } from "lucide-react";
import type { Dictation } from "@/lib/ipc";
import { CopyButton } from "@/components/common";
import { Button } from "@/components/ui/button";

export function dayLabel(value: string, now = new Date()) {
  const day = new Date(value);
  const yesterday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  );
  if (day.toDateString() === now.toDateString()) return "Today";
  if (day.toDateString() === yesterday.toDateString()) return "Yesterday";
  return day.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
function languageLabel(value?: string) {
  if (!value || value === "auto") return "Auto";
  if (value === "mixed") return "Multiple languages";
  try {
    return (
      new Intl.DisplayNames(["en"], { type: "language" }).of(
        value.split(/[_-]/)[0],
      ) ?? value
    );
  } catch {
    return value;
  }
}
export function TranscriptDetails({ entry }: { entry: Dictation }) {
  return (
    <dl className="flex flex-wrap gap-4 text-meta text-muted-foreground">
      <div>
        <dt className="sr-only">Words</dt>
        <dd>{entry.word_count} words</dd>
      </div>
      <div>
        <dt className="sr-only">Duration</dt>
        <dd>{(entry.duration_ms / 1000).toFixed(1)} seconds</dd>
      </div>
      <div>
        <dt>Engine</dt>
        <dd>
          {entry.engine === "local" ? "On this computer" : "Online"}
          {entry.stt_model ? ` · ${entry.stt_model}` : ""}
        </dd>
      </div>
      <div>
        <dt>Language</dt>
        <dd>{languageLabel(entry.language)}</dd>
      </div>
      <div>
        <dt className="sr-only">Text status</dt>
        <dd>
          {entry.copied ? (
            "Not inserted"
          ) : entry.engine === "local" ? (
            "Offline cleanup"
          ) : !entry.refined ? (
            <span>
              <span>Raw</span> · Text cleanup was skipped or unavailable.
            </span>
          ) : (
            "Cleaned up"
          )}
        </dd>
      </div>
    </dl>
  );
}
export const TranscriptList = memo(function TranscriptList({
  entries,
  onDelete,
  onDetails,
  selectedId,
}: {
  entries: Dictation[];
  onDelete?: (id: string) => void;
  onDetails?: (entry: Dictation) => void;
  selectedId?: string;
}) {
  const groups = new Map<string, Dictation[]>();
  for (const entry of entries) {
    const label = dayLabel(entry.created_at);
    const group = groups.get(label);
    if (group) group.push(entry);
    else groups.set(label, [entry]);
  }
  return (
    <div className="space-y-8">
      {[...groups].map(([label, rows]) => (
        <section key={label} className="space-y-3">
          <h2 className="text-section font-medium text-muted-foreground">
            {label}
          </h2>
          {rows.map((entry) => (
            <Transcript
              key={entry.id}
              entry={entry}
              onDelete={onDelete ? () => onDelete(entry.id) : undefined}
              onDetails={onDetails ? () => onDetails(entry) : undefined}
              selected={selectedId === entry.id}
            />
          ))}
        </section>
      ))}
    </div>
  );
});
export function Transcript({
  entry,
  onDelete,
  onDetails,
  selected = false,
}: {
  entry: Dictation;
  onDelete?: () => void;
  onDetails?: () => void;
  selected?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const inlineId = useId();
  const open = onDetails ? selected : expanded;
  return (
    <article
      className={`transcript-row group min-w-0 rounded-lg px-4 py-3 ${open ? "bg-muted" : "bg-card"}`}
    >
      <div className="flex items-start gap-4">
        <time
          className="pt-2 text-meta tabular-nums text-muted-foreground"
          dateTime={entry.created_at}
        >
          {new Date(entry.created_at).toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </time>
        <p
          className={`min-h-8 min-w-0 flex-1 select-text break-words pt-1.5 text-body ${open && !onDetails ? "whitespace-pre-wrap" : "line-clamp-2"}`}
        >
          {entry.final_transcript}
        </p>
        <div className="flex shrink-0 opacity-100 transition-opacity duration-160 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100">
          <Button
            id={`dictation-details-${entry.id}`}
            variant="ghost"
            size="icon"
            aria-label="Show dictation details"
            aria-expanded={open}
            aria-controls={onDetails ? "history-detail" : inlineId}
            onClick={() => {
              if (onDetails) onDetails();
              else setExpanded(!expanded);
            }}
          >
            <ChevronRight className={open ? "rotate-90" : ""} />
          </Button>
          <CopyButton text={entry.final_transcript} />
          {onDelete && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete dictation"
              onClick={onDelete}
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </div>
      {!onDetails && (
        <div id={inlineId} hidden={!open} className="mt-4 border-t pt-4">
          {open && <TranscriptDetails entry={entry} />}
        </div>
      )}
    </article>
  );
}
