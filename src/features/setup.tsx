import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { ipc, type Config, errorText } from "@/lib/ipc";
import { useApp } from "@/stores/app";
import { action, Confirm, CopyButton, briefError } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Choice, Shortcut } from "./settings";
import { MicrophoneMeter, useMicrophoneLevel } from "./microphone";
import { DeviceSelect, Waveform } from "./dashboard";
import { ModelPicker, ModelDownloadLine } from "./models";
import { useModels } from "@/hooks/use-models";
const titles = [
  "Welcome to Caelum",
  "Connect your speech service",
  "Check your microphone",
  "Choose your shortcut",
  "Try it",
  "You’re all set",
];
export function Setup({
  config,
  commit,
}: {
  config: Config;
  commit: (next: Config) => Promise<void>;
}) {
  const navigate = useApp((s) => s.navigate);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
  });
  const [mode, setMode] = useState(config.stt.engine);
  const [selectedModel, setSelectedModel] = useState(config.stt.local_model);
  const [skipPractice, setSkipPractice] = useState(false);
  const modelList = useModels(config.stt.language);
  const desiredModel =
    selectedModel ||
    modelList.data?.pending_use ||
    config.stt.local_model ||
    modelList.data?.recommended?.id ||
    "";
  const selected = modelList.models.find((model) => model.id === desiredModel);
  const localReady =
    config.stt.engine === "local" &&
    (!desiredModel || config.stt.local_model === desiredModel) &&
    selected?.state === "installed";
  const manageKeys = bootstrap.data?.setup?.complete === true;
  const openSettings = useApp((s) => s.openSettings);
  const names = [
    ...new Set([
      config.stt.key_env,
      ...(config.cleanup.model ? [config.cleanup.key_env] : []),
    ]),
  ];
  const [onboardingStep, setStep] = useState(0),
    [keys, setKeys] = useState<Record<string, string>>({}),
    [selectedName, setName] = useState(config.stt.key_env);
  const name = names.includes(selectedName) ? selectedName : config.stt.key_env;
  const step = manageKeys ? 1 : onboardingStep;
  const [revealed, reveal] = useState(false),
    [consent, setConsent] = useState(false),
    [training, setTraining] = useState(false);
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [micPassed, setMicPassed] = useState(false);
  const [keyStoredInFile, setKeyStoredInFile] = useState(false);
  const [micAttempt, setMicAttempt] = useState(0);
  const [practice, setPractice] = useState(""),
    [remove, setRemove] = useState(false);
  const [privacy, setPrivacy] = useState(false),
    [advanced, setAdvanced] = useState(false),
    [autostart, setAutostart] = useState<boolean | null>(null);
  const level = useMicrophoneLevel(step === 2 || step === 4);
  useEffect(() => {
    document.getElementById("setup-title")?.focus({ preventScroll: true });
  }, [step]);
  const [shortcutHint, setShortcutHint] = useState("");
  const generation = useRef(0);
  const microphoneSave = useRef(Promise.resolve());
  const shortcutRecording = useRef(false);
  const practiceInput = useRef<HTMLTextAreaElement>(null);
  const [practicePassed, setPracticePassed] = useState(false);
  const recordPractice = useCallback(
    async (interactive = false) => {
      setBusy(true);
      setNotice("");
      practiceInput.current?.focus();
      try {
        const result = await ipc("practice", {
          consent: mode === "local" || consent,
          ...(interactive ? { interactive: true, insert: true } : {}),
        });
        setPractice(result.text);
        setPracticePassed(true);
      } catch (e) {
        setNotice(errorText(e));
      } finally {
        shortcutRecording.current = false;
        setBusy(false);
      }
    },
    [consent, mode],
  );
  useEffect(() => {
    if (step !== 3) return;
    let disposed = false;
    void ipc("shortcut.check", {})
      .then((result) => {
        if (!disposed)
          setShortcutHint(
            typeof result === "string" && result.includes("permission")
              ? "Your system may ask for shortcut access."
              : "",
          );
      })
      .catch((e) => {
        if (!disposed) setNotice(errorText(e));
      });
    return () => {
      disposed = true;
    };
  }, [step, config.app.hotkey]);
  useEffect(() => {
    if (step !== 4 || (mode === "local" && !localReady)) return;
    const parts = config.app.hotkey
      .split("+")
      .map((v) => v.trim().toUpperCase());
    const modifiers: Record<string, string> = {
      SUPER: "Meta",
      CTRL: "Control",
      ALT: "Alt",
      SHIFT: "Shift",
    };
    const letter = parts.find((v) => !modifiers[v]);
    const matches = (e: KeyboardEvent) =>
      parts
        .filter((v) => modifiers[v])
        .every((v) => e.getModifierState(modifiers[v])) &&
      (!letter || (e.key === " " ? "SPACE" : e.key.toUpperCase()) === letter);
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (shortcutRecording.current) {
          e.preventDefault();
          void ipc("sample.cancel", {});
          shortcutRecording.current = false;
        }
        return;
      }
      if (e.repeat || !matches(e)) return;
      if (busy && !shortcutRecording.current) return;
      e.preventDefault();
      if (shortcutRecording.current) {
        if (config.app.recording_mode === "toggle") {
          shortcutRecording.current = false;
          void ipc("sample.cancel", { finish: true });
        }
        return;
      }
      if (busy) return;
      shortcutRecording.current = true;
      void recordPractice(true);
    };
    const up = (e: KeyboardEvent) => {
      if (
        shortcutRecording.current &&
        config.app.recording_mode !== "toggle" &&
        (parts.includes(e.key.toUpperCase()) ||
          Object.values(modifiers).includes(e.key) ||
          (e.key === " " && letter === "SPACE"))
      ) {
        shortcutRecording.current = false;
        void ipc("sample.cancel", { finish: true });
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [
    step,
    config.app.hotkey,
    config.app.recording_mode,
    busy,
    recordPractice,
    mode,
    localReady,
  ]);
  useEffect(
    () => () => {
      void ipc("sample.cancel", {});
    },
    [],
  );
  useEffect(() => {
    if (step !== 2) return;
    const revision = ++generation.current;
    let disposed = false;
    setBusy(true);
    setMicPassed(false);
    setPracticePassed(false);
    setPractice("");
    setNotice("");
    void microphoneSave.current
      .then(() => {
        if (!disposed) return ipc("microphone.test", {});
      })
      .then(() => {
        if (!disposed && revision === generation.current) {
          setMicPassed(true);
          setNotice("We hear you ✓");
        }
      })
      .catch((e) => {
        if (!disposed) setNotice(errorText(e));
      })
      .finally(() => {
        if (!disposed) setBusy(false);
      });
    return () => {
      disposed = true;
      void ipc("sample.cancel", {});
    };
  }, [step, config.app.microphone, micAttempt]);
  async function advance(withoutModel = false) {
    setBusy(true);
    setNotice("");
    try {
      if (step === 0) {
        if (mode === "local") {
          let saved = config;
          if (
            !withoutModel &&
            desiredModel &&
            desiredModel !== modelList.data?.pending_use &&
            !(
              config.stt.engine === "local" &&
              config.stt.local_model === desiredModel
            )
          ) {
            await ipc("models.use", { id: desiredModel, when_ready: true });
            saved = (await bootstrap.refetch()).data?.config ?? config;
            await modelList.refetch();
          }
          // Empty local mode permits setup while a pending model downloads. The
          // model id itself is committed only after the candidate loads.
          if (saved.stt.engine !== "local")
            await commit({
              ...saved,
              stt: {
                ...saved.stt,
                engine: "local",
                local_model: "",
                fallback: "none",
              },
            });
          setStep(2);
          return;
        }
        if (config.stt.engine !== "online")
          await commit({
            ...config,
            stt: { ...config.stt, engine: "online", fallback: "none" },
          });
        if (
          bootstrap.data?.setup?.complete === false &&
          !config.cleanup.model &&
          config.stt.base_url.includes("api.groq.com")
        ) {
          await commit({
            ...config,
            cleanup: {
              ...config.cleanup,
              model: "openai/gpt-oss-20b",
              reasoning_effort: "low",
            },
          });
        }
        setStep(1);
      } else if (step === 1) {
        if (!consent) throw new Error("Allow audio processing to continue.");
        if (
          (config.cleanup.model + config.cleanup.base_url)
            .toLowerCase()
            .includes("contributor")
        ) {
          if (!training) throw new Error("Choose whether to allow training.");
          await commit({
            ...config,
            cleanup: {
              ...config.cleanup,
              contributor_consent:
                config.cleanup.base_url.replace(/\/$/, "") +
                "|" +
                config.cleanup.model,
            },
          });
        }
        const result = await ipc("setup.validate", {
          consent,
          keys: Object.fromEntries(
            names
              .filter((name) => keys[name])
              .map((name) => [name, keys[name]]),
          ),
        });
        setKeys({});
        await bootstrap.refetch();
        setKeyStoredInFile(Object.values(result.storage).includes("file"));
        if (manageKeys) openSettings("Transcription");
        else setStep(2);
      } else if (step === 2 && micPassed) setStep(3);
      else if (step === 3) {
        await ipc("shortcut.check", {});
        setStep(4);
      } else if (step === 4) {
        if (!practicePassed) await recordPractice();
        else setStep(5);
      } else if (step === 5) {
        await ipc("launcher", {
          autostart: true,
          enabled: autostart ?? bootstrap.data?.autostart ?? false,
        });
        await ipc("setup.finish", skipPractice ? { skip_practice: true } : {});
        await bootstrap.refetch();
        navigate("home");
      }
    } catch (e) {
      setNotice(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const credential = bootstrap.data?.credentials[name];
  return (
    <div className="mx-auto flex h-[calc(100svh-64px)] min-h-[360px] max-h-[720px] max-w-[440px] flex-col gap-6 pt-8">
      {!manageKeys && (
        <Progress
          value={((step + 1) / 6) * 100}
          aria-label={`Setup step ${step + 1} of 6`}
          className="h-1"
        />
      )}
      <section
        key={step}
        className="screen-enter min-h-0 flex-1 space-y-8 overflow-y-auto px-1 pb-2 [scrollbar-gutter:stable]"
      >
        <h1 id="setup-title" tabIndex={-1} className="text-title font-semibold">
          {manageKeys ? "Manage keys" : titles[step]}
        </h1>
        <div className="space-y-6">
          {step === 0 && (
            <>
              <p className="text-body">Speak instead of typing, in any app.</p>
              <p className="text-meta text-muted-foreground">
                About two minutes
              </p>
              <Choice
                label="Transcribe with"
                value={mode}
                items={[
                  ["online", "Online"],
                  ["local", "On this computer"],
                ]}
                change={setMode}
              />
              {mode === "local" && (
                <>
                  <p className="text-meta text-muted-foreground">
                    Audio stays on this computer. No API key needed.
                  </p>
                  <Choice
                    label="Dictation language"
                    value={config.stt.language || "auto"}
                    items={[
                      ["auto", "Auto"],
                      ["en", "English"],
                      ["hi", "Hindi"],
                      ["es", "Spanish"],
                      ["fr", "French"],
                      ["de", "German"],
                      ["ja", "Japanese"],
                    ]}
                    change={(v) =>
                      void action(() =>
                        commit({
                          ...config,
                          stt: {
                            ...config.stt,
                            language: v === "auto" ? "" : v,
                          },
                        }),
                      )
                    }
                  />
                  <ModelPicker
                    language={config.stt.language}
                    selected={selectedModel}
                    onSelect={(id) => {
                      setSelectedModel(id);
                      void action(async () => {
                        await ipc("models.use", { id, when_ready: true });
                        await bootstrap.refetch();
                        await modelList.refetch();
                      });
                    }}
                  />
                </>
              )}
            </>
          )}
          {step === 1 && (
            <>
              {names.length > 1 && (
                <Choice
                  label="Key to edit"
                  value={name}
                  change={setName}
                  items={names.map((v) => [v, v])}
                />
              )}
              <div className="space-y-2">
                <Label htmlFor="provider-key">API key</Label>
                <div className="flex gap-2">
                  <Input
                    id="provider-key"
                    type={revealed ? "text" : "password"}
                    autoComplete="off"
                    value={keys[name] ?? ""}
                    onChange={(e) =>
                      setKeys({ ...keys, [name]: e.target.value })
                    }
                    placeholder="Paste your key"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={revealed ? "Hide key" : "Reveal key"}
                    onClick={() => reveal(!revealed)}
                  >
                    {revealed ? <EyeOff /> : <Eye />}
                  </Button>
                </div>
                <p className="text-meta text-muted-foreground">
                  {typeof credential === "object" &&
                  ["keyring", "file", "environment"].includes(
                    credential.storage,
                  )
                    ? "Your key is saved"
                    : "Add a key to get started"}
                </p>
              </div>
              {config.stt.base_url.startsWith("https://api.groq.com/") && (
                <Button
                  variant="link"
                  onClick={() => void action(() => invoke("open_key_console"))}
                >
                  Get a free Groq key ↗
                </Button>
              )}
              <label className="flex items-center gap-3 text-body">
                <Checkbox
                  checked={consent}
                  onCheckedChange={(v) => setConsent(v === true)}
                />
                Send my voice to{" "}
                {config.stt.base_url.includes("api.groq.com")
                  ? "Groq"
                  : "this service"}{" "}
                to turn it into text
                {config.cleanup.model ? ", and improve the wording" : ""}
              </label>
              {(config.cleanup.model + config.cleanup.base_url)
                .toLowerCase()
                .includes("contributor") && (
                <label className="flex gap-3 text-body">
                  <Checkbox
                    checked={training}
                    onCheckedChange={(v) => setTraining(v === true)}
                  />
                  Allow this Contributor model to train on my text
                </label>
              )}
              <div className="flex flex-wrap gap-2">
                <Button variant="link" onClick={() => setPrivacy(true)}>
                  How your data is handled
                </Button>
                <Button variant="link" onClick={() => setAdvanced(true)}>
                  Use another service
                </Button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <p className="text-body">Say a few words.</p>
              <MicrophoneMeter level={level} />
              <details>
                <summary className="cursor-pointer text-body">
                  Change mic
                </summary>
                <div className="mt-4">
                  <DeviceSelect
                    value={config.app.microphone}
                    onChange={(v) => {
                      microphoneSave.current = commit({
                        ...config,
                        app: { ...config.app, microphone: v },
                      });
                      // The check effect reports save failures with its result.
                      void microphoneSave.current.catch(() => {});
                    }}
                  />
                </div>
              </details>
              {!busy && !micPassed && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    microphoneSave.current = commit(config);
                    void microphoneSave.current.catch(() => {});
                    setMicAttempt((v) => v + 1);
                  }}
                >
                  Try microphone again
                </Button>
              )}
            </>
          )}
          {step === 3 && (
            <>
              <Shortcut
                large
                value={config.app.hotkey}
                change={(v) =>
                  void action(() =>
                    commit({ ...config, app: { ...config.app, hotkey: v } }),
                  )
                }
              />
              <p className="text-meta text-muted-foreground">Press to change</p>
              <div
                role="group"
                aria-label="Recording mode"
                className="flex w-fit gap-1 rounded-lg bg-muted p-1"
              >
                {(["hold", "toggle"] as const).map((mode) => (
                  <Button
                    key={mode}
                    variant="ghost"
                    aria-pressed={config.app.recording_mode === mode}
                    className={
                      config.app.recording_mode === mode ? "bg-card" : ""
                    }
                    onClick={() =>
                      void action(() =>
                        commit({
                          ...config,
                          app: { ...config.app, recording_mode: mode },
                        }),
                      )
                    }
                  >
                    {mode === "hold" ? "Hold" : "Toggle"}
                  </Button>
                ))}
              </div>
              <p className="text-body">
                {config.app.recording_mode === "toggle"
                  ? "Press to talk. Press again to insert."
                  : "Hold to talk. Let go to insert."}
              </p>
              {shortcutHint && (
                <>
                  <p role="status" className="text-body">
                    {shortcutHint}
                  </p>
                  <details>
                    <summary>Shortcut not working?</summary>
                    <p className="mt-4 text-body">
                      Add this command to a system shortcut.
                    </p>
                    <div className="mt-2 flex items-center gap-3">
                      <code>caelum control toggle</code>
                      <CopyButton text="caelum control toggle" />
                    </div>
                  </details>
                </>
              )}
            </>
          )}
          {step === 4 && (
            <>
              {mode === "local" && (
                <p className="text-meta text-muted-foreground">
                  Your practice recording stays on this computer.
                </p>
              )}
              <p className="text-body">
                {config.app.recording_mode === "toggle" ? "Press" : "Hold"}{" "}
                <kbd>{config.app.hotkey}</kbd> and say:
              </p>
              <p className="text-body">
                “A little less typing, a little more room to think.”
              </p>
              <textarea
                ref={practiceInput}
                aria-label="Practice text"
                placeholder="Your words will appear here"
                className="min-h-32 w-full rounded-lg border border-input bg-card p-4 text-body"
                value={practice}
                onChange={(e) => setPractice(e.target.value)}
              />
              <Waveform values={Array<number>(17).fill(level)} />
            </>
          )}
          {step === 5 && (
            <>
              <dl className="divide-y rounded-lg bg-card px-4">
                {[
                  [
                    "Service",
                    mode === "local"
                      ? "On this computer"
                      : config.stt.base_url.includes("groq")
                        ? "Groq"
                        : "Custom",
                    mode === "local" ? 0 : 1,
                  ],
                  ["Microphone", config.app.microphone ?? "System default", 2],
                  ["Shortcut", config.app.hotkey, 3],
                ].map(([label, value, target]) => (
                  <div
                    key={String(label)}
                    className="flex min-h-12 items-center justify-between gap-3"
                  >
                    <dt>{label}</dt>
                    <dd className="ml-auto truncate text-right text-meta">
                      {String(value)}
                    </dd>
                    <Button
                      variant="ghost"
                      onClick={() => setStep(Number(target))}
                      aria-label={`Change ${label}`}
                    >
                      Change
                    </Button>
                  </div>
                ))}
              </dl>
              <label className="flex items-center gap-3">
                <Checkbox
                  checked={autostart ?? bootstrap.data?.autostart ?? false}
                  onCheckedChange={(v) => setAutostart(v === true)}
                />
                Start Caelum when I log in
              </label>
            </>
          )}
          {notice && (
            <div role="status" className="text-body whitespace-pre-wrap">
              {briefError(notice)}
              {briefError(notice) !== notice && (
                <details className="mt-2">
                  <summary>Details</summary>
                  <p>{notice}</p>
                </details>
              )}
            </div>
          )}
        </div>
      </section>
      {step > 0 && mode === "local" && desiredModel && (
        <ModelDownloadLine modelId={desiredModel} />
      )}
      {step === 0 && mode === "local" && (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => void advance(true)}
        >
          Continue without a model
        </Button>
      )}
      {step === 4 && mode === "local" && !practicePassed && (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setSkipPractice(true);
            setStep(5);
          }}
        >
          Try it later
        </Button>
      )}
      {keyStoredInFile && (
        <p role="alert" className="text-body">
          Key stored without encryption. Review Settings after setup.
        </p>
      )}
      <div className="flex shrink-0 justify-between gap-3">
        {manageKeys ? (
          <Button
            variant="ghost"
            onClick={() => {
              setKeys({});
              openSettings("Transcription");
            }}
          >
            Close
          </Button>
        ) : step > 0 ? (
          <Button
            variant="ghost"
            disabled={busy && step === 5}
            onClick={() => {
              if (busy) void action(() => ipc("sample.cancel", {}));
              else setStep(step === 2 && mode === "local" ? 0 : step - 1);
            }}
          >
            {busy ? "Cancel" : "Back"}
          </Button>
        ) : (
          <span />
        )}
        <Button
          disabled={
            busy ||
            (step === 1 && !consent) ||
            (step === 2 && !micPassed) ||
            (step === 4 && mode === "local" && !localReady)
          }
          onClick={() => void advance()}
        >
          {busy
            ? step === 1
              ? "Checking…"
              : "Listening…"
            : manageKeys
              ? "Save keys"
              : step === 0
                ? mode === "local"
                  ? desiredModel && selected?.state === "not_installed"
                    ? "Download and continue"
                    : "Continue"
                  : "Get started"
                : step === 5
                  ? "Done"
                  : step === 4 && !practicePassed
                    ? "Record practice"
                    : "Continue"}
        </Button>
      </div>
      <Sheet open={privacy} onOpenChange={setPrivacy}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>How your data is handled</SheetTitle>
            <SheetDescription>{bootstrap.data?.privacy}</SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>
      <Sheet open={advanced} onOpenChange={setAdvanced}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Speech service</SheetTitle>
            <SheetDescription>
              Use an OpenAI compatible service.
            </SheetDescription>
          </SheetHeader>
          <div className="space-y-4 p-4">
            {(["base_url", "model", "key_env"] as const).map((field) => (
              <div key={field} className="space-y-2">
                <Label htmlFor={field}>
                  {field === "base_url"
                    ? "Service URL"
                    : field === "model"
                      ? "Model"
                      : "Key name"}
                </Label>
                <Input
                  id={field}
                  value={config.stt[field]}
                  onChange={(e) =>
                    void action(() =>
                      commit({
                        ...config,
                        stt: { ...config.stt, [field]: e.target.value },
                      }),
                    )
                  }
                />
              </div>
            ))}
            <Button variant="ghost" onClick={() => setRemove(true)}>
              Remove saved key
            </Button>
          </div>
        </SheetContent>
      </Sheet>
      <Confirm
        open={remove}
        title="Remove the saved key?"
        detail="Dictation with this key will stop working."
        confirm="Remove key"
        onCancel={() => setRemove(false)}
        onConfirm={async () => {
          await ipc("credentials.delete", { name });
          setRemove(false);
          await bootstrap.refetch();
        }}
      />
    </div>
  );
}
