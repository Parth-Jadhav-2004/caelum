import { Trash2 } from "lucide-react";
import type { Dictation } from "@/lib/ipc";
import { CopyButton } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
export function Transcript({
  entry,
  onDelete,
}: {
  entry: Dictation;
  onDelete?: () => void;
}) {
  return (
    <Card className="shadow-none">
      <CardContent className="space-y-4 pt-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <time dateTime={entry.created_at}>
              {new Date(entry.created_at).toLocaleString()}
            </time>
            <span>·</span>
            <span>{entry.word_count} words</span>
            <span>·</span>
            <span>{(entry.duration_ms / 1000).toFixed(1)}s</span>
            {entry.copied ? (
              <Badge variant="secondary">Clipboard recovery</Badge>
            ) : (
              !entry.refined && <Badge variant="secondary">Unrefined</Badge>
            )}
          </div>
          <div className="flex">
            <CopyButton text={entry.final_transcript} />
            {onDelete && (
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete dictation"
                onClick={onDelete}
              >
                <Trash2 className="size-4" />
              </Button>
            )}
          </div>
        </div>
        <p className="select-text whitespace-pre-wrap text-sm leading-7">
          {entry.final_transcript}
        </p>
        {!entry.refined && (
          <p className="text-xs text-muted-foreground">
            Raw transcription · refinement skipped or unavailable.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
