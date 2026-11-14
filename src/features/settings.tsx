import { COLOR_THEMES, resolveColorTheme } from "@/lib/themes";
import { version } from "../../package.json";
import { invoke } from "@tauri-apps/api/core";
import { useState, useRef, type ReactNode, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  KeyRound,
  FlaskConical,
  Check,
  Settings2,
  RefreshCw,
} from "lucide-react";
import { ipc, type Config } from "@/lib/ipc";
import { action, Heading, Confirm } from "@/components/common";
import { useApp } from "@/stores/app";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
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
      <SelectTrigger aria-label={label} className="w-full sm:w-56">
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
    <div className="flex flex-col justify-between gap-4 border-b py-5 last:border-0 sm:flex-row sm:items-center">
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        {detail && (
          <p className="max-w-sm text-xs leading-5 text-muted-foreground">
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
}: {
  value: string;
  change: (value: string) => void;
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
      className="font-mono text-xs"
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
}: {
  config: Config;
  change: (next: Config) => void;
  saveState: string;
}) {
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
    [checking, setChecking] = useState(false),
    [updateStatus, setUpdateStatus] = useState(""),
    [update, setUpdate] = useState<string | null>(null),
    [confirmUpdate, setConfirmUpdate] = useState(false);
  const [connection, setConnection] = useState(""),
    [autostart, setAutostart] = useState(bootstrap.data?.autostart ?? false);
  function set<S extends keyof Config, K extends keyof Config[S]>(
    section: S,
    field: K,
    value: Config[S][K],
  ) {
    change({ ...config, [section]: { ...config[section], [field]: value } });
  }
  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-3">
        <Heading
          title="Settings"
          detail="Configure recording, transcription, and appearance."
        />
        <span
          className="max-w-56 text-right text-xs text-muted-foreground"
          role="status"
        >
          {saveState}
        </span>
      </div>
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="advanced">
            <Settings2 className="mr-2 size-4" />
            Advanced
          </TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="mt-6 space-y-6">
          <Card
            className="shadow-none"
            role="region"
            aria-labelledby="theme-settings-title"
          >
            <CardHeader>
              <CardTitle>
                <h2 id="theme-settings-title">Theme</h2>
              </CardTitle>
              <CardDescription>
                Choose a color palette and appearance. Changes apply immediately
                and save automatically.
              </CardDescription>
            </CardHeader>
            <CardContent>
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
              <Row
                title="Color theme"
                detail="T3 Code palettes and Caelum’s original mint palette."
              >
                <Choice
                  label="Color theme"
                  value={resolveColorTheme(config.desktop.color_theme)}
                  items={COLOR_THEMES.map(({ id, label }) => [id, label])}
                  change={(v) => set("desktop", "color_theme", v)}
                />
              </Row>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent>
              <Row
                title="Dictation service"
                detail={status?.detail ?? "Connecting to local engine…"}
              >
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
              <Row
                title="Recording shortcut"
                detail="Hold to talk, or choose toggle mode below."
              >
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
              <Row
                title="Microphone"
                detail="Configured devices are preserved when disconnected."
              >
                <DeviceSelect
                  value={config.app.microphone}
                  onChange={(v) => set("app", "microphone", v)}
                />
              </Row>
              <Row
                title="Test your microphone"
                detail="Three seconds, locally. Nothing is saved or uploaded."
              >
                <Button
                  variant="outline"
                  disabled={testing}
                  onClick={() => {
                    setTesting(true);
                    void action(
                      () => ipc("microphone.test", {}),
                      "Heard you clearly. Nothing saved or uploaded.",
                    ).finally(() => setTesting(false));
                  }}
                >
                  <FlaskConical />
                  {testing ? "Listening…" : "Test mic"}
                </Button>
              </Row>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent>
              <Row
                title="Transcribe with"
                detail="OpenAI-compatible provider configuration is in Advanced."
              >
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
                    else
                      setConnection(
                        "Configure custom provider URL and models in Advanced.",
                      );
                  }}
                />
              </Row>
              <Row
                title="Tidy the text"
                detail="Optional cleanup. Raw transcription is retained if cleanup is unavailable."
              >
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
                    ["low", "Lightly"],
                    ["high", "Thoroughly"],
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
              <Row
                title="Provider connection"
                detail={
                  connection || "A saved key does not verify connectivity."
                }
              >
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={checking}
                    onClick={() => {
                      setChecking(true);
                      void action(() => ipc("providers.check", {}))
                        .then((v) => {
                          if (v) setConnection(v);
                        })
                        .finally(() => setChecking(false));
                    }}
                  >
                    <Check />
                    {checking ? "Checking…" : "Check"}
                  </Button>
                  <Button variant="secondary" onClick={() => navigate("setup")}>
                    <KeyRound />
                    Manage keys
                  </Button>
                </div>
              </Row>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent>
              <Row
                title="Save dictation history"
                detail="Final text only, stored locally without encryption. Old entries remain manageable."
              >
                <Switch
                  aria-label="Save dictation history"
                  checked={config.desktop.history_enabled}
                  onCheckedChange={(v) => set("desktop", "history_enabled", v)}
                />
              </Row>
              <Row
                title="Keep dictations for"
                detail="Retention runs when history is read or written."
              >
                <div className="flex items-center gap-2">
                  <Input
                    className="w-24"
                    aria-label="Retention days"
                    type="number"
                    min={1}
                    max={3650}
                    value={config.desktop.retention_days}
                    onChange={(e) =>
                      set("desktop", "retention_days", Number(e.target.value))
                    }
                  />
                  <span className="text-sm text-muted-foreground">days</span>
                </div>
              </Row>
              <Row
                title="Start at login"
                detail="Starts the dictation service in your desktop session."
              >
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
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="advanced" className="mt-6 space-y-6">
          <Card className="shadow-none">
            <CardContent>
              {(["stt", "cleanup"] as const).map((section) => (
                <section key={section} className="py-5">
                  <h2 className="mb-5 text-base font-medium">
                    {section === "stt" ? "Transcription" : "Refinement"}
                  </h2>
                  <div className="grid gap-5 sm:grid-cols-2">
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
                    {section === "stt" ? (
                      <div className="space-y-2">
                        <Label htmlFor="language">
                          Language (blank to auto-detect)
                        </Label>
                        <Input
                          id="language"
                          value={config.stt.language}
                          onChange={(e) =>
                            set("stt", "language", e.target.value)
                          }
                        />
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Label htmlFor="reasoning">Reasoning effort</Label>
                        <Input
                          id="reasoning"
                          value={config.cleanup.reasoning_effort}
                          onChange={(e) =>
                            set("cleanup", "reasoning_effort", e.target.value)
                          }
                        />
                      </div>
                    )}
                  </div>
                </section>
              ))}
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
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      <Card className="shadow-none">
        <CardContent>
          <Row
            title={`Caelum ${version}`}
            detail={
              update
                ? `Version ${update} available`
                : pending.data
                  ? "A verified update is queued."
                  : "Checks signed stable releases only. Prereleases require manual installation."
            }
          >
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={checking}
                onClick={() => {
                  if (update || pending.data) {
                    setConfirmUpdate(true);
                    return;
                  }
                  setChecking(true);
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
                        setUpdateStatus(
                          "No newer stable release is available. Prereleases are installed manually.",
                        );
                      } else {
                        setUpdateStatus("Could not check updates. Try again.");
                      }
                    })
                    .finally(() => setChecking(false));
                }}
              >
                <RefreshCw />
                {update || pending.data ? "Update & restart" : "Check updates"}
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
          <p role="status" className="text-xs text-muted-foreground">
            {updateStatus}
          </p>
          <Row title="Check updates when Caelum opens">
            <Switch
              aria-label="Check updates on launch"
              checked={config.desktop.check_updates}
              onCheckedChange={(v) => set("desktop", "check_updates", v)}
            />
          </Row>
        </CardContent>
      </Card>
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
