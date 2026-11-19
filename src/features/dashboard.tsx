import { History } from "./history";
import { useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  Mic,
  Square,
  RotateCcw,
  X,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useApp } from "@/stores/app";
import { ipc, type Config } from "@/lib/ipc";
import { formatShortcut } from "@/lib/shortcut";
import { action, Heading } from "@/components/common";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
export function Waveform({
  values = Array<number>(17).fill(0),
}: {
  values?: number[];
}) {
  return (
    <div
      className="flex h-14 items-center justify-center gap-1.5"
      role="img"
      aria-label="Microphone input level"
    >
      {values.map((value, i) => (
        <span
          key={i}
          className="w-1 rounded-full bg-primary transition-[height] duration-75"
          style={{ height: `${4 + Math.max(0, Math.min(1, value)) * 46}px` }}
        />
      ))}
    </div>
  );
}
export function DeviceSelect({
  value,
  onChange,
  disabled,
}: {
  value: Config["app"]["microphone"];
  onChange: (value: Config["app"]["microphone"]) => void;
  disabled?: boolean;
}) {
  const { data, isSuccess } = useQuery({
    queryKey: ["devices"],
    queryFn: () => ipc("devices", {}),
    refetchInterval: 15000,
  });
  const devices = [
    { label: "System default", value: null },
    ...(data ?? []).filter((d) => d.value !== null),
  ];
  if (value !== null && !devices.some((d) => d.value === value))
    devices.push({
      label: isSuccess ? `${value} (configured, not detected)` : String(value),
      value,
    });
  return (
    <Select
      value={JSON.stringify(value)}
      disabled={disabled}
      onValueChange={(v) =>
        onChange(JSON.parse(v) as Config["app"]["microphone"])
      }
    >
      <SelectTrigger className="w-full max-w-72" aria-label="Microphone">
        <Mic className="size-4" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {devices.map((d) => (
          <SelectItem
            key={JSON.stringify(d.value)}
            value={JSON.stringify(d.value)}
          >
            {d.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
export function Dashboard({ config }: { config: Config }) {
  const status = useApp((s) => s.status);
  const [busy, setBusy] = useState(false);
  const recording = ["starting", "listening", "recording"].includes(
    status?.state ?? "",
  );
  const processing = ["processing", "refining", "loading"].includes(
    status?.state ?? "",
  );
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => ipc("summary", {}),
    refetchInterval: 5000,
  });
  async function run(actionName: "start" | "stop" | "cancel" | "retry") {
    setBusy(true);
    await action(() => ipc("control", { action: actionName }));
    setBusy(false);
  }
  const nativeShortcut = status?.backend === "hyprland" || status?.backend === "windows";
  const activity = summary.data?.activity ?? {};
  let streak = 0;
  const day = new Date();
  if (!activity[dateKey(day)]) day.setDate(day.getDate() - 1);
  while (activity[dateKey(day)]) {
    streak++;
    day.setDate(day.getDate() - 1);
  }
  return (
    <div className="space-y-8">
      <section
        aria-label="Dictation"
        className="space-y-6 rounded-lg bg-card p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 tabIndex={-1} className="text-title font-medium">
            {nativeShortcut ? (
              <>
                {config.app.recording_mode === "toggle" ? "Press" : "Hold"}{" "}
                <kbd>{formatShortcut(config.app.hotkey)}</kbd> to dictate
              </>
            ) : (
              "Record, finish, then copy your transcript"
            )}
          </h1>
          {!nativeShortcut && (
            <Button
              variant="secondary"
              disabled={
                busy ||
                !status ||
                processing ||
                status.pending_audio ||
                status.paused ||
                !status.running
              }
              onClick={() => void run(recording ? "stop" : "start")}
            >
              {recording ? <Square /> : <Mic />}
              {recording ? "Finish recording" : "Record"}
            </Button>
          )}
          {nativeShortcut && recording && (
            <Button variant="secondary" onClick={() => void run("stop")}>
              Finish recording
            </Button>
          )}
        </div>
        <div
          aria-label="Today’s activity"
          aria-busy={summary.isPending}
          className="flex min-h-12 flex-wrap gap-8 border-b pb-6 text-meta text-muted-foreground tabular-nums"
        >
          <span>
            <strong className="mr-2 text-foreground">
              {summary.isPending ? (
                <Skeleton className="inline-block h-4 w-8 align-middle" />
              ) : summary.isError ? (
                "—"
              ) : (
                (summary.data.today_words ?? 0).toLocaleString()
              )}
            </strong>
            Words today
          </span>
          <span>
            <strong className="mr-2 text-foreground">
              {summary.isPending ? (
                <Skeleton className="inline-block h-4 w-8 align-middle" />
              ) : summary.isError ? (
                "—"
              ) : (
                (summary.data.wpm ?? 0).toFixed(0)
              )}
            </strong>
            Words/min
          </span>
          <span>
            <strong className="mr-2 text-foreground">
              {summary.isPending ? (
                <Skeleton className="inline-block h-4 w-8 align-middle" />
              ) : summary.isError ? (
                "—"
              ) : (
                streak
              )}
            </strong>
            Day streak
          </span>
        </div>
        <div className="flex min-h-24 flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            {recording ? (
              <Waveform values={status?.feedback?.history} />
            ) : (
              <p role="status" className="text-body text-muted-foreground">
                {processing
                  ? "Turning your speech into text…"
                  : status?.detail ||
                    "Your words appear in the app you’re using."}
              </p>
            )}
          </div>
          {status?.pending_audio && !processing && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void run("retry")}
            >
              <RotateCcw />
              Retry dictation
            </Button>
          )}
          {(recording || processing || status?.pending_audio) && (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => void run("cancel")}
            >
              <X />
              {status?.pending_audio ? "Discard recording" : "Cancel"}
            </Button>
          )}
        </div>
        {status?.storage_error && (
          <p role="alert">History wasn’t saved. Check storage permissions.</p>
        )}
      </section>
      <History compact />
    </div>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <section>
      <div className="space-y-3 py-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p
          className={`${label === "Total words" ? "text-display" : "text-title"} font-medium tabular-nums`}
        >
          {value}
        </p>
      </div>
    </section>
  );
}
export function Statistics() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["summary"],
    queryFn: () => ipc("summary", {}),
    refetchInterval: 5000,
  });
  if (isPending)
    return (
      <div className="space-y-8" aria-label="Loading insights" aria-busy="true">
        <Heading title="Insights" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  if (isError)
    return (
      <div className="space-y-8">
        <Heading title="Insights" />
        <p role="alert">Couldn’t load your activity.</p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  const max = Math.max(1, ...Object.values(data?.daily ?? {}));
  return (
    <div className="space-y-8">
      <Heading title="Insights" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Metric
          label="Words today"
          value={(data?.today_words ?? 0).toLocaleString()}
        />
        <Metric
          label="Words this month"
          value={(data?.month_words ?? 0).toLocaleString()}
        />
        <Metric
          label="Total words"
          value={(data?.total_words ?? 0).toLocaleString()}
        />
        <Metric label="Words/min" value={(data?.wpm ?? 0).toFixed(0)} />
      </div>
      <section>
        <div className="pt-6">
          <h2 className="font-medium">The last seven days</h2>
          <div className="mt-8 flex h-48 items-end gap-3">
            {Object.entries(data?.daily ?? {}).map(([day, words]) => (
              <div
                key={day}
                className="flex h-full flex-1 flex-col justify-end gap-2 text-center"
              >
                <span className="text-xs text-muted-foreground">{words}</span>
                <motion.div
                  initial={false}
                  animate={{ height: `${Math.max(2, (words / max) * 75)}%` }}
                  className="mx-auto w-full max-w-12 rounded-t-md bg-primary/70"
                  role="img"
                  aria-label={`${day}: ${words} words`}
                />
                <span className="text-xs text-muted-foreground">
                  {new Date(day + "T12:00:00").toLocaleDateString(undefined, {
                    weekday: "short",
                  })}
                </span>
              </div>
            ))}
          </div>
          {max === 1 && (
            <p className="mt-4 text-sm text-muted-foreground">
              Your first dictation starts the chart.
            </p>
          )}
        </div>
      </section>
      <UsageCalendar activity={data?.activity ?? {}} />
    </div>
  );
}
function dateKey(day: Date) {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}
export function UsageCalendar({
  activity,
}: {
  activity: Record<string, number>;
}) {
  const today = new Date(),
    [month, setMonth] = useState(
      () => new Date(today.getFullYear(), today.getMonth(), 1),
    ),
    [selected, select] = useState("");
  const [focused, setFocused] = useState(() => dateKey(today));
  const calendar = useRef<HTMLDivElement>(null);
  const focusPending = useRef(false);
  useLayoutEffect(() => {
    if (focusPending.current) {
      calendar.current
        ?.querySelector<HTMLButtonElement>(`[data-date="${focused}"]`)
        ?.focus();
      focusPending.current = false;
    }
  }, [focused, month]);
  function changeMonth(offset: number) {
    const next = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    setMonth(next);
    setFocused(dateKey(next));
  }
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-section font-medium">Daily usage</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Previous month"
            onClick={() => changeMonth(-1)}
          >
            <ChevronLeft />
          </Button>
          <span className="text-sm">
            {month.toLocaleDateString(undefined, {
              month: "long",
              year: "numeric",
            })}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Next month"
            disabled={
              month.getFullYear() === today.getFullYear() &&
              month.getMonth() === today.getMonth()
            }
            onClick={() => changeMonth(1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      <p id="calendar-help" className="sr-only">
        Use arrow keys to move by day or week, Home/End for the start/end of the
        week, Enter to select, and Escape to clear the selection.
      </p>
      <div
        ref={calendar}
        role="group"
        aria-label="Daily usage calendar"
        aria-describedby="calendar-help"
        className="grid grid-cols-7 gap-2"
      >
        {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((d) => (
          <span key={d} className="text-center text-xs text-muted-foreground">
            {d}
          </span>
        ))}
        {Array.from({ length: month.getDay() }, (_, i) => (
          <span key={`blank-${i}`} />
        ))}
        {Array.from({ length: days }, (_, i) => {
          const day = new Date(month.getFullYear(), month.getMonth(), i + 1),
            key = dateKey(day),
            words = activity[key] ?? 0;
          return (
            <Button
              key={key}
              variant={selected === key ? "outline" : "ghost"}
              className={`h-9 text-xs ${words >= 1000 ? "bg-primary/70 text-primary-foreground" : words >= 500 ? "bg-primary/40" : words >= 100 ? "bg-primary/20" : words ? "bg-primary/10" : "bg-muted/40"}`}
              disabled={day > today}
              aria-label={`${key}: ${words} words`}
              aria-pressed={selected === key}
              data-date={key}
              tabIndex={focused === key ? 0 : -1}
              onFocus={() => setFocused(key)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  select("");
                  return;
                }
                const offsets: Record<string, number> = {
                  ArrowLeft: -1,
                  ArrowRight: 1,
                  ArrowUp: -7,
                  ArrowDown: 7,
                  Home: -day.getDay(),
                  End: 6 - day.getDay(),
                };
                const offset = offsets[event.key];
                if (offset === undefined) return;
                event.preventDefault();
                const next = new Date(
                  day.getFullYear(),
                  day.getMonth(),
                  day.getDate() + offset,
                );
                if (next > today) next.setTime(today.getTime());
                focusPending.current = true;
                setFocused(dateKey(next));
                setMonth(new Date(next.getFullYear(), next.getMonth(), 1));
              }}
              onClick={() => select(key)}
            >
              {i + 1}
            </Button>
          );
        })}
      </div>
      <p role="status" className="text-xs text-muted-foreground">
        {selected ? (
          `${selected}: ${activity[selected] ?? 0} words`
        ) : (
          <span className="flex items-center gap-2">
            <span>Less</span>
            <span aria-hidden="true" className="flex gap-1">
              {[
                "bg-primary/10",
                "bg-primary/20",
                "bg-primary/40",
                "bg-primary/70",
              ].map((colour) => (
                <span key={colour} className={`size-3 rounded-sm ${colour}`} />
              ))}
            </span>
            <span>More</span>
          </span>
        )}
      </p>
    </section>
  );
}
