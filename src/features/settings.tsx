import { version } from "../../package.json";
import { invoke } from "@tauri-apps/api/core";
import {
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type KeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, FlaskConical, Check, RefreshCw } from "lucide-react";
import { ipc, type Config } from "@/lib/ipc";
import { action, Heading, Confirm } from "@/components/common";
import { useApp } from "@/stores/app";
import { Button } from "@/components/ui/button";
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
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { HistoryTools } from "./history";
import { MicrophoneTestDialog } from "./microphone";
import { ACCENTS, resolveColorTheme } from "@/lib/themes";
import { DeviceSelect } from "./dashboard";
export function Choice({
  label,
  value,
  items,
  change,
}: {
  label: string;
  value: string;
  items: [string, string][];
  change: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={change}>
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
      <div className="flex items-center">
        <p className="text-sm font-medium">{title}</p>
        {detail && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                aria-label={`About ${title}`}
                className="ml-2 inline-flex size-8 items-center justify-center rounded-md text-muted-foreground"
              >
                <Info className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{detail}</TooltipContent>
          </Tooltip>
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
      {capture ? "Keys… Esc cancels" : value}
    </Button>
  );
}
export function Settings({
  config,
  change,
  saveState,
  initialGroup = "General",
}: {
  config: Config;
  change: (next: Config) => void;
  saveState: string;
  initialGroup?: string;
}) {
  const [group, setLocalGroup] = useState(initialGroup);
  function setGroup(value: string) {
    setLocalGroup(value);
    useApp.setState({ settingsGroup: value });
  }
  const navigate = useApp((s) => s.navigate);
  const status = useApp((s) => s.status);
  const [stopService, setStopService] = useState(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
  });
  const pending = useQuery({
    queryKey: ["updates.pending"],
    queryFn: () => ipc("updates.pending", {}),
  });
  const [testing, setTesting] = useState(false),
    [connectionChecking, setConnectionChecking] = useState(false),
    [updateChecking, setUpdateChecking] = useState(false),
    [updateStatus, setUpdateStatus] = useState(""),
    [update, setUpdate] = useState<string | null>(null),
    [confirmUpdate, setConfirmUpdate] = useState(false);
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
        <section aria-label={group} className="min-w-0 flex-1">
          <h2 className="sr-only">{group}</h2>
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
                <Button variant="outline" onClick={() => setTesting(true)}>
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
                  value={
                    !config.cleanup.model
                      ? "off"
                      : config.cleanup.reasoning_effort === "high"
                        ? "high"
                        : "low"
                  }
                  items={[
                    ["off", "Off"],
                    ["low", "Light"],
                    ["high", "Thorough"],
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
                        reasoning_effort: v === "off" ? "" : v,
                      },
                    })
                  }
                />
              </Row>
              <Row title={connection || "Connection"}>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={connectionChecking}
                    onClick={() => {
                      setConnectionChecking(true);
                      void action(() => ipc("providers.check", {}))
                        .then((v) => {
                          if (v) setConnection("Connected ✓");
                        })
                        .finally(() => setConnectionChecking(false));
                    }}
                  >
                    <Check />
                    {connectionChecking ? "Checking…" : "Test connection"}
                  </Button>
                  <Button variant="secondary" onClick={() => navigate("setup")}>
                    <KeyRound />
                    Manage keys
                  </Button>
                </div>
              </Row>
            </>
          )}
          {group === "Transcription" && (
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
                    "Audio goes to your selected service. Microphone recordings are never saved. History is text only, stored on this device without encryption."}
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
                <fieldset
                  role="radiogroup"
                  aria-label="Caelum accent"
                  className="flex flex-wrap gap-2"
                >
                  <legend className="sr-only">Caelum accent</legend>
                  {ACCENTS.map((accent) => (
                    <label key={accent.id} className="relative cursor-pointer">
                      <input
                        className="peer sr-only"
                        type="radio"
                        name="caelum-accent"
                        value={accent.id}
                        checked={
                          resolveColorTheme(config.desktop.color_theme) ===
                          accent.id
                        }
                        onChange={() =>
                          set("desktop", "color_theme", accent.id)
                        }
                      />
                      <span className="flex min-h-9 items-center gap-2 rounded-md border border-transparent px-3 text-meta peer-checked:border-input peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring">
                        <span
                          aria-hidden="true"
                          className={`size-3 rounded-full ${resolveColorTheme(config.desktop.color_theme) === accent.id ? "bg-accent-brand" : "border border-input bg-muted"}`}
                        />
                        {accent.label}
                      </span>
                    </label>
                  ))}
                </fieldset>
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
                  Install entry
                </Button>
              </Row>
              <Row title="Dictation service">
                <Button
                  variant="outline"
                  disabled={!status}
                  onClick={() => {
                    if (status?.running) setStopService(true);
                    else void action(() => ipc("service.start", {}));
                  }}
                >
                  {status?.running ? "Stop service" : "Start service"}
                </Button>
              </Row>
            </>
          )}
          {group === "System" && (
            <>
              <Row
                title={`Caelum ${version}`}
                detail={
                  update
                    ? `Version ${update} available`
                    : pending.data
                      ? "A verified update is queued."
                      : "Up to date"
                }
              >
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={updateChecking}
                    onClick={() => {
                      if (update || pending.data) {
                        setConfirmUpdate(true);
                        return;
                      }
                      setUpdateChecking(true);
                      setUpdateStatus("Checking stable releases…");
                      void action(() => ipc("updates.check", {}))
                        .then((result) => {
                          if (result) {
                            setUpdate(result.version);
                            setUpdateStatus(
                              `Version ${result.version} is available.`,
                            );
                          } else if (result === null) {
                            setUpdate(null);
                            setUpdateStatus("Up to date");
                          } else {
                            setUpdateStatus(
                              "Could not check updates. Try again.",
                            );
                          }
                        })
                        .finally(() => setUpdateChecking(false));
                    }}
                  >
                    <RefreshCw />
                    {update || pending.data
                      ? "Update & restart"
                      : "Check updates"}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => void action(() => invoke("open_releases"))}
                  >
                    View releases
                  </Button>
                  {pending.data && (
                    <Button
                      variant="ghost"
                      onClick={() => {
                        void action(
                          () => ipc("updates.discard", {}),
                          "Queued update discarded.",
                        ).then(() => pending.refetch());
                      }}
                    >
                      Discard
                    </Button>
                  )}
                </div>
              </Row>
              <Row title="Check updates when Caelum opens">
                <Switch
                  aria-label="Check updates on launch"
                  checked={config.desktop.check_updates}
                  onCheckedChange={(v) => set("desktop", "check_updates", v)}
                />
              </Row>
              <p role="status" className="text-meta">
                {updateStatus}
              </p>
            </>
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
                                ? "Credential variable"
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
      <Confirm
        open={confirmUpdate}
        title={`Install ${update ? `Caelum ${update}` : "queued update"}?`}
        detail="Downloads and verifies a signed package. Administrator authorization is required. Finish dictation first. Settings and history are preserved."
        confirm="Update & restart"
        onCancel={() => setConfirmUpdate(false)}
        onConfirm={async () => {
          if (!pending.data) await ipc("updates.stage", {});
          await ipc("updates.apply", {});
          await invoke("restart_app");
          setConfirmUpdate(false);
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
    </div>
  );
}
