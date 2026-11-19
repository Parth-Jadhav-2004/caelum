import {
  useState,
  lazy,
  Suspense,
  useRef,
  useEffect,
  useLayoutEffect,
  type ReactNode,
  type KeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, FlaskConical, Check } from "lucide-react";
import { ipc, type Config } from "@/lib/ipc";
import { formatShortcut } from "@/lib/shortcut";
import { action, Heading, Confirm } from "@/components/common";
import { useApp } from "@/stores/app";
import { Button } from "@/components/ui/button";
import { ModelPicker } from "./models";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { HistoryTools } from "./history";
import { MicrophoneTestDialog } from "./microphone";
import { ACCENTS, resolveColorTheme } from "@/lib/themes";
import { DeviceSelect } from "./dashboard";
import { Skeleton } from "@/components/ui/skeleton";
const UpdateSettings = lazy(() =>
  import("./update-settings").then((m) => ({ default: m.UpdateSettings })),
);
export function Choice({
  label,
  value,
  items,
  change,
  disabled = false,
}: {
  disabled?: boolean;
  label: string;
  value: string;
  items: [string, string][];
  change: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={change} disabled={disabled}>
      <SelectTrigger aria-label={label} className="w-full max-w-full sm:w-56">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map(([key, text]) => (
          <SelectItem key={key} value={key}>
            {text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
export function Row({
  title,
  detail,
  children,
}: {
  title: string;
  detail?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-12 flex-col justify-between gap-4 border-b py-1 last:border-0 sm:flex-row sm:items-center">
      <div className="min-w-0 space-y-1 py-2">
        <p className="text-sm font-medium">{title}</p>
        {detail && (
          <p className="max-w-md whitespace-pre-line text-meta text-muted-foreground">
            {detail}
          </p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
export function Shortcut({
  value,
  change,
  large = false,
}: {
  value: string;
  change: (value: string) => void;
  large?: boolean;
}) {
  const [capture, setCapture] = useState(false);
  const modifierCombo = useRef<string[]>([]);
  function key(event: KeyboardEvent<HTMLButtonElement>) {
    if (!capture) return;
    if (event.key === "Tab" || event.key === "Escape") {
      setCapture(false);
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const mods = [
      event.metaKey && "SUPER",
      event.ctrlKey && "CTRL",
      event.altKey && "ALT",
      event.shiftKey && "SHIFT",
    ].filter(Boolean) as string[];
    if (["Meta", "Control", "Alt", "Shift"].includes(event.key)) {
      modifierCombo.current = mods;
      return;
    }
    if (mods.length) {
      change(
        [...mods, event.key === " " ? "SPACE" : event.key.toUpperCase()].join(
          " + ",
        ),
      );
      setCapture(false);
    }
  }
  return (
    <Button
      variant="outline"
      className={`font-mono ${large ? "h-12 text-title" : "text-meta"}`}
      aria-label="Recording shortcut"
      onClick={() => {
        modifierCombo.current = [];
        setCapture(true);
      }}
      onBlur={() => setCapture(false)}
      onKeyDown={key}
      onKeyUp={() => {
        if (capture && modifierCombo.current.length >= 2) {
          change(modifierCombo.current.join(" + "));
          setCapture(false);
        }
      }}
    >
      {capture ? "Keys… Esc cancels" : formatShortcut(value)}
    </Button>
  );
}
export function Settings({
  config,
  change,
  saveState,
  commit,
  initialGroup = "General",
}: {
  config: Config;
  change: (next: Config) => void;
  saveState: string;
  commit?: (next: Config) => Promise<void>;
  initialGroup?: string;
}) {
  const [group, setLocalGroup] = useState(initialGroup);
  const settingsContent = useRef<HTMLElement>(null);
  const previousGroup = useRef(group);
  useLayoutEffect(() => {
    if (previousGroup.current === group) return;
    previousGroup.current = group;
    settingsContent.current?.focus({ preventScroll: true });
    settingsContent.current?.scrollIntoView({ block: "nearest" });
  }, [group]);
  function setGroup(value: string) {
    setLocalGroup(value);
    useApp.setState({ settingsGroup: value });
  }
  const navigate = useApp((s) => s.navigate);
  const running = useApp((s) => s.status?.running);
  const [stopService, setStopService] = useState(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
  });
  const [testing, setTesting] = useState(false),
    [preparingMic, setPreparingMic] = useState(false),
    [connectionChecking, setConnectionChecking] = useState(false);
  const [connection, setConnection] = useState(""),
    [autostart, setAutostart] = useState(bootstrap.data?.autostart ?? false);
  useEffect(() => {
    if (bootstrap.data?.autostart !== undefined)
      setAutostart(bootstrap.data.autostart);
  }, [bootstrap.data?.autostart]);
  const credentialState = JSON.stringify(bootstrap.data?.credentials ?? {});
  useEffect(() => {
    setConnection("");
  }, [
    config.stt.base_url,
    config.stt.model,
    config.stt.key_env,
    config.cleanup.base_url,
    config.cleanup.model,
    config.cleanup.key_env,
    credentialState,
  ]);
  function set<S extends keyof Config, K extends keyof Config[S]>(
    section: S,
    field: K,
    value: Config[S][K],
  ) {
    change({ ...config, [section]: { ...config[section], [field]: value } });
  }
  const groups = [
    "General",
    "Transcription",
    "Dictionary",
    "Privacy & data",
    "Appearance",
    "System",
    "Advanced",
  ];
  return (
    <div className="space-y-8">
      <Heading title="Settings" />
      {saveState.startsWith("Not saved") && (
        <div role="alert">
          <p>Couldn’t save. Try again.</p>
          <details>
            <summary>Details</summary>
            <p>{saveState}</p>
          </details>
        </div>
      )}
      {Object.values(bootstrap.data?.credentials ?? {}).some((c) =>
        typeof c === "string"
          ? c.includes("not encrypted")
          : c.storage === "file",
      ) && (
        <div role="alert" className="rounded-lg bg-muted p-4 text-body">
          <p className="font-medium">
            API keys are stored unencrypted on this device.
          </p>
          <p className="mt-2">
            Unlock your desktop keyring, then save your keys again.
          </p>
          <Button variant="link" onClick={() => navigate("setup")}>
            Review key storage
          </Button>
        </div>
      )}
      <div className="flex flex-col gap-8 sm:flex-row">
        <nav
          aria-label="Settings groups"
          className="flex shrink-0 flex-wrap gap-1 sm:w-40 sm:flex-col"
        >
          {groups.map((g) => (
            <Button
              key={g}
              variant={g === group ? "secondary" : "ghost"}
              className="justify-start"
              aria-current={g === group ? "page" : undefined}
              onClick={() => setGroup(g)}
            >
              {g}
            </Button>
          ))}
        </nav>
        <section
          ref={settingsContent}
          key={group}
          tabIndex={-1}
          aria-label={group}
          className="screen-enter min-w-0 flex-1"
        >
          {group === "General" && (
            <>
              <Row title="Recording shortcut">
                <Shortcut
                  value={config.app.hotkey}
                  change={(v) => set("app", "hotkey", v)}
                />
              </Row>
              <Row title="Recording mode">
                <Choice
                  label="Recording mode"
                  value={config.app.recording_mode}
                  change={(v) => set("app", "recording_mode", v)}
                  items={[
                    ["hold", "Hold to talk"],
                    ["toggle", "Press to toggle"],
                  ]}
                />
              </Row>
              <Row title="Microphone">
                <DeviceSelect
                  value={config.app.microphone}
                  onChange={(v) => set("app", "microphone", v)}
                />
              </Row>
              <Row title="Test your microphone">
                <Button
                  variant="outline"
                  disabled={preparingMic}
                  onClick={() => {
                    setPreparingMic(true);
                    void action(async () => {
                      // Flush a newly selected device before the backend opens it.
                      await commit?.(config);
                      setTesting(true);
                    }).finally(() => setPreparingMic(false));
                  }}
                >
                  <FlaskConical />
                  Test mic
                </Button>
              </Row>
              <Row title="Language">
                <Choice
                  label="Language"
                  value={config.stt.language || "auto"}
                  items={[
                    ["auto", "Auto"],
                    ["en", "English"],
                    ["hi", "Hindi"],
                    ["es", "Spanish"],
                    ["fr", "French"],
                    ["de", "German"],
                    ["ja", "Japanese"],
                    ...(!["", "en", "hi", "es", "fr", "de", "ja"].includes(
                      config.stt.language,
                    )
                      ? [
                          [config.stt.language, config.stt.language] as [
                            string,
                            string,
                          ],
                        ]
                      : []),
                  ]}
                  change={(v) => set("stt", "language", v === "auto" ? "" : v)}
                />
              </Row>
            </>
          )}
          {group === "Transcription" && (
            <>
              <Row
                title="Transcription engine"
                detail="Online sends speech and vocabulary to your provider. Optional cleanup sends the transcript to your cleanup provider. On this computer uses a downloaded model."
              >
                <Choice
                  label="Transcription engine"
                  value={config.stt.engine}
                  items={[
                    ["online", "Online"],
                    ["local", "On this computer"],
                  ]}
                  change={(v) =>
                    change({
                      ...config,
                      stt: {
                        ...config.stt,
                        engine: v,
                        fallback:
                          config.stt.fallback === v
                            ? "none"
                            : config.stt.fallback,
                      },
                    })
                  }
                />
              </Row>
              {config.stt.engine === "local" ? (
                <>
                  <ModelPicker
                    language={config.stt.language}
                    applyInstalled={commit && ((id) => commit({
                      ...config,
                      stt: { ...config.stt, local_model: id },
                    }))}
                    beforeUse={() => commit?.(config) ?? Promise.resolve()}
                  />
                  <Row title="Run local models on">
                    <Choice
                      label="Local model device"
                      value={config.stt.local_device}
                      items={[
                        ["auto", "Auto"],
                        ["gpu", "GPU"],
                        ["cpu", "CPU"],
                      ]}
                      change={(v) => set("stt", "local_device", v)}
                    />
                  </Row>
                  <Row
                    title="Free memory after"
                    detail="The model loads again when you next dictate."
                  >
                    <Choice
                      label="Unload idle model"
                      value={String(config.stt.local_idle_seconds)}
                      items={[
                        ["60", "1 minute"],
                        ["300", "5 minutes"],
                        ["900", "15 minutes"],
                        ["0", "Never"],
                        ...(![0, 60, 300, 900].includes(
                          config.stt.local_idle_seconds,
                        )
                          ? [
                              [
                                String(config.stt.local_idle_seconds),
                                `${config.stt.local_idle_seconds} seconds`,
                              ] as [string, string],
                            ]
                          : []),
                      ]}
                      change={(v) =>
                        set("stt", "local_idle_seconds", Number(v))
                      }
                    />
                  </Row>
                  <Row
                    title="If the model is missing or won’t load"
                    detail="Use Online sends speech and vocabulary to your provider if the model fails to load. Unclear speech alone never triggers an upload."
                  >
                    <Choice
                      label="Local model fallback"
                      value={config.stt.fallback}
                      items={[
                        ["none", "Keep audio on this computer"],
                        ["online", "Use Online"],
                      ]}
                      change={(v) => set("stt", "fallback", v)}
                    />
                  </Row>
                  <p className="py-4 text-meta text-muted-foreground">
                    Offline cleanup applies Dictionary replacements. For English
                    speech it also removes “um” and “uh” and handles “new line”.
                  </p>
                </>
              ) : (
                <>
                  <Row title="Transcribe with">
                    <Choice
                      label="Transcription provider"
                      value={
                        config.stt.base_url === "https://api.groq.com/openai/v1"
                          ? "groq"
                          : "custom"
                      }
                      items={[
                        ["groq", "Groq"],
                        ["custom", "Custom provider"],
                      ]}
                      change={(v) => {
                        if (v === "groq")
                          change({
                            ...config,
                            stt: {
                              ...config.stt,
                              base_url: "https://api.groq.com/openai/v1",
                              model: "whisper-large-v3-turbo",
                              key_env: "GROQ_API_KEY",
                            },
                          });
                        else setGroup("Advanced");
                      }}
                    />
                  </Row>
                  <Row title="Clean up my text">
                    <Choice
                      label="Text cleanup"
                      disabled={config.stt.engine === "local"}
                      value={
                        !config.cleanup.model ? "off" : config.cleanup.style
                      }
                      items={[
                        ["off", "Off"],
                        ["light", "Light"],
                        ["thorough", "Thorough"],
                        ["email", "Email"],
                        ["casual", "Casual"],
                        ["code", "Code"],
                      ]}
                      change={(v) =>
                        change({
                          ...config,
                          cleanup: {
                            ...config.cleanup,
                            model:
                              v === "off"
                                ? ""
                                : config.cleanup.model || "openai/gpt-oss-20b",
                            style: v === "off" ? config.cleanup.style : v,
                            reasoning_effort: v === "thorough" ? "high" : "low",
                          },
                        })
                      }
                    />
                  </Row>
                  <Row title="Connection" detail={connection || undefined}>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        disabled={connectionChecking}
                        onClick={() => {
                          setConnectionChecking(true);
                          void action(() => ipc("providers.check", {}))
                            .then((v) => {
                              if (v) setConnection(v);
                            })
                            .finally(() => setConnectionChecking(false));
                        }}
                      >
                        <Check />
                        {connectionChecking ? "Checking…" : "Test connection"}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => navigate("setup")}
                      >
                        <KeyRound />
                        Manage keys
                      </Button>
                    </div>
                  </Row>
                  <Row title="When Online is unavailable">
                    <Choice
                      label="Online fallback"
                      value={config.stt.fallback}
                      items={[
                        ["none", "Ask me to retry"],
                        ["local", "Use a local model"],
                      ]}
                      change={(v) => set("stt", "fallback", v)}
                    />
                  </Row>
                  {config.stt.fallback === "local" && (
                    <ModelPicker
                      requireInstalled
                      language={config.stt.language}
                      selected={config.stt.local_model}
                      onSelect={(id) => set("stt", "local_model", id)}
                    />
                  )}
                </>
              )}
            </>
          )}
          {group === "Transcription" && config.stt.engine === "online" && (
            <Row title="Model">
              <Input
                aria-label="Transcription model"
                value={config.stt.model}
                onChange={(e) => set("stt", "model", e.target.value)}
              />
            </Row>
          )}
          {group === "Dictionary" && (
            <Dictionary config={config} change={change} />
          )}
          {group === "Privacy & data" && (
            <>
              <p className="mb-4 text-meta text-muted-foreground">
                Text only, stored on this device
              </p>
              <Row title="Save dictation history">
                <Switch
                  aria-label="Save dictation history"
                  checked={config.desktop.history_enabled}
                  onCheckedChange={(v) => set("desktop", "history_enabled", v)}
                />
              </Row>
              <Row title="Keep history for">
                <Choice
                  label="Keep history for"
                  value={
                    config.desktop.history_forever
                      ? "forever"
                      : String(config.desktop.retention_days)
                  }
                  items={[
                    ["7", "7 days"],
                    ["30", "30 days"],
                    ["90", "90 days"],
                    ["forever", "Forever"],
                    ...(![7, 30, 90].includes(config.desktop.retention_days)
                      ? [
                          [
                            String(config.desktop.retention_days),
                            `${config.desktop.retention_days} days`,
                          ] as [string, string],
                        ]
                      : []),
                  ]}
                  change={(v) =>
                    change({
                      ...config,
                      desktop: {
                        ...config.desktop,
                        history_forever: v === "forever",
                        retention_days:
                          v === "forever"
                            ? config.desktop.retention_days
                            : Number(v),
                      },
                    })
                  }
                />
              </Row>
            </>
          )}
          {group === "Privacy & data" && (
            <>
              <Row title="Saved dictations">
                <HistoryTools />
              </Row>
              <details className="py-4 text-body">
                <summary>How your data is handled</summary>
                <p className="mt-4 whitespace-pre-wrap">
                  {bootstrap.data?.privacy ??
                    "Online sends speech and vocabulary to your provider. On this computer keeps speech local unless you enable online fallback. Optional online cleanup sends text. History is stored locally without encryption."}
                </p>
              </details>
            </>
          )}
          {group === "Appearance" && (
            <>
              <Row title="Appearance">
                <Choice
                  label="Appearance"
                  value={config.desktop.theme}
                  items={[
                    ["dark", "Dark"],
                    ["light", "Light"],
                    ["system", "Follow system"],
                  ]}
                  change={(v) => set("desktop", "theme", v)}
                />
              </Row>
            </>
          )}
          {group === "Appearance" && (
            <>
              <Row title="Caelum accent">
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="size-3 rounded-sm bg-accent-brand"
                  />
                  <Choice
                    label="Caelum accent"
                    value={resolveColorTheme(config.desktop.color_theme)}
                    items={ACCENTS.map((accent) => [accent.id, accent.label])}
                    change={(v) => set("desktop", "color_theme", v)}
                  />
                </div>
              </Row>
              <Row title="Reduce motion">
                <Switch
                  aria-label="Reduce motion"
                  checked={config.app.reduced_motion}
                  onCheckedChange={(v) => set("app", "reduced_motion", v)}
                />
              </Row>
              <Row title="High contrast">
                <Switch
                  aria-label="High contrast"
                  checked={config.app.high_contrast}
                  onCheckedChange={(v) => set("app", "high_contrast", v)}
                />
              </Row>
            </>
          )}
          {group === "System" && (
            <>
              <Row title="Start at login">
                <Switch
                  aria-label="Start at login"
                  checked={autostart}
                  onCheckedChange={(v) => {
                    void action(() =>
                      ipc("launcher", { autostart: true, enabled: v }),
                    ).then((result) => {
                      if (result) setAutostart(v);
                    });
                  }}
                />
              </Row>
              <Row title="Add to app launcher">
                <Button
                  variant="outline"
                  onClick={() => {
                    void action(
                      () => ipc("launcher", {}),
                      "Added to app launcher.",
                    );
                  }}
                >
                  Add to launcher
                </Button>
              </Row>
              <Row title="Dictation service">
                <Button
                  variant="outline"
                  disabled={running === undefined}
                  onClick={() => {
                    if (running) setStopService(true);
                    else void action(() => ipc("service.start", {}));
                  }}
                >
                  {running ? "Stop service" : "Start service"}
                </Button>
              </Row>
            </>
          )}
          {group === "System" && (
            <Suspense
              fallback={
                <Skeleton
                  aria-label="Loading update controls"
                  aria-busy="true"
                  className="h-40"
                />
              }
            >
              <UpdateSettings config={config} change={change} />
            </Suspense>
          )}
          {group === "Advanced" && (
            <>
              {" "}
              {(["stt", "cleanup"] as const).map((section) => (
                <section key={section} className="py-6">
                  <h2 className="mb-4 text-section font-medium">
                    {section === "stt" ? "Transcription" : "Text cleanup"}
                  </h2>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {(["base_url", "model", "key_env"] as const).map(
                      (field) => (
                        <div key={field} className="space-y-2">
                          <Label htmlFor={`${section}-${field}`}>
                            {field === "base_url"
                              ? "Provider URL"
                              : field === "key_env"
                                ? "API key name"
                                : "Model"}
                          </Label>
                          <Input
                            id={`${section}-${field}`}
                            value={config[section][field]}
                            onChange={(e) =>
                              set(section, field, e.target.value)
                            }
                          />
                        </div>
                      ),
                    )}
                    {section === "cleanup" && (
                      <div className="space-y-2">
                        <Label htmlFor="reasoning">Reasoning effort</Label>
                        <Choice
                          label="Reasoning effort"
                          value={config.cleanup.reasoning_effort || "default"}
                          items={[
                            ["default", "Default"],
                            ["low", "Low"],
                            ["medium", "Medium"],
                            ["high", "High"],
                          ]}
                          change={(v) =>
                            set(
                              "cleanup",
                              "reasoning_effort",
                              v === "default" ? "" : v,
                            )
                          }
                        />
                      </div>
                    )}
                  </div>
                </section>
              ))}
            </>
          )}
        </section>
      </div>
      <MicrophoneTestDialog
        open={testing}
        onOpenChange={setTesting}
        device={config.app.microphone}
      />
      <Confirm
        open={stopService}
        title="Stop the dictation service?"
        detail="Active or retryable audio will be discarded. Start the service again to record."
        confirm="Discard and stop"
        onCancel={() => setStopService(false)}
        onConfirm={async () => {
          await ipc("service.stop", { discard: true });
          setStopService(false);
        }}
      />
    </div>
  );
}
export function Dictionary({
  config,
  change,
}: {
  config: Config;
  change: (next: Config) => void;
}) {
  const [word, setWord] = useState("");
  const [spoken, setSpoken] = useState("");
  const [replacement, setReplacement] = useState("");
  const words = config.stt.vocabulary
    .split(/[,\n]/)
    .map((w) => w.trim())
    .filter(Boolean);
  function save(next: string[]) {
    change({ ...config, stt: { ...config.stt, vocabulary: next.join(", ") } });
  }
  return (
    <div className="space-y-4">
      <p className="text-body text-muted-foreground">Names and words you use</p>
      <form
        className="flex gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const added = word
            .split(",")
            .map((w) => w.trim())
            .filter(Boolean);
          save([...new Set([...words, ...added])]);
          setWord("");
        }}
      >
        <Input
          aria-label="New word"
          placeholder="Add a word"
          value={word}
          onChange={(e) => setWord(e.target.value)}
        />
        <Button disabled={!word.trim()}>Add</Button>
      </form>
      <ul>
        {words.map((w, i) => (
          <li
            key={w + i}
            className="flex min-h-12 items-center justify-between border-b"
          >
            <span>{w}</span>
            <Button
              variant="ghost"
              aria-label={`Remove ${w}`}
              onClick={() => save(words.filter((_, j) => i !== j))}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
      <h2 className="pt-4 text-section font-medium">Replacements</h2>
      <p className="text-meta text-muted-foreground">
        Applied when you use a local model.
      </p>
      <form
        className="flex flex-wrap gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          change({
            ...config,
            cleanup: {
              ...config.cleanup,
              replacements: {
                ...config.cleanup.replacements,
                [spoken.trim()]: replacement.trim(),
              },
            },
          });
          setSpoken("");
          setReplacement("");
        }}
      >
        <Input
          aria-label="Spoken phrase"
          placeholder="When I say"
          value={spoken}
          onChange={(event) => setSpoken(event.target.value)}
          className="min-w-32 flex-1"
        />
        <Input
          aria-label="Replacement text"
          placeholder="Replace with"
          value={replacement}
          onChange={(event) => setReplacement(event.target.value)}
          className="min-w-32 flex-1"
        />
        <Button disabled={!spoken.trim()}>Add replacement</Button>
      </form>
      <ul>
        {Object.entries(config.cleanup.replacements).map(([from, to]) => (
          <li
            key={from}
            className="flex min-h-12 items-center justify-between gap-3 border-b text-body"
          >
            <span className="min-w-0 break-words">
              {from} → {to || "(remove)"}
            </span>
            <Button
              variant="ghost"
              aria-label={`Remove replacement ${from}`}
              onClick={() => {
                const next = { ...config.cleanup.replacements };
                delete next[from];
                change({
                  ...config,
                  cleanup: { ...config.cleanup, replacements: next },
                });
              }}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
