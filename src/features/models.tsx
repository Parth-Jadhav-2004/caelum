import { useEffect, useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { ChevronDown, MoreHorizontal } from "lucide-react";
import { ipc, type SpeechModel } from "@/lib/ipc";
import { useModels } from "@/hooks/use-models";
import { useDownloads } from "@/stores/models";
import { useApp } from "@/stores/app";
import { action, Confirm, CopyButton } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function size(bytes: number) {
  return bytes >= 1e9
    ? `${(bytes / 1e9).toFixed(1)} GB`
    : `${Math.ceil(bytes / 1e6)} MB`;
}
function displaySize(model: SpeechModel) {
  return size(
    model.id === "parakeet-110m" ? model.disk_bytes : model.download_bytes,
  );
}
export function languageName(code: string) {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}
export function DownloadProgress({ model }: { model: SpeechModel }) {
  const total = model.total_bytes || model.download_bytes;
  const percent = Math.min(
    100,
    Math.max(0, (model.received_bytes / Math.max(1, total)) * 100),
  );
  const checking = ["verifying", "installing"].includes(model.state);
  return (
    <div className="space-y-2">
      {checking ? (
        <div
          role="progressbar"
          aria-label={`${model.label} download`}
          aria-valuetext="Checking files"
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <span className="block h-full w-1/3 bg-muted-foreground motion-safe:animate-pulse" />
        </div>
      ) : (
        <Progress
          value={percent}
          aria-label={`${model.label} download`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={checking ? undefined : Math.round(percent)}
          aria-valuetext={`${Math.round(model.received_bytes / 1e6)} megabytes of ${Math.round(total / 1e6)}`}
        />
      )}
      {!checking && (
        <p className="text-xs text-muted-foreground">
          {checking
            ? "Checking files…"
            : `${model.state === "paused" ? "Paused · " : ""}${size(model.received_bytes)} of ${size(total)}`}
          {!checking &&
            model.state !== "paused" &&
            model.eta_seconds !== null &&
            ` · about ${Math.max(1, Math.ceil(model.eta_seconds / 60))} min left`}
        </p>
      )}
    </div>
  );
}

export function ModelPicker({
  selected,
  onSelect,
  beforeUse,
}: {
  selected?: string;
  onSelect?: (id: string) => void;
  beforeUse?: () => Promise<void>;
}) {
  const { data, models, isPending, error, refetch } = useModels();
  const client = useQueryClient();
  const status = useApp((s) => s.status);
  const announcement = useDownloads((s) => s.announcement);
  const [all, setAll] = useState(false);
  const [remove, setRemove] = useState<SpeechModel | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [damaged, setDamaged] = useState<Record<string, boolean>>({});
  const group = useId();
  const root = useRef<HTMLDivElement>(null);
  async function run(id: string, operation: () => Promise<unknown>) {
    setBusy(id);
    await action(operation);
    await refetch();
    await client.invalidateQueries({ queryKey: ["bootstrap"] });
    setBusy(null);
  }
  function select(model: SpeechModel) {
    if (onSelect) {
      onSelect(model.id);
      return;
    }
    void run(model.id, async () => {
      await beforeUse?.();
      await ipc("models.use", { id: model.id, when_ready: true });
    });
  }
  const chosen =
    selected ?? data?.pending_use ?? models.find((m) => m.in_use)?.id;
  if (isPending)
    return (
      <p role="status" className="py-4 text-sm text-muted-foreground">
        Checking speech models…
      </p>
    );
  if (error)
    return (
      <div role="alert" className="space-y-2">
        <p>Couldn’t check speech models.</p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  const visible = models.filter((m) => all || m.visible);
  return (
    <div className="space-y-4">
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>
      <div
        ref={root}
        role="radiogroup"
        aria-label="Speech model"
        className="space-y-3"
      >
        {visible.map((model) => {
          const loading = model.in_use && status?.engine?.state === "loading";
          const active = [
            "downloading",
            "paused",
            "verifying",
            "installing",
          ].includes(model.state);
          const ready = model.state === "installed";
          const disabled =
            !!model.disabled_reason &&
            (!ready || model.disabled_reason === "Needs an extra component.");
          const id = `${group}-${model.id}`;
          return (
            <div key={model.id} className="rounded-lg border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <input
                    type="radio"
                    name={group}
                    id={id}
                    value={model.id}
                    className="mt-1 size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                    checked={chosen === model.id}
                    disabled={disabled || busy === model.id}
                    onChange={() => select(model)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        select(model);
                      }
                      if (
                        ![
                          "ArrowRight",
                          "ArrowDown",
                          "ArrowLeft",
                          "ArrowUp",
                        ].includes(event.key)
                      )
                        return;
                      event.preventDefault();
                      const radios = Array.from(
                        root.current?.querySelectorAll<HTMLInputElement>(
                          "input[type=radio]:not(:disabled)",
                        ) ?? [],
                      );
                      const offset = ["ArrowRight", "ArrowDown"].includes(
                        event.key,
                      )
                        ? 1
                        : -1;
                      const next =
                        radios[
                          (radios.indexOf(event.currentTarget) +
                            offset +
                            radios.length) %
                            radios.length
                        ];
                      next?.focus();
                      next?.click();
                    }}
                  />
                  <div className="min-w-0 space-y-1">
                    <label
                      htmlFor={id}
                      className="cursor-pointer text-sm font-medium"
                    >
                      {model.label}
                    </label>
                    {model.id === data?.recommended.id && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        Recommended for this computer
                      </span>
                    )}
                    <p className="text-xs leading-5 text-muted-foreground">
                      {model.blurb}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {displaySize(model)}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  {onSelect ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={disabled}
                      onClick={() => select(model)}
                    >
                      Choose
                    </Button>
                  ) : model.state === "queued" ? (
                    <>
                      <span className="text-xs text-muted-foreground">
                        Waiting…
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          void run(model.id, () =>
                            ipc("models.cancel", { id: model.id }),
                          )
                        }
                      >
                        Cancel
                      </Button>
                    </>
                  ) : ["downloading", "paused"].includes(model.state) ? (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy === model.id}
                        onClick={() =>
                          void run(model.id, () =>
                            ipc(
                              model.state === "paused"
                                ? "models.resume"
                                : "models.pause",
                              { id: model.id },
                            ),
                          )
                        }
                      >
                        {model.state === "paused" ? "Resume" : "Pause"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy === model.id}
                        onClick={() =>
                          void run(model.id, () =>
                            ipc("models.cancel", { id: model.id }),
                          )
                        }
                      >
                        Cancel
                      </Button>
                    </>
                  ) : ["verifying", "installing"].includes(model.state) ? (
                    <span className="text-xs text-muted-foreground">
                      Checking files…
                    </span>
                  ) : ready ? (
                    <>
                      {model.in_use ? (
                        <span className="px-2 text-xs text-muted-foreground">
                          {loading ? "Getting ready…" : "In use"}
                        </span>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={disabled || busy === model.id}
                          onClick={() => select(model)}
                        >
                          Use
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Actions for ${model.label}`}
                          >
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem
                            onSelect={() =>
                              void run(model.id, async () => {
                                const result = await ipc("models.verify", {
                                  id: model.id,
                                });
                                setDamaged((state) => ({
                                  ...state,
                                  [model.id]: !result.ok,
                                }));
                              })
                            }
                          >
                            Check files
                          </DropdownMenuItem>
                          {!model.in_use && (
                            <DropdownMenuItem onSelect={() => setRemove(model)}>
                              Remove
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={disabled || busy === model.id}
                      onClick={() =>
                        void run(model.id, () =>
                          ipc("models.download", { id: model.id }),
                        )
                      }
                    >
                      {model.state === "failed"
                        ? "Try again"
                        : damaged[model.id]
                          ? "Download again"
                          : `Download ${displaySize(model)}`}
                    </Button>
                  )}
                </div>
              </div>
              {active && (
                <div className="mt-4">
                  <DownloadProgress model={model} />
                </div>
              )}
              {model.error && (
                <p className="mt-2 text-xs text-destructive">
                  {model.error.message}
                </p>
              )}
              {damaged[model.id] && (
                <p className="mt-2 text-xs text-destructive">
                  Some files are damaged. Download them again (
                  {displaySize(model)}).
                </p>
              )}
              {model.disabled_reason &&
                (!ready ||
                  model.disabled_reason === "Needs an extra component.") && (
                  <p
                    className={`mt-2 text-xs ${model.disabled_reason.includes("free") ? "text-destructive" : "text-muted-foreground"}`}
                  >
                    {model.disabled_reason}{" "}
                    {model.disabled_reason === "Needs an extra component." && (
                      <Button
                        variant="link"
                        size="sm"
                        onClick={() =>
                          void action(() => invoke("open_model_help"))
                        }
                      >
                        How to add it
                      </Button>
                    )}
                  </p>
                )}
              <details className="mt-3 text-xs leading-6 text-muted-foreground">
                <summary className="flex w-fit cursor-pointer list-none items-center gap-1">
                  Details <ChevronDown className="size-3" />
                </summary>
                <dl className="mt-2 space-y-1">
                  <div>
                    <dt className="inline font-medium">Languages: </dt>
                    <dd className="inline">
                      {model.languages.includes("*")
                        ? "99 languages"
                        : model.languages.map(languageName).join(", ")}
                      {model.auto_language &&
                        " · Detects the language automatically"}
                    </dd>
                  </div>
                  {model.wer.open_asr_latest !== undefined && (
                    <div>
                      <dt className="inline font-medium">Mistakes: </dt>
                      <dd className="inline">
                        About {Math.round(model.wer.open_asr_latest)} in 100
                        words on standard English tests
                      </dd>
                    </div>
                  )}
                  <div>
                    <dt className="inline font-medium">
                      Speed on this computer:{" "}
                    </dt>
                    <dd className="inline">
                      {model.decode_ms === null
                        ? "Measured after your first dictation"
                        : `${(model.decode_ms / 1000).toFixed(1)} s after you let go`}
                    </dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Memory: </dt>
                    <dd className="inline">
                      about{" "}
                      {model.id === "cohere-transcribe"
                        ? "3.5 GB"
                        : model.id === "parakeet-110m"
                          ? "0.4 GB"
                          : model.requires_extra
                            ? "2–4 GB"
                            : "1.1 GB"}{" "}
                      while Caelum is running
                    </dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Licence: </dt>
                    <dd className="inline">
                      <a
                        href={model.licence.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline underline-offset-4"
                      >
                        {model.licence.attribution}
                      </a>
                    </dd>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <dt className="font-medium">Stored in:</dt>
                    <dd className="break-all">{model.stored_in}</dd>
                    <CopyButton text={model.stored_in} />
                  </div>
                </dl>
              </details>
            </div>
          );
        })}
      </div>
      {models.some((m) => !m.visible) && (
        <Button variant="ghost" size="sm" onClick={() => setAll(!all)}>
          {all
            ? "Show fewer models"
            : `Show all models (${models.filter((m) => !m.visible).length})`}
        </Button>
      )}
      {data?.pending_use && (
        <p role="status" className="text-xs text-muted-foreground">
          Caelum will switch to{" "}
          {models.find((m) => m.id === data.pending_use)?.label} when it’s
          downloaded.
        </p>
      )}
      <Confirm
        open={!!remove}
        title={`Remove ${remove?.label ?? "model"}?`}
        detail={`This frees ${size(remove?.disk_bytes ?? 0)}. You can download it again anytime.`}
        confirm="Remove"
        onCancel={() => setRemove(null)}
        onConfirm={async () => {
          if (remove) await ipc("models.remove", { id: remove.id });
          setRemove(null);
          await refetch();
        }}
      />
    </div>
  );
}

export function ModelDownloadLine({ modelId }: { modelId: string }) {
  const { models, refetch } = useModels();
  const announcement = useDownloads((state) => state.announcement);
  const model = models.find((item) => item.id === modelId);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (model?.state !== "installed") return;
    setReady(true);
    const timeout = setTimeout(() => setReady(false), 3000);
    return () => clearTimeout(timeout);
  }, [model?.state]);
  if (!model) return null;
  if (model.state === "installed")
    return ready ? (
      <p role="status" className="text-sm text-muted-foreground">
        {model.label} is ready
      </p>
    ) : null;
  if (
    !["queued", "downloading", "paused", "verifying", "installing"].includes(
      model.state,
    )
  )
    return null;
  return (
    <section
      aria-label="Speech model download"
      className="space-y-3 rounded-lg border p-4"
    >
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm">
          {model.state === "paused"
            ? "Download paused"
            : `Downloading ${model.label}`}
        </p>
        {["paused", "downloading"].includes(model.state) && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              void action(() =>
                ipc(
                  model.state === "paused" ? "models.resume" : "models.pause",
                  { id: model.id },
                ),
              ).then(() => refetch())
            }
          >
            {model.state === "paused" ? "Resume" : "Pause"}
          </Button>
        )}
      </div>
      <DownloadProgress model={model} />
    </section>
  );
}
