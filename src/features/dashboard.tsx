import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  Mic,
  Square,
  RotateCcw,
  X,
  ArrowUpRight,
  AudioLines,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
} from "lucide-react";
import { useApp } from "@/stores/app";
import { ipc, type Config } from "@/lib/ipc";
import { action, Heading } from "@/components/common";
import { Transcript } from "@/components/transcript";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  const { data = [] } = useQuery({
    queryKey: ["devices"],
    queryFn: () => ipc("devices", {}),
    refetchInterval: 15000,
  });
  const devices = [
    { label: "System default", value: null },
    ...data.filter((d) => d.value !== null),
  ];
  if (value !== null && !devices.some((d) => d.value === value))
    devices.push({ label: `${value} (configured, not detected)`, value });
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
export function Dashboard({
  config,
  onMicrophone,
}: {
  config: Config;
  onMicrophone: (value: Config["app"]["microphone"]) => void;
}) {
  const status = useApp((s) => s.status),
    navigate = useApp((s) => s.navigate);
  const [busy, setBusy] = useState(false);
  const recording = ["starting", "listening", "recording"].includes(
    status?.state ?? "",
  );
  const processing = ["processing", "refining"].includes(status?.state ?? "");
  const history = useQuery({
    queryKey: ["history", "recent"],
    queryFn: () => ipc("history", {}),
    refetchInterval: 3000,
  });
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => ipc("summary", {}),
    refetchInterval: 5000,
  });
  const seconds = Math.floor((status?.feedback?.elapsed_ms ?? 0) / 1000);
  async function run(operation: () => Promise<unknown>) {
    setBusy(true);
    await action(operation);
    setBusy(false);
  }
  return (
    <div className="space-y-8">
      <Heading
        title="Dictation"
        detail="Record with the microphone button or your recording shortcut."
      />
      <Card className="overflow-hidden shadow-none">
        <CardContent className="space-y-7 p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Badge variant="outline" className="gap-2 py-1.5">
              <span
                className={`size-1.5 rounded-full ${recording ? "bg-destructive" : "bg-primary"}`}
              />
              <span role="status">{status?.title ?? "Connecting…"}</span>
            </Badge>
            <DeviceSelect
              value={config.app.microphone}
              onChange={onMicrophone}
              disabled={recording || processing}
            />
          </div>
          <div className="space-y-4 py-2 text-center">
            <div className="mx-auto flex size-14 items-center justify-center rounded-2xl border bg-secondary/40">
              <AudioLines className="size-7 text-primary" />
            </div>
            <Waveform values={status?.feedback?.history} />
            <p className="font-mono text-2xl tabular-nums">
              {recording
                ? `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
                : config.app.hotkey}
            </p>
            <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
              {status?.detail ??
                "Connecting to your local transcription engine."}
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {status && !status.running ? (
              <Button
                disabled={busy}
                onClick={() => {
                  void run(() => ipc("service.start", {}));
                }}
              >
                <Play />
                Start service
              </Button>
            ) : (
              <>
                <Button
                  disabled={
                    busy ||
                    !status ||
                    processing ||
                    (status.backend === "hyprland" && !recording) ||
                    status.pending_audio ||
                    status.paused
                  }
                  onClick={() => {
                    void run(() =>
                      ipc("control", { action: recording ? "stop" : "start" }),
                    );
                  }}
                >
                  {recording ? (
                    <Square className="size-4" />
                  ) : (
                    <Mic className="size-4" />
                  )}
                  {recording
                    ? "Finish recording"
                    : status?.backend === "hyprland"
                      ? "Use your recording shortcut"
                      : "Record"}
                </Button>
                {status?.pending_audio && !processing && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => {
                      void run(() => ipc("control", { action: "retry" }));
                    }}
                  >
                    <RotateCcw />
                    Retry dictation
                  </Button>
                )}
                {recording || processing || status?.pending_audio ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      void run(() => ipc("control", { action: "cancel" }));
                    }}
                  >
                    <X />
                    {status?.pending_audio ? "Discard recording" : "Cancel"}
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    disabled={busy || !status}
                    onClick={() => {
                      void run(() =>
                        ipc("control", {
                          action: status?.paused ? "resume" : "pause",
                        }),
                      );
                    }}
                  >
                    {status?.paused ? <Play /> : <Pause />}
                    {status?.paused ? "Resume" : "Pause"}
                  </Button>
                )}
              </>
            )}
          </div>
          <p className="text-center text-xs text-muted-foreground">
            Audio goes to your provider. Microphone recordings are never saved.
          </p>
          {status?.storage_error && (
            <p role="alert" className="text-sm text-destructive">
              Dictation worked, but history could not be saved. Check local
              storage permissions.
            </p>
          )}
        </CardContent>
      </Card>
      <div className="grid gap-4 sm:grid-cols-2">
        <Metric
          label="Words dictated · lifetime"
          value={(summary.data?.total_words ?? 0).toLocaleString()}
        />
        <Metric
          label="Recording minutes · saved history"
          value={((summary.data?.duration_ms ?? 0) / 60000).toFixed(1)}
        />
      </div>
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Recent dictations</h2>
          <Button variant="ghost" size="sm" onClick={() => navigate("history")}>
            View all
            <ArrowUpRight className="size-4" />
          </Button>
        </div>
        {history.data?.length ? (
          history.data
            .slice(0, 5)
            .map((entry) => <Transcript key={entry.id} entry={entry} />)
        ) : (
          <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
            No transcriptions yet. Start a recording to see the result here.
          </p>
        )}
      </section>
      <UsageCalendar activity={summary.data?.activity ?? {}} />
    </div>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card className="shadow-none">
      <CardContent className="space-y-3 pt-5">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-3xl font-medium tracking-tight tabular-nums">
          {value}
        </p>
      </CardContent>
    </Card>
  );
}
export function Statistics() {
  const { data } = useQuery({
    queryKey: ["summary"],
    queryFn: () => ipc("summary", {}),
    refetchInterval: 5000,
  });
  const max = Math.max(1, ...Object.values(data?.daily ?? {}));
  return (
    <div className="space-y-8">
      <Heading
        title="Statistics"
        detail="Your dictation activity. Daily counts reflect retained history; lifetime words survive deletion."
      />
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
          label="Total words · lifetime"
          value={(data?.total_words ?? 0).toLocaleString()}
        />
        <Metric
          label="Words / recording minute"
          value={(data?.wpm ?? 0).toFixed(0)}
        />
      </div>
      <Card className="shadow-none">
        <CardContent className="pt-6">
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
        </CardContent>
      </Card>
      <UsageCalendar activity={data?.activity ?? {}} />
    </div>
  );
}
function UsageCalendar({ activity }: { activity: Record<string, number> }) {
  const today = new Date(),
    [month, setMonth] = useState(
      () => new Date(today.getFullYear(), today.getMonth(), 1),
    ),
    [selected, select] = useState("");
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Daily usage</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Previous month"
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
            }
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
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
            }
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-2">
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
            key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`,
            words = activity[key] ?? 0;
          return (
            <Button
              key={key}
              variant={selected === key ? "outline" : "ghost"}
              className={`h-9 text-xs ${words >= 1000 ? "bg-primary/70 text-primary-foreground" : words >= 500 ? "bg-primary/40" : words >= 100 ? "bg-primary/20" : words ? "bg-primary/10" : "bg-muted/40"}`}
              disabled={day > today}
              aria-label={`${key}: ${words} words`}
              onClick={() => select(key)}
            >
              {i + 1}
            </Button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        {selected ? `${selected}: ${activity[selected] ?? 0} words. ` : ""}Words
        from saved dictations. Intensity: 0, 1–99, 100–499, 500–999, 1,000+.
      </p>
    </section>
  );
}
